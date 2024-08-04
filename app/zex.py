import asyncio
import heapq
import os
from collections import defaultdict, deque
from collections.abc import Callable
from copy import deepcopy
from struct import unpack
from threading import Lock
from time import time as unix_time

import line_profiler
import pandas as pd
from loguru import logger

from .models.transaction import (
    WithdrawTransaction,
)
from .verify import chunkify, verify

DEPOSIT, WITHDRAW, BUY, SELL, CANCEL = b"dwbsc"
TRADES_TTL = 1000


class SingletonMeta(type):
    """
    This is a thread-safe implementation of Singleton.
    """

    _instances = {}

    _lock: Lock = Lock()
    """
    We now have a lock object that will be used to synchronize threads during
    first access to the Singleton.
    """

    def __call__(cls, *args, **kwargs):
        """
        Possible changes to the value of the `__init__` argument do not affect
        the returned instance.
        """
        # Now, imagine that the program has just been launched. Since there's no
        # Singleton instance yet, multiple threads can simultaneously pass the
        # previous conditional and reach this point almost at the same time. The
        # first of them will acquire lock and will proceed further, while the
        # rest will wait here.
        with cls._lock:
            # The first thread to acquire the lock, reaches this conditional,
            # goes inside and creates the Singleton instance. Once it leaves the
            # lock block, a thread that might have been waiting for the lock
            # release may then enter this section. But since the Singleton field
            # is already initialized, the thread won't create a new object.
            if cls not in cls._instances:
                instance = super().__call__(*args, **kwargs)
                cls._instances[cls] = instance
        return cls._instances[cls]


class Zex(metaclass=SingletonMeta):
    def __init__(
        self,
        kline_callback: Callable[[str, pd.DataFrame], None],
        depth_callback: Callable[[str, dict], None],
        benchmark_mode=False,
    ):
        self.kline_callback = kline_callback
        self.depth_callback = depth_callback

        self.benchmark_mode = benchmark_mode

        self.markets: dict[str, Market] = {}
        self.balances = {}
        self.amounts = {}
        self.trades = {}
        self.orders = {}
        self.withdrawals = {}
        self.deposited_blocks = {
            "BST": 42665675,
            "SEP": 6431079,
            "HOL": 2061292,
        }
        self.nonces = {}
        self.pair_lookup = {}

        self.test_mode = os.getenv("TEST_MODE")
        if self.test_mode:
            client_pub = b"\x02 \xfa;\x9b\xb1\xa9\xc7\x9a$\xe2>\x92\xce\x83\xea\xa2\xb8\xd5\x8b\x00r\x8fifG\xa5\x808\x9aFZ\x17"
            bot1_pub = b"\x02\x08v\x02\xe7\x1a\x82wzz\x9c#Kf\x8a\x1d\xc9B\xc9\xa2\x9b\xf3\x1c\x93\x11T\xeb3\x1c!\xb6\xf6\xfd"
            bot2_pub = b"\x03\x8c\xb5\xa2\x9c \xc2]\xb6Gb\x83\x13\xa9\n\xc3\xe51\x86\xcc&\x8f\xff\x91\xb0\xe0:*+\x18\xba\xa5P"
            self.balances["BST:1"] = {
                client_pub: 1_000_000_000,
                bot2_pub: 2_500_000_000,
            }
            self.balances["BST:2"] = {
                client_pub: 1_000_000_000,
                bot1_pub: 2_500_000_000,
            }
            for public in [client_pub, bot1_pub, bot2_pub]:
                self.trades[public] = deque()
                self.orders[public] = {}
                self.nonces[public] = 0

    @line_profiler.profile
    def process(self, txs: list[bytes]):
        verify(txs)
        modified_pairs = set()
        for tx in txs:
            if not tx:
                continue
            v, name = tx[0:2]
            if v != 1:
                logger.error("invalid verion", version=v)
                continue

            if name == DEPOSIT:
                self.deposit(tx)
            elif name == WITHDRAW:
                tx = WithdrawTransaction.from_tx(tx)
                self.withdraw(tx)
            elif name in (BUY, SELL):
                base_token, quote_token, pair = self._get_tx_pair(tx)

                if pair not in self.markets:
                    self.markets[pair] = Market(base_token, quote_token, self)
                    if base_token not in self.balances:
                        self.balances[base_token] = {}
                    if quote_token not in self.balances:
                        self.balances[quote_token] = {}
                # fast route check for instant match
                # if self.orderbooks[pair].match_instantly(tx):
                #     modified_pairs.add(pair)
                #     continue
                t = unpack("I", tx[32:36])[0]
                self.markets[pair].place(tx)
                while self.markets[pair].match(t):
                    pass
                modified_pairs.add(pair)

            elif name == CANCEL:
                self.markets[pair].cancel(tx)
                modified_pairs.add(pair)
            else:
                raise ValueError(f"invalid transaction name {name}")
        for pair in modified_pairs:
            if self.benchmark_mode:
                break
            asyncio.create_task(self.kline_callback(pair, self.get_kline(pair)))
            asyncio.create_task(
                self.depth_callback(pair, self.get_order_book_update(pair))
            )

    def deposit(self, tx: bytes):
        chain = tx[2:5].upper().decode()
        from_block, to_block, count = unpack(">QQH", tx[5:23])
        if self.deposited_blocks[chain] != from_block - 1:
            logger.error(
                f"invalid from block. self.deposited_blocks[chain]: {self.deposited_blocks[chain]}, from_block - 1: {from_block - 1}"
            )
            return
        self.deposited_blocks[chain] = to_block

        # chunk_size = 49
        # deposits = [tx[i : i + chunk_size] for i in range(0, len(tx), chunk_size)]
        deposits = list(chunkify(tx[23 : 23 + 49 * count], 49))
        for chunk in deposits:
            token_index, amount, t = unpack(">IdI", chunk[:16])
            token = f"{chain}:{token_index}"
            public = chunk[16:49]
            if token not in self.balances:
                self.balances[token] = {}
            if public not in self.balances[token]:
                self.balances[token][public] = 0
            self.balances[token][public] += amount
            if public not in self.trades:
                self.trades[public] = deque()
                self.orders[public] = {}
                self.nonces[public] = 0

    def cancel(self, tx: bytes):
        operation = tx[2]
        base_token, quote_token = tx[3:10], tx[10:17]
        amount, price = unpack("dd", tx[17:33])
        public = tx[41:74]
        order_slice = tx[2:41]
        for order in self.orders[public]:
            if order_slice not in order:
                continue
            self.amounts[order] = 0
            if operation == BUY:
                self.balances[quote_token][public] += amount * price
            else:
                self.balances[base_token][public] += amount
            break
        else:
            raise Exception("order not found")

    def withdraw(self, tx: WithdrawTransaction):
        if self.nonces[tx.public] != tx.nonce:
            logger.debug(f"invalid nonce: {self.nonces[tx.public]} != {tx.nonce}")
            return
        balance = self.balances[tx.token].get(tx.public, 0)
        if balance < tx.amount:
            logger.debug("balance not enough")
            return
        self.balances[tx.token][tx.public] = balance - tx.amount
        if tx.chain not in self.withdrawals:
            self.withdrawals[tx.chain] = {}
        if tx.public not in self.withdrawals[tx.chain]:
            self.withdrawals[tx.chain][tx.public] = []
        self.withdrawals[tx.chain][tx.public].append(tx)

    def get_order_book_update(self, pair: str):
        order_book_update = self.markets[pair].get_order_book_update()
        print(order_book_update)
        now = int(unix_time() * 1000)
        return {
            "e": "depthUpdate",  # Event type
            "E": now,  # Event time
            "T": now,  # Transaction time
            "s": pair.upper(),
            "U": order_book_update["U"],
            "u": order_book_update["u"],
            "pu": order_book_update["pu"],
            "b": [
                [p, q] for p, q in order_book_update["bids"].items()
            ],  # Bids to be updated
            "a": [
                [p, q] for p, q in order_book_update["asks"].items()
            ],  # Asks to be updated
        }

    def get_order_book(self, pair: str, limit: int):
        if pair not in self.markets:
            now = int(unix_time() * 1000)
            return {
                "lastUpdateId": 0,
                "E": now,  # Message output time
                "T": now,  # Transaction time
                "bids": [],
                "asks": [],
            }
        with self.markets[pair].order_book_lock:
            order_book = {
                "bids": deepcopy(self.markets[pair].bids_order_book),
                "asks": deepcopy(self.markets[pair].asks_order_book),
            }
        last_update_id = self.markets[pair].last_update_id
        now = int(unix_time() * 1000)
        return {
            "lastUpdateId": last_update_id,
            "E": now,  # Message output time
            "T": now,  # Transaction time
            "bids": [
                [p, q]
                for p, q in sorted(
                    order_book["bids"].items(), key=lambda x: x[0], reverse=True
                )[:limit]
            ],
            "asks": [
                [p, q]
                for p, q in sorted(order_book["asks"].items(), key=lambda x: x[0])[
                    :limit
                ]
            ],
        }

    def get_order_book_all(self):
        return [{}]

    def get_kline(self, pair: str) -> pd.DataFrame:
        if pair not in self.markets:
            kline = pd.DataFrame(
                columns=[
                    "OpenTime",
                    "CloseTime",
                    "Open",
                    "High",
                    "Low",
                    "Close",
                    "Volume",
                    "NumberOfTrades",
                ],
            ).set_index("OpenTime")
            return kline
        return self.markets[pair].kline

    def _get_tx_pair(self, tx: bytes):
        if tx[5:16] in self.pair_lookup:
            return self.pair_lookup[tx[5:16]]
        base_token = f"{tx[2:5].upper().decode()}:{unpack('>I', tx[5:9])[0]}"
        quote_token = f"{tx[9:12].upper().decode()}:{unpack('>I', tx[12:16])[0]}"
        pair = f"{base_token}-{quote_token}"
        self.pair_lookup[tx[5:16]] = (base_token, quote_token, pair)
        return base_token, quote_token, pair


def get_current_1m_open_time():
    now = int(unix_time())
    open_time = now - now % 60
    return open_time * 1000


class Market:
    def __init__(self, base_token: str, quote_token: str, zex: Zex):
        self.base_token = base_token
        self.quote_token = quote_token
        self.pair = f"{base_token}-{quote_token}"
        self.zex = zex

        self.amount_tolerance = 1e-8
        self.buy_orders: list[tuple[float, int, bytes]] = []
        self.sell_orders: list[tuple[float, int, bytes]] = []
        self.order_book_lock = Lock()
        self.bids_order_book: dict[float, float] = defaultdict(float)
        self.asks_order_book: dict[float, float] = defaultdict(float)
        self._order_book_updates = {"bids": {}, "asks": {}}

        self.first_id = 0
        self.final_id = 0
        self.last_update_id = 0

        self.kline = pd.DataFrame(
            columns=[
                "OpenTime",
                "CloseTime",
                "Open",
                "High",
                "Low",
                "Close",
                "Volume",
                "NumberOfTrades",
            ]
        ).set_index("OpenTime")

        self.base_token_balances = zex.balances[base_token]
        self.quote_token_balances = zex.balances[quote_token]

    def get_order_book_update(self):
        with self.order_book_lock:
            data = {
                "bids": self._order_book_updates["bids"],
                "asks": self._order_book_updates["asks"],
                "U": self.first_id,
                "u": self.final_id,
                "pu": self.last_update_id,
            }
            self._order_book_updates = {"bids": {}, "asks": {}}
            self.first_id = self.final_id + 1
            self.last_update_id = self.final_id
        return data

    def place(self, tx: bytes):
        operation, amount, price, nonce, public, index = self._parse_transaction(tx)

        if not self._validate_nonce(public, nonce):
            return

        if operation == BUY:
            self._place_buy_order(public, amount, price, index, tx)
        elif operation == SELL:
            self._place_sell_order(public, amount, price, index, tx)
        else:
            raise ValueError(f"Unsupported transaction type: {operation}")

        self.final_id += 1
        self.zex.amounts[tx] = amount
        self.zex.orders[public][tx] = True

    def match(self, t: int) -> bool:
        if not self.buy_orders or not self.sell_orders:
            return False

        buy_price, buy_i, buy_order = self.buy_orders[0]
        sell_price, sell_i, sell_order = self.sell_orders[0]
        buy_price = -buy_price

        if buy_price < sell_price:
            return False

        trade_amount = min(self.zex.amounts[buy_order], self.zex.amounts[sell_order])
        price = sell_price if sell_i < buy_i else buy_price

        buy_public = buy_order[40:73]
        sell_public = sell_order[40:73]
        self._update_orders(
            buy_order,
            sell_order,
            trade_amount,
            buy_price,
            sell_price,
            buy_public,
            sell_public,
        )
        self._update_balances(buy_public, sell_public, trade_amount, price)
        self._record_trade(
            buy_order, sell_order, buy_public, sell_public, trade_amount, t
        )

        if not self.zex.benchmark_mode:
            self._update_kline(sell_price, trade_amount)

        return True

    def get_last_price(self):
        return self.kline["Close"].iloc[-1]

    def get_price_change_24h(self):
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span >= ms_in_24h:
            prev_24h_index = 24 * 60 * 60
            return (
                self.kline["Close"].iloc[-1] - self.kline["Open"].iloc[-prev_24h_index]
            )
        return self.kline["Close"].iloc[-1] - self.kline["Open"].iloc[0]

    def get_volume_24h(self):
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span >= ms_in_24h:
            prev_24h_index = 24 * 60 * 60
            return self.kline["Volume"].iloc[-prev_24h_index:].sum()
        return self.kline["Volume"].sum()

    def _parse_transaction(self, tx: bytes):
        operation, amount, price, nonce, public, index = unpack(
            ">xB14xdd4xI33s64xQ", tx
        )
        return operation, amount, price, nonce, public, index

    def _validate_nonce(self, public: bytes, nonce: int) -> bool:
        if self.zex.nonces[public] != nonce:
            logger.debug(
                f"Invalid nonce: expected {self.zex.nonces[public]}, got {nonce}"
            )
            return False
        self.zex.nonces[public] += 1
        return True

    def _place_buy_order(
        self, public: bytes, amount: float, price: float, index: int, tx: bytes
    ):
        required = amount * price
        balance = self.quote_token_balances.get(public, 0)
        if balance < required:
            logger.debug(
                "Insufficient balance",
                current_balance=balance,
                quote_token=self.quote_token,
            )
            return

        heapq.heappush(self.buy_orders, (-price, index, tx))
        with self.order_book_lock:
            self.bids_order_book[price] += amount
            self._order_book_updates["bids"][price] = self.bids_order_book[price]

        self.quote_token_balances[public] = balance - required

    def _place_sell_order(
        self, public: bytes, amount: float, price: float, index: int, tx: bytes
    ):
        balance = self.base_token_balances.get(public, 0)
        if balance < amount:
            logger.debug(
                "Insufficient balance",
                current_balance=balance,
                base_token=self.base_token,
            )
            return

        heapq.heappush(self.sell_orders, (price, index, tx))
        with self.order_book_lock:
            self.asks_order_book[price] += amount
            self._order_book_updates["asks"][price] = self.asks_order_book[price]

        self.base_token_balances[public] = balance - amount

    def _update_orders(
        self,
        buy_order: bytes,
        sell_order: bytes,
        trade_amount: float,
        buy_price: float,
        sell_price: float,
        buy_public: bytes,
        sell_public: bytes,
    ):
        self._update_buy_order(buy_order, trade_amount, buy_price, buy_public)
        self._update_sell_order(sell_order, trade_amount, sell_price, sell_public)

    def _update_buy_order(
        self,
        buy_order: bytes,
        trade_amount: float,
        buy_price: float,
        buy_public: bytes,
    ):
        with self.order_book_lock:
            if self.zex.amounts[buy_order] > trade_amount:
                self.bids_order_book[buy_price] -= trade_amount
                self._order_book_updates["bids"][buy_price] = self.bids_order_book[
                    buy_price
                ]
                self.zex.amounts[buy_order] -= trade_amount
                self.final_id += 1
            else:
                heapq.heappop(self.buy_orders)
                self._remove_from_order_book("bids", buy_price, trade_amount)
                del self.zex.amounts[buy_order]
                del self.zex.orders[buy_public][buy_order]
                self.final_id += 1

    def _update_sell_order(
        self,
        sell_order: bytes,
        trade_amount: float,
        sell_price: float,
        sell_public: bytes,
    ):
        with self.order_book_lock:
            if self.zex.amounts[sell_order] > trade_amount:
                self.asks_order_book[sell_price] -= trade_amount
                self._order_book_updates["asks"][sell_price] = self.asks_order_book[
                    sell_price
                ]
                self.zex.amounts[sell_order] -= trade_amount
                self.final_id += 1
            else:
                heapq.heappop(self.sell_orders)
                self._remove_from_order_book("asks", sell_price, trade_amount)
                del self.zex.amounts[sell_order]
                del self.zex.orders[sell_public][sell_order]
                self.final_id += 1

    def _remove_from_order_book(self, book_type: str, price: float, amount: float):
        order_book = (
            self.bids_order_book if book_type == "bids" else self.asks_order_book
        )
        if (
            order_book[price] < amount
            or abs(order_book[price] - amount) < self.amount_tolerance
        ):
            self._order_book_updates[book_type][price] = 0
            del order_book[price]
        else:
            order_book[price] -= amount
            self._order_book_updates[book_type][price] = order_book[price]

    def _update_balances(
        self,
        buy_public: bytes,
        sell_public: bytes,
        trade_amount: float,
        price: float,
    ):
        self.base_token_balances[buy_public] = (
            self.base_token_balances.get(buy_public, 0) + trade_amount
        )
        self.quote_token_balances[sell_public] = (
            self.quote_token_balances.get(sell_public, 0) + price * trade_amount
        )

    def _record_trade(
        self,
        buy_order: bytes,
        sell_order: bytes,
        buy_public: bytes,
        sell_public: bytes,
        trade_amount: float,
        t: int,
    ):
        for public, order_type in [(buy_public, BUY), (sell_public, SELL)]:
            trade = (
                t,
                trade_amount,
                self.pair,
                order_type,
                buy_order if order_type == BUY else sell_order,
            )
            self.zex.trades[public].append(trade)
            self._prune_old_trades(public, t)

    def _prune_old_trades(self, public: bytes, current_time: int):
        trades = self.zex.trades[public]
        while trades and current_time - trades[0][0] > TRADES_TTL:
            trades.popleft()

    def _update_kline(self, price: float, trade_amount: float):
        current_candle_index = get_current_1m_open_time()
        if len(self.kline.index) != 0 and current_candle_index == self.kline.index[-1]:
            self.kline.iat[-1, 2] = max(price, self.kline.iat[-1, 2])  # High
            self.kline.iat[-1, 3] = min(price, self.kline.iat[-1, 3])  # Low
            self.kline.iat[-1, 4] = price  # Close
            self.kline.iat[-1, 5] += trade_amount  # Volume
            self.kline.iat[-1, 6] += 1  # NumberOfTrades
        else:
            self.kline.loc[current_candle_index] = [
                current_candle_index + 59999,  # CloseTime
                price,  # Open
                price,  # High
                price,  # Low
                price,  # Close
                trade_amount,  # Volume
                1,  # Volume, NumberOfTrades
            ]
