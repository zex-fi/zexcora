import asyncio
import heapq
import os
from collections import defaultdict, deque
from collections.abc import Callable
from copy import deepcopy
from struct import unpack
from threading import Lock
from time import time as unix_time
from typing import IO

import line_profiler
import pandas as pd
from loguru import logger

from .models.transaction import (
    Deposit,
    WithdrawTransaction,
)
from .proto import zex_pb2
from .verify import chunkify, verify

DEPOSIT, WITHDRAW, BUY, SELL, CANCEL, REGISTER = b"dwbscr"
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
        state_dest: str,
        light_node: bool = False,
        benchmark_mode=False,
    ):
        self.kline_callback = kline_callback
        self.depth_callback = depth_callback
        self.state_dest = state_dest
        self.light_node = light_node
        self.save_frequency = 10_000  # save state every N transactions

        self.benchmark_mode = benchmark_mode

        self.last_tx_index = 0
        self.save_state_tx_index_threshold = self.save_frequency
        self.markets: dict[str, Market] = {}
        self.balances = {}
        self.amounts = {}
        self.trades = {}
        self.orders = {}
        self.deposits: dict[bytes, list[Deposit]] = {}
        self.public_to_id_lookup: dict[bytes, int] = {}
        self.id_to_public_lookup: dict[int, bytes] = {}

        self.withdrawals: dict[str, dict[bytes, list[WithdrawTransaction]]] = {}
        self.deposited_blocks = {
            "BTC": 2874750,
            "BST": 43300371,
            "SEP": 6570903,
            "HOL": 2205681,
        }
        self.nonces = {}
        self.pair_lookup = {}

        self.last_user_id_lock = Lock()
        self.last_user_id = 0

        self.test_mode = os.getenv("TEST_MODE")
        if self.test_mode:
            from secp256k1 import PrivateKey

            client_private = (
                "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43eba0"
            )
            client_priv = PrivateKey(bytes(bytearray.fromhex(client_private)), raw=True)
            client_pub = client_priv.pubkey.serialize()
            self.register_pub(client_pub)

            private_seed = (
                "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebac"
            )
            private_seed_int = int.from_bytes(
                bytearray.fromhex(private_seed), byteorder="big"
            )

            TOKENS = {
                "BTC": [0],
                "XMR": [0],
                "HOL": [1, 2, 3],
                "BST": [1, 2, 3, 4, 5, 6],
                "SEP": [1, 2, 3, 4],
            }

            for i in range(100):
                bot_private_key = (private_seed_int + i).to_bytes(32, "big")
                bot_priv = PrivateKey(bot_private_key, raw=True)
                bot_pub = bot_priv.pubkey.serialize()
                self.register_pub(bot_pub)

                for chain, token_ids in TOKENS.items():
                    for token_id in token_ids:
                        if f"{chain}:{token_id}" not in self.balances:
                            self.balances[f"{chain}:{token_id}"] = {}
                        self.balances[f"{chain}:{token_id}"][bot_pub] = (
                            9_000_000_000_000 + i
                        )
                        self.balances[f"{chain}:{token_id}"][client_pub] = 1_000_000

    def to_protobuf(self) -> zex_pb2.ZexState:
        state = zex_pb2.ZexState()

        state.last_tx_index = self.last_tx_index

        for pair, market in self.markets.items():
            pb_market = state.markets[pair]
            pb_market.base_token = market.base_token
            pb_market.quote_token = market.quote_token
            for order in market.buy_orders:
                pb_order = pb_market.buy_orders.add()
                pb_order.price = -order[0]  # Negate price for buy orders
                pb_order.index = order[1]
                pb_order.tx = order[2]
            for order in market.sell_orders:
                pb_order = pb_market.sell_orders.add()
                pb_order.price = order[0]
                pb_order.index = order[1]
                pb_order.tx = order[2]
            for price, amount in market.bids_order_book.items():
                entry = pb_market.bids_order_book.add()
                entry.price = price
                entry.amount = amount
            for price, amount in market.asks_order_book.items():
                entry = pb_market.asks_order_book.add()
                entry.price = price
                entry.amount = amount
            pb_market.first_id = market.first_id
            pb_market.final_id = market.final_id
            pb_market.last_update_id = market.last_update_id
            pb_market.kline = market.kline.to_json().encode()

        for token, balances in self.balances.items():
            pb_balance = state.balances[token]
            for public, amount in balances.items():
                entry = pb_balance.balances.add()
                entry.public_key = public
                entry.amount = amount

        for tx, amount in self.amounts.items():
            entry = state.amounts.add()
            entry.tx = tx
            entry.amount = amount

        for public, trades in self.trades.items():
            entry = state.trades.add()
            entry.public_key = public
            for trade in trades:
                pb_trade = entry.trades.add()
                (
                    pb_trade.t,
                    pb_trade.amount,
                    pb_trade.pair,
                    pb_trade.order_type,
                    pb_trade.order,
                ) = trade

        for public, orders in self.orders.items():
            entry = state.orders.add()
            entry.public_key = public
            entry.orders.extend(orders.keys())

        for chain, withdrawals in self.withdrawals.items():
            pb_withdrawals = state.withdrawals[chain]
            for public, withdrawal_list in withdrawals.items():
                entry = pb_withdrawals.withdrawals.add()
                entry.public_key = public
                for withdrawal in withdrawal_list:
                    pb_withdrawal = entry.transactions.add()
                    pb_withdrawal.token = withdrawal.token
                    pb_withdrawal.amount = withdrawal.amount
                    pb_withdrawal.nonce = withdrawal.nonce
                    pb_withdrawal.public = withdrawal.public
                    pb_withdrawal.chain = withdrawal.chain

        state.deposited_blocks.update(self.deposited_blocks)

        for public, nonce in self.nonces.items():
            entry = state.nonces.add()
            entry.public_key = public
            entry.nonce = nonce

        for key, (base_token, quote_token, pair) in self.pair_lookup.items():
            entry = state.pair_lookup.add()
            entry.key = key
            entry.base_token = base_token
            entry.quote_token = quote_token
            entry.pair = pair

        for public, user_id in self.public_to_id_lookup.items():
            entry = state.id_lookup.add()
            entry.public_key = public
            entry.user_id = user_id

        return state

    @classmethod
    def from_protobuf(
        cls,
        pb_state: zex_pb2.ZexState,
        kline_callback: Callable[[str, pd.DataFrame], None],
        depth_callback: Callable[[str, dict], None],
        state_dest: str,
        light_node: bool,
    ):
        zex = cls(
            kline_callback,
            depth_callback,
            state_dest,
            light_node,
        )

        zex.last_tx_index = pb_state.last_tx_index

        for pair, pb_market in pb_state.markets.items():
            market = Market(pb_market.base_token, pb_market.quote_token, zex)
            market.buy_orders = [
                (-o.price, o.index, o.tx) for o in pb_market.buy_orders
            ]
            market.sell_orders = [
                (o.price, o.index, o.tx) for o in pb_market.sell_orders
            ]
            market.bids_order_book = defaultdict(
                float, {e.price: e.amount for e in pb_market.bids_order_book}
            )
            market.asks_order_book = defaultdict(
                float, {e.price: e.amount for e in pb_market.asks_order_book}
            )
            market.first_id = pb_market.first_id
            market.final_id = pb_market.final_id
            market.last_update_id = pb_market.last_update_id
            market.kline = pd.read_json(pb_market.kline.decode())
            zex.markets[pair] = market

        zex.balances = {
            token: {e.public_key: e.amount for e in pb_balance.balances}
            for token, pb_balance in pb_state.balances.items()
        }
        zex.amounts = {e.tx: e.amount for e in pb_state.amounts}
        zex.trades = {
            e.public_key: deque(trade for trade in e.trades) for e in pb_state.trades
        }
        zex.orders = {
            e.public_key: {order: True for order in e.orders} for e in pb_state.orders
        }

        zex.withdrawals = {}
        for chain, pb_withdrawals in pb_state.withdrawals.items():
            zex.withdrawals[chain] = {}
            for entry in pb_withdrawals.withdrawals:
                zex.withdrawals[chain][entry.public_key] = [
                    WithdrawTransaction(w.token, w.amount, w.nonce, w.public, w.chain)
                    for w in entry.transactions
                ]

        zex.deposited_blocks = dict(pb_state.deposited_blocks)
        zex.nonces = {e.public_key: e.nonce for e in pb_state.nonces}
        zex.pair_lookup = {
            e.key: (e.base_token, e.quote_token, e.pair) for e in pb_state.pair_lookup
        }

        zex.public_to_id_lookup = {
            entry.public_key: entry.user_id for entry in pb_state.id_lookup
        }
        zex.last_user_id = (
            max(zex.public_to_id_lookup.values()) if zex.public_to_id_lookup else 0
        )

        return zex

    def save_state(self):
        state = self.to_protobuf()
        with open(self.state_dest, "wb") as f:
            f.write(state.SerializeToString())

    @classmethod
    def load_state(
        cls,
        data: IO[bytes],
        kline_callback: Callable[[str, pd.DataFrame], None],
        depth_callback: Callable[[str, dict], None],
        state_dest: str,
        light_node: bool,
    ):
        pb_state = zex_pb2.ZexState()
        pb_state.ParseFromString(data.read())
        return cls.from_protobuf(
            pb_state,
            kline_callback,
            depth_callback,
            state_dest,
            light_node,
        )

    @line_profiler.profile
    def process(self, txs: list[bytes], last_tx_index):
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
                t = unpack(">I", tx[32:36])[0]
                # fast route check for instant match
                if self.markets[pair].match_instantly(tx, t):
                    modified_pairs.add(pair)
                    continue
                ok = self.markets[pair].place(tx)
                if not ok:
                    continue

                modified_pairs.add(pair)

            elif name == CANCEL:
                success = self.markets[pair].cancel(tx)
                if success:
                    modified_pairs.add(pair)
            elif name == REGISTER:
                self.register_pub(public=tx[2:35])
            else:
                raise ValueError(f"invalid transaction name {name}")
        for pair in modified_pairs:
            if self.benchmark_mode:
                break
            asyncio.create_task(self.kline_callback(pair, self.get_kline(pair)))
            asyncio.create_task(
                self.depth_callback(pair, self.get_order_book_update(pair))
            )
        self.last_tx_index = last_tx_index

        if self.save_state_tx_index_threshold < self.last_tx_index:
            self.save_state()
            self.save_state_tx_index_threshold = (
                self.last_tx_index
                - (self.last_tx_index % self.save_frequency)
                + self.save_frequency
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

            if public not in self.deposits:
                self.deposits[public] = []

            self.deposits[public].append(
                Deposit(
                    token=token,
                    amount=amount,
                    time=t,
                )
            )
            self.balances[token][public] += amount

            if public not in self.trades:
                self.trades[public] = deque()
            if public not in self.orders:
                self.orders[public] = {}
            if public not in self.nonces:
                self.nonces[public] = 0

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
        if tx[2:16] in self.pair_lookup:
            return self.pair_lookup[tx[2:16]]
        base_token = f"{tx[2:5].upper().decode()}:{unpack('>I', tx[5:9])[0]}"
        quote_token = f"{tx[9:12].upper().decode()}:{unpack('>I', tx[12:16])[0]}"
        pair = f"{base_token}-{quote_token}"
        self.pair_lookup[tx[2:16]] = (base_token, quote_token, pair)
        return base_token, quote_token, pair

    def register_pub(self, public: bytes):
        if public not in self.public_to_id_lookup:
            with self.last_user_id_lock:
                self.last_user_id += 1
                self.public_to_id_lookup[public] = self.last_user_id
                self.id_to_public_lookup[self.last_user_id] = public

        if public not in self.trades:
            self.trades[public] = deque()
        if public not in self.orders:
            self.orders[public] = {}
        if public not in self.deposits:
            self.deposits[public] = []
        if public not in self.nonces:
            self.nonces[public] = 0


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

    def match_instantly(self, tx: bytes, t: int) -> bool:
        operation, amount, price, nonce, public, index = self._parse_transaction(tx)

        if not self._validate_nonce(public, nonce):
            return False

        if operation == BUY:
            if not self.sell_orders:
                return False
            best_sell_price, _, _ = self.sell_orders[0]
            if price >= best_sell_price:
                return self._execute_instant_buy(public, amount, price, index, tx, t)
        elif operation == SELL:
            if not self.buy_orders:
                return False
            best_buy_price = -self.buy_orders[0][
                0
            ]  # Negate because buy prices are stored negatively
            if price <= best_buy_price:
                return self._execute_instant_sell(public, amount, price, index, tx, t)
        else:
            raise ValueError(f"Unsupported transaction type: {operation}")

        return False

    def _execute_instant_buy(
        self,
        public: bytes,
        amount: float,
        price: float,
        index: int,
        tx: bytes,
        t: int,
    ) -> bool:
        required = amount * price
        balance = self.quote_token_balances.get(public, 0)
        if balance < required:
            logger.debug(
                "Insufficient balance, current balance: {current_balance}, quote token: {quote_token}",
                current_balance=balance,
                quote_token=self.quote_token,
            )
            return False

        self.zex.orders[public][tx] = True

        # Execute the trade
        while amount > 0 and self.sell_orders and self.sell_orders[0][0] <= price:
            sell_price, _, sell_order = self.sell_orders[0]
            trade_amount = min(amount, self.zex.amounts[sell_order])
            self._execute_trade(tx, sell_order, trade_amount, sell_price, t)

            sell_public = sell_order[40:73]
            self._update_sell_order(sell_order, trade_amount, sell_price, sell_public)
            self._update_balances(public, sell_public, trade_amount, sell_price)

            amount -= trade_amount

        if amount > 0:
            # Add remaining amount to buy orders
            heapq.heappush(self.buy_orders, (-price, index, tx))
            self.zex.amounts[tx] = amount
            with self.order_book_lock:
                self.bids_order_book[price] += amount
                self._order_book_updates["bids"][price] = self.bids_order_book[price]

        return True

    def _execute_instant_sell(
        self,
        public: bytes,
        amount: float,
        price: float,
        index: int,
        tx: bytes,
        t: int,
    ) -> bool:
        balance = self.base_token_balances.get(public, 0)
        if balance < amount:
            logger.debug(
                "Insufficient balance, current balance: {current_balance}, base token: {base_token}",
                current_balance=balance,
                base_token=self.base_token,
            )
            return False

        self.zex.orders[public][tx] = True
        self.base_token_balances[public] = balance - amount

        # Execute the trade
        while amount > 0 and self.buy_orders and -self.buy_orders[0][0] >= price:
            buy_price, _, buy_order = self.buy_orders[0]
            buy_price = -buy_price  # Negate because buy prices are stored negatively
            trade_amount = min(amount, self.zex.amounts[buy_order])
            self._execute_trade(buy_order, tx, trade_amount, buy_price, t)

            buy_public = buy_order[40:73]
            self._update_buy_order(buy_order, trade_amount, buy_price, buy_public)
            self._update_balances(buy_public, public, trade_amount, buy_price)

            amount -= trade_amount

        if amount > 0:
            # Add remaining amount to sell orders
            heapq.heappush(self.sell_orders, (price, index, tx))
            self.zex.amounts[tx] = amount
            with self.order_book_lock:
                self.asks_order_book[price] += amount
                self._order_book_updates["asks"][price] = self.asks_order_book[price]

        return True

    def _execute_trade(
        self,
        buy_order: bytes,
        sell_order: bytes,
        trade_amount: float,
        price: float,
        t: int,
    ):
        buy_public = buy_order[40:73]
        sell_public = sell_order[40:73]

        self._record_trade(
            buy_order, sell_order, buy_public, sell_public, trade_amount, t
        )

        if not self.zex.benchmark_mode and not self.zex.light_node:
            self._update_kline(price, trade_amount)

        self.final_id += 1

    def place(self, tx: bytes) -> bool:
        operation, amount, price, nonce, public, index = self._parse_transaction(tx)

        if operation == BUY:
            ok = self._place_buy_order(public, amount, price, index, tx)
        elif operation == SELL:
            ok = self._place_sell_order(public, amount, price, index, tx)
        else:
            raise ValueError(f"Unsupported transaction type: {operation}")

        if not ok:
            return False

        self.final_id += 1
        self.zex.amounts[tx] = amount
        self.zex.orders[public][tx] = True
        return True

    def cancel(self, tx: bytes) -> bool:
        operation = tx[2]
        amount, price = unpack(">dd", tx[17:33])
        public = tx[41:74]
        order_slice = tx[2:41]
        for order in self.zex.orders[public]:
            if order_slice not in order:
                continue
            self.zex.amounts[order] = 0
            if operation == BUY:
                self.quote_token_balances[public] += amount * price
            else:
                self.base_token_balances[public] += amount
            return True
        else:
            return False

    def get_last_price(self):
        if len(self.kline) == 0:
            return 0
        return self.kline["Close"].iloc[-1]

    def get_price_change_24h(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span >= ms_in_24h:
            prev_24h_index = 24 * 60 * 60
            return (
                self.kline["Close"].iloc[-1] - self.kline["Open"].iloc[-prev_24h_index]
            )
        return self.kline["Close"].iloc[-1] - self.kline["Open"].iloc[0]

    def get_price_change_24h_percent(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span >= ms_in_24h:
            prev_24h_index = 24 * 60 * 60
            open_price = self.kline["Open"].iloc[-prev_24h_index]
            close_price = self.kline["Close"].iloc[-1]
            if open_price == 0:
                return 0
            return ((close_price - open_price) / open_price) * 100

        close_price = self.kline["Close"].iloc[-1]
        open_price = self.kline["Open"].iloc[0]
        if open_price == 0:
            return 0
        return ((close_price - open_price) / open_price) * 100

    def get_price_change_7D_percent(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_7D = 7 * 24 * 60 * 60 * 1000
        if total_span > ms_in_7D:
            prev_7D_index = 7 * 24 * 60 * 60
            open_price = self.kline["Open"].iloc[-prev_7D_index]
            close_price = self.kline["Close"].iloc[-1]
            return (close_price - open_price) / open_price
        return self.kline["Close"].iloc[-1] - self.kline["Open"].iloc[0]

    def get_volume_24h(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span > ms_in_24h:
            prev_24h_index = 24 * 60 * 60
            return self.kline["Volume"].iloc[-prev_24h_index:].sum()
        return self.kline["Volume"].sum()

    def get_high_24h(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span > ms_in_24h:
            prev_24h_index = 24 * 60 * 60
            return self.kline["High"].iloc[-prev_24h_index:].max()
        return self.kline["High"].max()

    def get_low_24h(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span > ms_in_24h:
            prev_24h_index = 24 * 60 * 60
            return self.kline["Low"].iloc[-prev_24h_index:].min()
        return self.kline["Low"].min()

    def _parse_transaction(self, tx: bytes):
        operation, amount, price, nonce, public, index = unpack(
            ">xB14xdd4xI33s64xQ", tx
        )
        return operation, amount, price, nonce, public, index

    def _validate_nonce(self, public: bytes, nonce: int) -> bool:
        if self.zex.nonces[public] != nonce:
            logger.debug(
                "Invalid nonce: expected {expected_nonce}, got {nonce}",
                expected_nonce=self.zex.nonces[public],
                nonce=nonce,
            )
            return False
        self.zex.nonces[public] += 1
        return True

    def _place_buy_order(
        self, public: bytes, amount: float, price: float, index: int, tx: bytes
    ) -> bool:
        required = amount * price
        balance = self.quote_token_balances.get(public, 0)
        if balance < required:
            logger.debug(
                "Insufficient balance, current balance: {current_balance}, quote token: {quote_token}",
                current_balance=balance,
                quote_token=self.quote_token,
            )
            return False

        heapq.heappush(self.buy_orders, (-price, index, tx))
        with self.order_book_lock:
            self.bids_order_book[price] += amount
            self._order_book_updates["bids"][price] = self.bids_order_book[price]

        self.quote_token_balances[public] = balance - required
        return True

    def _place_sell_order(
        self, public: bytes, amount: float, price: float, index: int, tx: bytes
    ) -> bool:
        balance = self.base_token_balances.get(public, 0)
        if balance < amount:
            logger.debug(
                "Insufficient balance, current balance: {current_balance}, base token: {base_token}",
                current_balance=balance,
                base_token=self.base_token,
            )
            return False

        heapq.heappush(self.sell_orders, (price, index, tx))
        with self.order_book_lock:
            self.asks_order_book[price] += amount
            self._order_book_updates["asks"][price] = self.asks_order_book[price]

        self.base_token_balances[public] = balance - amount
        return True

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
