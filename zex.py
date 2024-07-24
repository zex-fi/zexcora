import asyncio
from copy import deepcopy
import heapq
from struct import unpack
from collections import deque
from threading import Lock
from time import time as unix_time
from typing import Callable

import pandas as pd
import line_profiler
from loguru import logger

from models.transaction import (
    DepositTransaction,
    MarketTransaction,
    WithdrawTransaction,
)
from verify import chunkify, verify


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
        kline_callback: Callable[[pd.DataFrame], None],
        depth_callback: Callable[[dict], None],
        benchmark_mode=False,
    ):
        self.kline_callback = kline_callback
        self.depth_callback = depth_callback

        self.benchmark_mode = benchmark_mode

        self.orderbooks: dict[str, Market] = {}
        self.balances = {}
        self.amounts = {}
        self.trades = {}
        self.orders = {}
        self.withdrawals = {}
        self.deposited_blocks = {"pol": 0, "eth": 0, "bst": 42051703}
        self.nonces = {}

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
                tx = MarketTransaction(tx)
                if tx.pair not in self.orderbooks:
                    base, quote = tx.pair.split("-")
                    self.orderbooks[tx.pair] = Market(base, quote, self)
                    if tx.base_token not in self.balances:
                        self.balances[tx.base_token] = {}
                    if tx.quote_token not in self.balances:
                        self.balances[tx.quote_token] = {}
                # fast route check for instant match
                # if self.orderbooks[tx.pair].match_instantly(tx):
                #     modified_pairs.add(tx.pair)
                #     continue

                self.orderbooks[tx.pair].place(tx)
                while self.orderbooks[tx.pair].match(tx.time):
                    pass
                modified_pairs.add(tx.pair)

            elif name == CANCEL:
                tx = MarketTransaction(tx)
                self.orderbooks[tx.pair].cancel(tx)
                modified_pairs.add(tx.pair)
            else:
                raise ValueError(f"invalid transaction name {name}")
        for pair in modified_pairs:
            if self.benchmark_mode:
                break
            asyncio.create_task(self.kline_callback(self.get_kline(pair)))
            asyncio.create_task(self.depth_callback(self.get_order_book_update(pair)))

    def deposit(self, tx: bytes):
        chain = tx[2:5].decode()
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
            token = f"{chain}:{unpack('>I', chunk[:4])[0]}"
            amount, t = unpack(">dI", chunk[4:16])
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

    def cancel(self, tx: MarketTransaction):
        for order in self.orders[tx.public]:
            if tx.order_slice not in order:
                continue
            self.amounts[order] = 0
            if tx.operation == BUY:
                self.balances[tx.quote_token][tx.public] += tx.amount * tx.price
            else:
                self.balances[tx.base_token][tx.public] += tx.amount
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
        order_book = self.orderbooks[pair].get_order_book_update()
        print(order_book)
        now = int(unix_time() * 1000)
        return {
            "e": "depthUpdate",  # Event type
            "E": now,  # Event time
            "T": now,  # Transaction time
            "s": pair.upper(),
            "U": order_book["U"],
            "u": order_book["u"],
            "pu": order_book["pu"],
            "b": [[p, q] for p, q in order_book["bids"].items()],  # Bids to be updated
            "a": [[p, q] for p, q in order_book["asks"].items()],  # Asks to be updated
        }

    def get_order_book(self, pair: str, limit: int):
        if pair not in self.orderbooks:
            now = int(unix_time() * 1000)
            return {
                "lastUpdateId": 0,
                "E": now,  # Message output time
                "T": now,  # Transaction time
                "bids": [],
                "asks": [],
            }
        with self.orderbooks[pair].order_book_lock:
            order_book = deepcopy(self.orderbooks[pair].order_book)
        last_update_id = self.orderbooks[pair].last_update_id
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
        if pair not in self.orderbooks:
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
        return self.orderbooks[pair].kline


def get_current_1m_open_time():
    now = int(unix_time())
    open_time = now - now % 60
    return open_time * 1000


class Market:
    def __init__(self, base_token, quote_token, zex: Zex):
        self.amount_tolerance = 1e-8
        # bid price
        self.buy_orders: list[
            tuple[float, int, MarketTransaction]
        ] = []  # Max heap for buy orders, prices negated
        # ask price
        self.sell_orders: list[
            tuple[float, int, MarketTransaction]
        ] = []  # Min heap for sell orders
        heapq.heapify(self.buy_orders)
        heapq.heapify(self.sell_orders)
        self.order_book_lock = Lock()
        self.bids_order_book = {}
        self.asks_order_book = {}

        self._bids_order_book_update = {}
        self._asks_order_book_update = {}

        self.first_id = 0
        self.final_id = 0
        self.last_update_id = 0
        self.base_token = base_token
        self.quote_token = quote_token
        self.pair = base_token + quote_token
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
            ],
        ).set_index("OpenTime")

        self.zex = zex
        self.base_token_balances = zex.balances[base_token]
        self.quote_token_balances = zex.balances[quote_token]

    def get_order_book_update(self):
        data = {
            "bids": self._bids_order_book_update,
            "asks": self._asks_order_book_update,
        }
        self.bids_order_book = {}
        self.asks_order_book = {}

        data["U"] = self.first_id
        data["u"] = self.final_id
        data["pu"] = self.last_update_id
        self.first_id = self.final_id + 1
        self.last_update_id = self.final_id
        return data

    @line_profiler.profile
    def match_instantly(self, tx: MarketTransaction):
        return False

    @line_profiler.profile
    def place(self, tx: MarketTransaction):
        if self.zex.nonces[tx.public] != tx.nonce:
            logger.debug(
                f"invalid nonce: expected: {self.zex.nonces[tx.public]} !=  got: {tx.nonce}"
            )
            return
        self.zex.nonces[tx.public] += 1
        if tx.operation == BUY:
            required = tx.amount * tx.price
            balance = self.quote_token_balances.get(tx.public, 0)
            if balance < required:
                logger.debug(
                    "balance not enough",
                    current_balance=balance,
                    base_token=tx.base_token,
                )
                return
            heapq.heappush(self.buy_orders, (-tx.price, tx.index, tx))
            with self.order_book_lock:
                amount = 0
                if tx.price not in self.bids_order_book:
                    amount = tx.amount
                    self.bids_order_book[tx.price] = amount
                else:
                    amount = self.bids_order_book[tx.price] + tx.amount
                    self.bids_order_book[tx.price] = amount

                self._bids_order_book_update[tx.price] = amount
            self.quote_token_balances[tx.public] = balance - required
        elif tx.operation == SELL:
            required = tx.amount
            balance = self.base_token_balances.get(tx.public, 0)
            if balance < required:
                logger.debug(
                    "balance not enough",
                    current_balance=balance,
                    base_token=tx.base_token,
                )
                return
            heapq.heappush(self.sell_orders, (tx.price, tx.index, tx))
            with self.order_book_lock:
                amount = 0
                if tx.price not in self.asks_order_book:
                    amount = tx.amount
                    self.asks_order_book[tx.price] = amount
                else:
                    amount = self.asks_order_book[tx.price] + tx.amount
                    self.asks_order_book[tx.price] = amount

                self._asks_order_book_update[tx.price] = amount
            self.base_token_balances[tx.public] = balance - required
        else:
            raise NotImplementedError(
                f"transaction type {tx.operation} is not supported"
            )
        self.final_id += 1
        self.zex.amounts[tx.raw_tx] = tx.amount
        self.zex.orders[tx.public][tx.raw_tx] = True

    @line_profiler.profile
    def match(self, t):
        # Match orders while there are matching orders available
        if not self.buy_orders or not self.sell_orders:
            return False

        # Check if the top buy order matches the top sell order
        buy_price, buy_i, buy_order = self.buy_orders[0]
        sell_price, sell_i, sell_order = self.sell_orders[0]
        buy_price = -buy_price
        if buy_price < sell_price:
            return False

        # Determine the amount to trade
        trade_amount = min(
            self.zex.amounts[buy_order.raw_tx], self.zex.amounts[sell_order.raw_tx]
        )

        # Update orders
        buy_public = buy_order.public
        sell_public = sell_order.public

        if self.zex.amounts[buy_order.raw_tx] > trade_amount:
            with self.order_book_lock:
                self.bids_order_book[buy_price] -= trade_amount
                self._bids_order_book_update[buy_price] = self.bids_order_book[
                    buy_price
                ]
            self.zex.amounts[buy_order.raw_tx] -= trade_amount
            self.final_id += 1
        else:
            heapq.heappop(self.buy_orders)
            with self.order_book_lock:
                if (
                    self.bids_order_book[buy_price] < trade_amount
                    or abs(self.bids_order_book[buy_price] - trade_amount)
                    < self.amount_tolerance
                ):
                    self._bids_order_book_update[buy_price] = 0
                    del self.bids_order_book[buy_price]
                else:
                    self.bids_order_book[buy_price] -= trade_amount
                    self._bids_order_book_update[buy_price] = self.bids_order_book[
                        buy_price
                    ]
            del self.zex.amounts[buy_order.raw_tx]
            del self.zex.orders[buy_public][buy_order.raw_tx]
            self.final_id += 1

        if self.zex.amounts[sell_order.raw_tx] > trade_amount:
            with self.order_book_lock:
                amount = self.asks_order_book[sell_price] - trade_amount
                self.asks_order_book[sell_price] = amount
                self._asks_order_book_update[sell_price] = amount
            self.zex.amounts[sell_order.raw_tx] -= trade_amount
            self.final_id += 1
        else:
            heapq.heappop(self.sell_orders)
            with self.order_book_lock:
                if (
                    self.asks_order_book[sell_price] < trade_amount
                    or abs(self.asks_order_book[sell_price] - trade_amount)
                    < self.amount_tolerance
                ):
                    self._asks_order_book_update[sell_price] = 0
                    del self.asks_order_book[sell_price]
                else:
                    amount = self.asks_order_book[sell_price] - trade_amount
                    self.asks_order_book[sell_price] = amount
                    self._asks_order_book_update[sell_price] = amount
            del self.zex.orders[sell_public][sell_order.raw_tx]
            del self.zex.amounts[sell_order.raw_tx]
            self.final_id += 1

        # This should be delegated to another process
        if not self.zex.benchmark_mode:
            current_candle_index = get_current_1m_open_time()
            if current_candle_index in self.kline.index:
                self.kline.iat[-1, 2] = max(sell_price, self.kline.iat[-1, 2])  # High
                self.kline.iat[-1, 3] = min(sell_price, self.kline.iat[-1, 3])  # Low
                self.kline.iat[-1, 4] = sell_price  # Close
                self.kline.iat[-1, 5] += trade_amount  # Volume
                self.kline.iat[-1, 6] += 1  # NumberOfTrades
            else:
                self.kline.loc[current_candle_index] = [
                    current_candle_index + 59999,  # CloseTime
                    sell_price,  # Open
                    sell_price,  # High
                    sell_price,  # Low
                    sell_price,  # Close
                    trade_amount,  # Volume
                    1,  # NumberOfTrades
                ]

        # Amount for canceled order is set to 0
        if trade_amount == 0:
            return False

        # Update users balances
        price = sell_price if sell_i < buy_i else buy_price
        base_balance = self.zex.balances[self.base_token].get(buy_public, 0)
        self.zex.balances[self.base_token][buy_public] = base_balance + trade_amount
        quote_balance = self.zex.balances[self.quote_token].get(sell_public, 0)
        self.zex.balances[self.quote_token][sell_public] = (
            quote_balance + price * trade_amount
        )

        # Add trades to users in-memory history
        buy_q = self.zex.trades[buy_public]
        sell_q = self.zex.trades[sell_public]
        buy_q.append((t, trade_amount, self.pair, BUY))
        sell_q.append((t, trade_amount, self.pair, SELL))

        # Remove trades older than TRADES_TTL from users in-memory history
        while len(buy_q) > 0 and t - buy_q[0][0] > TRADES_TTL:
            buy_q.popleft()
        while len(sell_q) > 0 and t - sell_q[0][0] > TRADES_TTL:
            sell_q.popleft()

        return True
