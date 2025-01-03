from collections import deque
from collections.abc import Callable
from copy import deepcopy
from decimal import Decimal, FloatOperation, getcontext
from io import BytesIO
from threading import Lock
from time import time as unix_time
from typing import IO, Literal
import asyncio
import heapq
import struct
import time

from loguru import logger
import pandas as pd

from .config import settings
from .models.transaction import (
    Deposit,
    DepositTransaction,
    WithdrawTransaction,
)
from .proto import zex_pb2
from .singleton import SingletonMeta
from .zex_types import Chain, ContractAddress, ExecutionType, Token, UserPublic

BTC_DEPOSIT, DEPOSIT, WITHDRAW, BUY, SELL, CANCEL, REGISTER = b"xdwbscr"
TRADES_TTL = 1000


def get_token_name(chain, address):
    for verified_name, tokens in settings.zex.verified_tokens.items():
        if chain not in tokens:
            continue
        if tokens[chain].contract_address == address:
            return verified_name
    return f"{chain}:{address}"


class Zex(metaclass=SingletonMeta):
    def __init__(
        self,
        kline_callback: Callable[[str, pd.DataFrame], None],
        depth_callback: Callable[[str, dict], None],
        order_callback: Callable[
            [UserPublic, int, str, str, Decimal, Decimal, str, int, bool], None
        ],
        deposit_callback: Callable[[UserPublic, Chain, str, Decimal], None],
        withdraw_callback: Callable[[UserPublic, Chain, str, Decimal], None],
        state_dest: str,
        light_node: bool = False,
        benchmark_mode=False,
    ):
        c = getcontext()
        c.traps[FloatOperation] = True

        self.kline_callback = kline_callback
        self.depth_callback = depth_callback
        self.order_callback = order_callback
        self.deposit_callback = deposit_callback
        self.withdraw_callback = withdraw_callback

        self.state_dest = state_dest
        self.light_node = light_node
        self.save_frequency = (
            settings.zex.state_save_frequency
        )  # save state every N transactions

        self.benchmark_mode = benchmark_mode

        self.last_tx_index = 0
        self.saved_state_index = 0
        self.save_state_tx_index_threshold = self.save_frequency
        self.markets: dict[str, Market] = {}
        self.zex_balance_on_chain: dict[Token, dict[ContractAddress, Decimal]] = {}
        self.assets: dict[Token, dict[UserPublic, Decimal]] = {
            settings.zex.usdt_mainnet: {}
        }

        self.contract_decimal_on_chain: dict[Chain, dict[ContractAddress, int]] = {}
        for _, details in settings.zex.verified_tokens.items():
            for chain, token_info in details.items():
                if chain not in self.contract_decimal_on_chain:
                    self.contract_decimal_on_chain[chain] = {}
                self.contract_decimal_on_chain[chain][token_info.contract_address] = (
                    token_info.decimal
                )

        self.amounts: dict[UserPublic, Decimal] = {}
        self.trades: dict[UserPublic, deque] = {}
        self.orders: dict[UserPublic, dict[bytes, Literal[True]]] = {}
        self.user_deposits: dict[UserPublic, list[Deposit]] = {}
        self.public_to_id_lookup: dict[UserPublic, int] = {}
        self.id_to_public_lookup: dict[int, UserPublic] = {}

        self.user_withdraws_on_chain: dict[
            Chain, dict[UserPublic, list[WithdrawTransaction]]
        ] = {}

        self.withdraws_on_chain: dict[Chain, list[WithdrawTransaction]] = {}
        self.deposits: dict[Chain, set[tuple[str, int]]] = {
            chain: set() for chain in settings.zex.chains
        }
        self.user_withdraw_nonce_on_chain: dict[Chain, dict[UserPublic, int]] = {
            k: {} for k in self.deposits.keys()
        }
        self.withdraw_nonce_on_chain: dict[Chain, int] = {
            k: 0 for k in self.deposits.keys()
        }
        self.nonces: dict[bytes, int] = {}
        self.pair_lookup: dict[str, tuple[str, str, str]] = {}

        self.last_user_id_lock = Lock()
        self.last_user_id = 0

        self.test_mode = not settings.zex.mainnet
        if self.test_mode:
            self.initialize_test_mode()

    def initialize_test_mode(self):
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

        tokens = {
            "BTC": [("0x" + "0" * 40, 8)],
            "POL": [
                ("0xc2132D05D31c914a87C6611C10748AEb04B58e8F", 6),
                ("0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359", 6),
                ("0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6", 8),
                ("0x53E0bca35eC356BD5ddDFebbD1Fc0fD03FaBad39", 18),
                ("0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619", 18),  # WETH
            ],
            "BSC": [
                ("0x55d398326f99059fF775485246999027B3197955", 18),
                ("0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d", 18),
                ("0x0555E30da8f98308EdB960aa94C0Db47230d2B9c", 8),
                ("0xF8A0BF9cF54Bb92F17374d9e9A321E6a111a51bD", 18),
            ],
            "OPT": [
                ("0x94b008aA00579c1307B0EF2c499aD98a8ce58e58", 6),
                ("0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85", 6),
                ("0x68f180fcCe6836688e9084f035309E29Bf0A2095", 8),
                ("0x350a791Bfc2C21F9Ed5d10980Dad2e2638ffa7f6", 18),
            ],
        }

        for i in range(1):
            bot_private_key = (private_seed_int + i).to_bytes(32, "big")
            bot_priv = PrivateKey(bot_private_key, raw=True)
            bot_pub = bot_priv.pubkey.serialize()
            self.register_pub(bot_pub)

            for chain, details in tokens.items():
                if chain not in self.zex_balance_on_chain:
                    self.zex_balance_on_chain[chain] = {}
                for contract_address, decimal in details:
                    token_name = get_token_name(chain, contract_address)
                    if token_name not in self.assets:
                        self.assets[token_name] = {}
                    if chain not in self.contract_decimal_on_chain:
                        self.contract_decimal_on_chain[chain] = {}

                    pair = f"{token_name}-{settings.zex.usdt_mainnet}"
                    if pair not in self.markets:
                        self.markets[pair] = Market(
                            token_name, settings.zex.usdt_mainnet, self
                        )

                    self.contract_decimal_on_chain[chain][contract_address] = decimal
                    self.assets[token_name][bot_pub] = Decimal("5_000_000")
                    self.assets[token_name][client_pub] = Decimal("1_000_000")
                    self.zex_balance_on_chain[chain][contract_address] = Decimal(
                        "5_000_000"
                    )

    def to_protobuf(self) -> zex_pb2.ZexState:
        state = zex_pb2.ZexState()

        state.last_tx_index = self.last_tx_index

        for pair, market in self.markets.items():
            pb_market = state.markets[pair]
            pb_market.base_token = market.base_token
            pb_market.quote_token = market.quote_token
            for order in market.buy_orders:
                pb_order = pb_market.buy_orders.add()
                pb_order.price = str(-order[0])  # Negate price for buy orders
                pb_order.tx = order[1]
            for order in market.sell_orders:
                pb_order = pb_market.sell_orders.add()
                pb_order.price = str(order[0])
                pb_order.tx = order[1]
            for price, amount in market.bids_order_book.items():
                entry = pb_market.bids_order_book.add()
                entry.price = str(price)
                entry.amount = str(amount)
            for price, amount in market.asks_order_book.items():
                entry = pb_market.asks_order_book.add()
                entry.price = str(price)
                entry.amount = str(amount)
            pb_market.first_id = market.first_id
            pb_market.final_id = market.final_id
            pb_market.last_update_id = market.last_update_id

            # TODO: find a better solution since loading pickle is dangerous
            buffer = BytesIO()
            market.kline.to_pickle(buffer)
            pb_market.kline = buffer.getvalue()

        for token, balances in self.assets.items():
            pb_balance = state.balances[token]
            for public, amount in balances.items():
                entry = pb_balance.balances.add()
                entry.public_key = public
                entry.amount = str(amount)

        for tx, amount in self.amounts.items():
            entry = state.amounts.add()
            entry.tx = tx
            entry.amount = str(amount)

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
                ) = trade[0], str(trade[1]), trade[2], trade[3], trade[4]

        for public, orders in self.orders.items():
            entry = state.orders.add()
            entry.public_key = public
            entry.orders.extend(orders.keys())

        for address, withdraws in self.withdraws_on_chain.items():
            pb_withdraws = state.withdraws_on_chain[address]
            entry = pb_withdraws.withdraws.add()
            entry.raw_txs.extend([w.raw_tx for w in withdraws])

        for address, withdraws in self.user_withdraws_on_chain.items():
            pb_withdraws = state.user_withdraws_on_chain[address]
            for public, withdraw_list in withdraws.items():
                entry = pb_withdraws.withdraws.add()
                entry.public_key = public
                entry.raw_txs.extend([w.raw_tx for w in withdraw_list])

        for address, withdraw_nonces in self.user_withdraw_nonce_on_chain.items():
            pb_withdraw_nonces = state.user_withdraw_nonce_on_chain[address]
            for public, nonce in withdraw_nonces.items():
                entry = pb_withdraw_nonces.nonces.add()
                entry.public_key = public
                entry.nonce = nonce

        state.withdraw_nonce_on_chain.update(self.withdraw_nonce_on_chain)

        for address, deposits in self.deposits.items():
            pb_deposits = state.deposits[address]
            for deposit in deposits:
                entry = pb_deposits.deposits.add()
                entry.tx_hash = deposit[0]
                entry.vout = deposit[1]

        for public, nonce in self.nonces.items():
            entry = state.nonces.add()
            entry.public_key = public
            entry.nonce = nonce

        for public, deposits in self.user_deposits.items():
            entry = state.user_deposits.add()
            entry.public_key = public
            for deposit in deposits:
                pb_deposit = entry.deposits.add()
                pb_deposit.tx_hash = deposit.tx_hash
                pb_deposit.chain = deposit.chain
                pb_deposit.token_contract = deposit.token_contract
                pb_deposit.amount = str(deposit.amount)
                pb_deposit.decimal = deposit.decimal
                pb_deposit.time = deposit.time
                pb_deposit.user_id = deposit.user_id
                pb_deposit.vout = deposit.vout

        for public, user_id in self.public_to_id_lookup.items():
            entry = state.public_to_id_lookup.add()
            entry.public_key = public
            entry.user_id = user_id
        state.id_to_public_lookup.update(self.id_to_public_lookup)

        for chain, details in self.contract_decimal_on_chain.items():
            state.contract_decimal_on_chain[chain].contract_decimal.update(details)

        return state

    @classmethod
    def from_protobuf(
        cls,
        pb_state: zex_pb2.ZexState,
        kline_callback: Callable[[str, pd.DataFrame], None],
        depth_callback: Callable[[str, dict], None],
        order_callback: Callable,
        deposit_callback: Callable,
        withdraw_callback: Callable,
        state_dest: str,
        light_node: bool,
    ):
        zex = cls(
            kline_callback,
            depth_callback,
            order_callback,
            deposit_callback,
            withdraw_callback,
            state_dest,
            light_node,
        )

        zex.last_tx_index = pb_state.last_tx_index

        zex.assets = {
            token: {e.public_key: Decimal(e.amount) for e in pb_balance.balances}
            for token, pb_balance in pb_state.balances.items()
        }
        for pair, pb_market in pb_state.markets.items():
            market = Market(pb_market.base_token, pb_market.quote_token, zex)
            market.buy_orders = [
                (-Decimal(o.price), o.tx) for o in pb_market.buy_orders
            ]
            market.sell_orders = [
                (Decimal(o.price), o.tx) for o in pb_market.sell_orders
            ]

            market.bids_order_book = {
                Decimal(e.price): Decimal(e.amount) for e in pb_market.bids_order_book
            }
            market.asks_order_book = {
                Decimal(e.price): Decimal(e.amount) for e in pb_market.asks_order_book
            }

            market.first_id = pb_market.first_id
            market.final_id = pb_market.final_id
            market.last_update_id = pb_market.last_update_id
            market.kline = pd.read_pickle(BytesIO(pb_market.kline))
            zex.markets[pair] = market

        zex.amounts = {e.tx: Decimal(e.amount) for e in pb_state.amounts}
        zex.trades = {
            e.public_key: deque(
                (
                    trade.t,
                    Decimal(trade.amount),
                    trade.pair,
                    trade.order_type,
                    trade.order,
                )
                for trade in e.trades
            )
            for e in pb_state.trades
        }
        zex.orders = {
            e.public_key: {order: True for order in e.orders} for e in pb_state.orders
        }

        zex.withdraws_on_chain = {}
        for chain, pb_withdraws in pb_state.withdraws_on_chain.items():
            zex.withdraws_on_chain[chain] = {}
            for entry in pb_withdraws.withdraws:
                zex.withdraws_on_chain[chain] = [
                    WithdrawTransaction.from_tx(raw_tx) for raw_tx in entry.raw_txs
                ]
        zex.withdraw_nonce_on_chain = dict(pb_state.withdraw_nonce_on_chain)

        zex.user_withdraws_on_chain = {}
        for chain, pb_withdraws in pb_state.user_withdraws_on_chain.items():
            zex.user_withdraws_on_chain[chain] = {}
            for entry in pb_withdraws.withdraws:
                zex.user_withdraws_on_chain[chain][entry.public_key] = [
                    WithdrawTransaction.from_tx(raw_tx) for raw_tx in entry.raw_txs
                ]

        zex.user_withdraw_nonce_on_chain = {}
        for chain, pb_withdraw_nonces in pb_state.user_withdraw_nonce_on_chain.items():
            zex.user_withdraw_nonce_on_chain[chain] = {
                entry.public_key: entry.nonce for entry in pb_withdraw_nonces.nonces
            }

        zex.deposits = {
            chain: {(item.tx_hash, item.vout) for item in e.deposits}
            for chain, e in pb_state.deposits.items()
        }

        zex.nonces = {e.public_key: e.nonce for e in pb_state.nonces}

        zex.user_deposits = {
            e.public_key: [
                Deposit(
                    tx_hash=pb_deposit.tx_hash,
                    chain=pb_deposit.chain,
                    token_contract=pb_deposit.token_contract,
                    amount=Decimal(pb_deposit.amount),
                    decimal=pb_deposit.decimal,
                    time=pb_deposit.time,
                    user_id=pb_deposit.user_id,
                    vout=pb_deposit.vout,
                )
                for pb_deposit in e.deposits
            ]
            for e in pb_state.user_deposits
        }

        zex.public_to_id_lookup = {
            entry.public_key: entry.user_id for entry in pb_state.public_to_id_lookup
        }
        zex.id_to_public_lookup = dict(pb_state.id_to_public_lookup)

        zex.contract_decimal_on_chain = {
            k: v.contract_decimal for k, v in pb_state.contract_decimal_on_chain.items()
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
        order_callback: Callable,
        deposit_callback: Callable,
        withdraw_callback: Callable,
        state_dest: str,
        light_node: bool,
    ):
        pb_state = zex_pb2.ZexState()
        pb_state.ParseFromString(data.read())
        return cls.from_protobuf(
            pb_state,
            kline_callback,
            depth_callback,
            order_callback,
            deposit_callback,
            withdraw_callback,
            state_dest,
            light_node,
        )

    def process(self, txs: list[bytes], last_tx_index):
        modified_pairs: set[str] = set()
        for tx in txs:
            if not tx:
                continue
            v, name = tx[0:2]
            if v != 1:
                logger.error("invalid version", version=v)
                continue

            if name == DEPOSIT or name == BTC_DEPOSIT:
                tx = DepositTransaction.from_tx(tx)
                self.deposit(tx)
            elif name == WITHDRAW:
                tx = WithdrawTransaction.from_tx(tx)
                self.withdraw(tx)
            elif name in (BUY, SELL):
                base_token, quote_token, pair = self._get_tx_pair(tx)

                if pair not in self.markets:
                    if base_token not in self.assets:
                        self.assets[base_token] = {}
                    if quote_token not in self.assets:
                        self.assets[quote_token] = {}
                    self.markets[pair] = Market(base_token, quote_token, self)
                t = int(unix_time())
                # fast route check for instant match
                logger.debug(
                    "executing tx base: {base_token}, quote: {quote_token}",
                    base_token=base_token,
                    quote_token=quote_token,
                )

                _, _, _, nonce, public = _parse_transaction(tx)
                if not self.validate_nonce(public, nonce):
                    continue

                if self.markets[pair].match_instantly(tx, t):
                    modified_pairs.add(pair)
                    continue
                ok = self.markets[pair].place(tx)
                if not ok:
                    continue

                modified_pairs.add(pair)

            elif name == CANCEL:
                base_token, quote_token, pair = self._get_tx_pair(tx[1:])
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

        if self.saved_state_index + self.save_frequency < self.last_tx_index:
            self.saved_state_index = self.last_tx_index
            self.save_state()

    def deposit(self, tx: DepositTransaction):
        for deposit in tx.deposits:
            if deposit.user_id < 1:
                logger.critical(
                    f"invalid user id: {deposit.user_id}, tx_hash: {deposit.tx_hash}, vout: {deposit.vout}, "
                    f"token_contract: {deposit.token_contract}, amount: {deposit.amount}, decimal: {deposit.decimal}"
                )
                continue
            if self.last_user_id < deposit.user_id:
                logger.error(
                    f"deposit for missing user: {deposit.user_id}, tx_hash: {deposit.tx_hash}, vout: {deposit.vout}, "
                    f"token_contract: {deposit.token_contract}, amount: {deposit.amount}, decimal: {deposit.decimal}"
                )
                continue

            if deposit.chain not in self.deposits:
                self.deposits[deposit.chain] = set()
            if deposit.chain not in self.zex_balance_on_chain:
                self.zex_balance_on_chain[deposit.chain] = {}

            if (deposit.tx_hash, deposit.vout) in self.deposits[deposit.chain]:
                logger.error(
                    f"chain: {deposit.chain}, tx_hash: {deposit.tx_hash}, vout: {deposit.vout} has already been deposited"
                )
                continue
            self.deposits[deposit.chain].add((deposit.tx_hash, deposit.vout))

            if deposit.token_contract not in self.zex_balance_on_chain[deposit.chain]:
                self.zex_balance_on_chain[deposit.chain][deposit.token_contract] = (
                    Decimal("0")
                )

            if deposit.chain not in self.contract_decimal_on_chain:
                self.contract_decimal_on_chain[deposit.chain] = {}
            if (
                deposit.token_contract
                not in self.contract_decimal_on_chain[deposit.chain]
            ):
                self.contract_decimal_on_chain[deposit.chain][
                    deposit.token_contract
                ] = deposit.decimal

            if (
                self.contract_decimal_on_chain[deposit.chain][deposit.token_contract]
                != deposit.decimal
            ):
                logger.warning(
                    f"decimal for contract {deposit.token_contract} changed "
                    f"from {self.contract_decimal_on_chain[deposit.chain][deposit.token_contract]} to {deposit.decimal}"
                )
                self.contract_decimal_on_chain[deposit.chain][
                    deposit.token_contract
                ] = deposit.decimal

            public = self.id_to_public_lookup[deposit.user_id]

            if deposit.token_name not in self.assets:
                self.assets[deposit.token_name] = {}
            if public not in self.assets[deposit.token_name]:
                self.assets[deposit.token_name][public] = Decimal("0")

            pair = f"{deposit.token_name}-{settings.zex.usdt_mainnet}"
            if pair not in self.markets:
                self.markets[pair] = Market(
                    deposit.token_name, settings.zex.usdt_mainnet, self
                )

            if public not in self.user_deposits:
                self.user_deposits[public] = []

            self.user_deposits[public].append(deposit)
            self.assets[deposit.token_name][public] += deposit.amount
            self.zex_balance_on_chain[deposit.chain][deposit.token_contract] += (
                deposit.amount
            )
            logger.info(
                f"deposit on chain: {deposit.chain}, token: {deposit.token_name}, amount: {deposit.amount} for user: {public}, "
                f"tx_hash: {deposit.tx_hash}, new balance: {self.assets[deposit.token_name][public]}"
            )

            if public not in self.trades:
                self.trades[public] = deque()
            if public not in self.orders:
                self.orders[public] = {}
            if public not in self.nonces:
                self.nonces[public] = 0

            asyncio.create_task(
                self.deposit_callback(
                    public.hex(), deposit.chain, deposit.token_name, deposit.amount
                )
            )

    def withdraw(self, tx: WithdrawTransaction):
        if tx.amount <= 0:
            logger.debug(f"invalid amount: {tx.amount}")
            return

        if tx.chain not in self.user_withdraw_nonce_on_chain:
            logger.debug(f"invalid chain: {self.nonces[tx.public]} != {tx.nonce}")
            return

        if self.user_withdraw_nonce_on_chain[tx.chain].get(tx.public, 0) != tx.nonce:
            logger.debug(f"invalid nonce: {self.nonces[tx.public]} != {tx.nonce}")
            return

        token_info = settings.zex.verified_tokens.get(tx.token_name)
        if token_info:
            if tx.chain in token_info:
                # Token is verified and chain is supported
                token = tx.token_name
                token_contract = token_info[tx.chain].contract_address
            else:
                # Token is verified, but the chain is not supported
                # Fail transaction
                logger.debug(
                    f"invalid chain: {tx.chain} for withdraw of verified token: {tx.token_name}"
                )
                return
        else:
            token = tx.token_name
            _, token_contract = tx.token_name.split(":")

        balance = self.assets[token].get(tx.public, Decimal("0"))
        if balance < tx.amount:
            logger.debug("balance not enough")
            return
        if self.zex_balance_on_chain[tx.chain][token_contract] < tx.amount:
            vault_balance = self.zex_balance_on_chain[tx.chain][token_contract]
            logger.debug(
                f"vault balance: {vault_balance}, withdraw amount: {tx.amount}, vault does not have enough balance"
            )
            return

        if tx.public not in self.user_withdraw_nonce_on_chain[tx.chain]:
            self.user_withdraw_nonce_on_chain[tx.chain][tx.public] = 0

        self.assets[token][tx.public] = balance - tx.amount
        self.zex_balance_on_chain[tx.chain][token_contract] -= tx.amount

        if tx.chain not in self.user_withdraws_on_chain:
            self.user_withdraws_on_chain[tx.chain] = {}
        if tx.public not in self.user_withdraws_on_chain[tx.chain]:
            self.user_withdraws_on_chain[tx.chain][tx.public] = []
        self.user_withdraws_on_chain[tx.chain][tx.public].append(tx)

        if tx.chain not in self.withdraw_nonce_on_chain:
            self.withdraw_nonce_on_chain[tx.chain] = 0
        self.withdraw_nonce_on_chain[tx.chain] += 1

        self.user_withdraw_nonce_on_chain[tx.chain][tx.public] += 1
        if tx.chain not in self.withdraws_on_chain:
            self.withdraws_on_chain[tx.chain] = []
        self.withdraws_on_chain[tx.chain].append(tx)

        logger.info(
            f"withdraw on chain: {tx.chain}, token: {tx.token_name}, amount: {tx.amount} for user: {tx.public}, "
            f"new balance: {self.assets[tx.token_name][tx.public]}"
        )

        asyncio.create_task(
            self.withdraw_callback(tx.public.hex(), tx.chain, tx.token_name, tx.amount)
        )

    def validate_nonce(self, public: bytes, nonce: int) -> bool:
        if self.nonces[public] != nonce:
            logger.debug(
                "Invalid nonce: expected {expected_nonce}, got {nonce}",
                expected_nonce=self.nonces[public],
                nonce=nonce,
            )
            return False
        self.nonces[public] += 1
        return True

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
                [float(p), float(q)] for p, q in order_book_update["bids"].items()
            ],  # Bids to be updated
            "a": [
                [float(p), float(q)] for p, q in order_book_update["asks"].items()
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
        base_token, quote_token = self._extract_base_and_quote_token(tx)
        pair = f"{base_token}-{quote_token}"
        return base_token, quote_token, pair

    def _extract_base_and_quote_token(self, tx):
        base_token_len, quote_token_len = struct.unpack(">xx B B", tx[:4])

        order_format = f">{base_token_len}s {quote_token_len}s"
        order_format_size = struct.calcsize(order_format)
        base_token, quote_token = struct.unpack(
            order_format, tx[4 : 4 + order_format_size]
        )
        base_token = base_token.decode("ascii")
        quote_token = quote_token.decode("ascii")
        return base_token, quote_token

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
        if public not in self.user_deposits:
            self.user_deposits[public] = []
        if public not in self.nonces:
            self.nonces[public] = 0

        logger.info(
            "user registered with public: {public}, user id: {user_id}",
            public=public.hex(),
            user_id=self.public_to_id_lookup[public],
        )


def get_current_1m_open_time():
    now = int(unix_time())
    open_time = now - now % 60
    return open_time * 1000


def _parse_transaction(tx: bytes) -> tuple[int, Decimal, Decimal, int, bytes]:
    operation, base_token_len, quote_token_len = struct.unpack(">x B B B", tx[:4])

    order_format = f">{base_token_len}s {quote_token_len}s d d I I 33s"
    order_format_size = struct.calcsize(order_format)
    base_token, quote_token, amount, price, t, nonce, public = struct.unpack(
        order_format, tx[4 : 4 + order_format_size]
    )
    base_token = base_token.decode("ascii")
    quote_token = quote_token.decode("ascii")

    return operation, Decimal(str(amount)), Decimal(str(price)), nonce, public


class Market:
    def __init__(self, base_token: str, quote_token: str, zex: Zex):
        self.base_token = base_token
        self.quote_token = quote_token
        self.pair = f"{base_token}-{quote_token}"
        self.zex = zex

        self.buy_orders: list[tuple[Decimal, bytes]] = []
        self.sell_orders: list[tuple[Decimal, bytes]] = []
        self.order_book_lock = Lock()
        self.bids_order_book: dict[Decimal, Decimal] = {}
        self.asks_order_book: dict[Decimal, Decimal] = {}
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

        self.base_token_balances = zex.assets[base_token]
        self.quote_token_balances = zex.assets[quote_token]

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
        operation, amount, price, nonce, public = _parse_transaction(tx)
        if price <= 0 or amount <= 0:
            return False

        if operation == BUY:
            if not self.sell_orders:
                return False
            best_sell_price = self.sell_orders[0][0]
            if price >= best_sell_price:
                return self._execute_instant_buy(public, nonce, amount, price, tx, t)
        elif operation == SELL:
            if not self.buy_orders:
                return False
            # Negate because buy prices are stored negatively
            best_buy_price = -self.buy_orders[0][0]
            if price <= best_buy_price:
                return self._execute_instant_sell(public, nonce, amount, price, tx, t)
        else:
            raise ValueError(f"Unsupported transaction type: {operation}")

        return False

    def _execute_instant_buy(
        self,
        public: bytes,
        nonce: int,
        amount: Decimal,
        price: Decimal,
        tx: bytes,
        t: int,
    ) -> bool:
        initial_amount = amount
        required = amount * price
        balance = self.quote_token_balances.get(public, 0)
        if balance < required:
            logger.debug(
                "Insufficient balance, current balance: {current_balance}, "
                "side: buy, base token: {base_token}, quote token: {quote_token}",
                current_balance=balance,
                base_token=self.base_token,
                quote_token=self.quote_token,
            )
            return False

        # Execute the trade
        while amount > 0 and self.sell_orders and self.sell_orders[0][0] <= price:
            sell_price, sell_order = self.sell_orders[0]
            trade_amount = min(amount, self.zex.amounts[sell_order])
            self._execute_trade(tx, sell_order, trade_amount, sell_price, t)

            sell_public = sell_order[-97:-64]
            self._update_sell_order(sell_order, trade_amount, sell_price, sell_public)
            self._update_balances(public, sell_public, trade_amount, sell_price)
            self.quote_token_balances[public] -= trade_amount * sell_price
            amount -= trade_amount

        if amount > 0:
            # Add remaining amount to buy orders
            heapq.heappush(self.buy_orders, (-price, tx))
            self.zex.amounts[tx] = amount
            self.zex.orders[public][tx] = True
            with self.order_book_lock:
                if price in self.bids_order_book:
                    self.bids_order_book[price] += amount
                else:
                    self.bids_order_book[price] = amount
                self._order_book_updates["bids"][price] = self.bids_order_book[price]
            self.quote_token_balances[public] -= amount * price

            # TODO: send partial fill message for taker order
            t = int(time.time() * 1000)
            asyncio.create_task(
                self.zex.order_callback(
                    public=public.hex(),
                    nonce=nonce,
                    symbol=self.pair,
                    side="buy",
                    amount=initial_amount,
                    price=price,
                    execution_type=ExecutionType.TRADE,
                    order_status="PARTIALLY_FILLED",
                    last_filled=initial_amount - amount,
                    cumulative_filled=initial_amount - amount,
                    last_executed_price=sell_price,
                    transaction_time=t,
                    is_on_orderbook=True,
                    is_maker=False,
                    cumulative_quote_asset_quantity=Decimal(0),  # TODO
                    last_quote_asset_quantity=Decimal(0),  # TODO
                    quote_order_quantity=Decimal(0),  # TODO
                )
            )

        else:
            # TODO: send completed message for taker order
            t = int(time.time() * 1000)
            asyncio.create_task(
                self.zex.order_callback(
                    public=public.hex(),
                    nonce=nonce,
                    symbol=self.pair,
                    side="buy",
                    amount=initial_amount,
                    price=price,
                    execution_type=ExecutionType.TRADE,
                    order_status="COMPLETED",
                    last_filled=initial_amount,
                    cumulative_filled=initial_amount,
                    last_executed_price=sell_price,
                    transaction_time=t,
                    is_on_orderbook=False,
                    is_maker=False,
                    cumulative_quote_asset_quantity=Decimal(0),  # TODO
                    last_quote_asset_quantity=Decimal(0),  # TODO
                    quote_order_quantity=Decimal(0),  # TODO
                )
            )

        return True

    def _execute_instant_sell(
        self,
        public: bytes,
        nonce: int,
        amount: Decimal,
        price: Decimal,
        tx: bytes,
        t: int,
    ) -> bool:
        initial_amount = amount
        balance = self.base_token_balances.get(public, 0)
        if balance < amount:
            logger.debug(
                "Insufficient balance, current balance: {current_balance}, "
                "side: sell, base token: {base_token}, quote token: {quote_token}",
                current_balance=balance,
                base_token=self.base_token,
                quote_token=self.quote_token,
            )
            return False
        # Execute the trade
        while amount > 0 and self.buy_orders and -self.buy_orders[0][0] >= price:
            buy_price, buy_order = self.buy_orders[0]
            buy_price = -buy_price  # Negate because buy prices are stored negatively
            trade_amount = min(amount, self.zex.amounts[buy_order])
            self._execute_trade(buy_order, tx, trade_amount, buy_price, t)

            buy_public = buy_order[-97:-64]
            self._update_buy_order(buy_order, trade_amount, buy_price, buy_public)
            self._update_balances(buy_public, public, trade_amount, buy_price)
            self.base_token_balances[public] -= trade_amount

            amount -= trade_amount

        if amount > 0:
            # Add remaining amount to sell orders
            heapq.heappush(self.sell_orders, (price, tx))
            self.zex.amounts[tx] = amount
            self.zex.orders[public][tx] = True
            with self.order_book_lock:
                if price in self.asks_order_book:
                    self.asks_order_book[price] += amount
                else:
                    self.asks_order_book[price] = amount
                self._order_book_updates["asks"][price] = self.asks_order_book[price]
            self.base_token_balances[public] -= amount

            t = int(time.time() * 1000)
            asyncio.create_task(
                self.zex.order_callback(
                    public=public.hex(),
                    nonce=nonce,
                    symbol=self.pair,
                    side="sell",
                    amount=initial_amount,
                    price=price,
                    execution_type=ExecutionType.TRADE,
                    order_status="PARTIALLY_FILLED",
                    last_filled=initial_amount - amount,
                    cumulative_filled=initial_amount - amount,
                    last_executed_price=buy_price,
                    transaction_time=t,
                    is_on_orderbook=True,
                    is_maker=False,
                    cumulative_quote_asset_quantity=Decimal(0),  # TODO
                    last_quote_asset_quantity=Decimal(0),  # TODO
                    quote_order_quantity=Decimal(0),  # TODO
                )
            )

        else:
            t = int(time.time() * 1000)
            asyncio.create_task(
                self.zex.order_callback(
                    public.hex(),
                    nonce,
                    self.pair,
                    "sell",
                    initial_amount,
                    price,
                    ExecutionType.TRADE,
                    "FILLED",
                    last_filled=initial_amount,
                    cumulative_filled=initial_amount,
                    last_executed_price=buy_price,
                    transaction_time=t,
                    is_on_orderbook=True,
                    is_maker=False,
                    cumulative_quote_asset_quantity=Decimal(0),  # TODO
                    last_quote_asset_quantity=Decimal(0),  # TODO
                    quote_order_quantity=Decimal(0),  # TODO
                )
            )
        return True

    def _execute_trade(
        self,
        buy_order: bytes,
        sell_order: bytes,
        trade_amount: Decimal,
        price: Decimal,
        t: int,
    ):
        buy_public = buy_order[-97:-64]
        sell_public = sell_order[-97:-64]

        self._record_trade(
            buy_order, sell_order, buy_public, sell_public, trade_amount, t
        )

        if not self.zex.benchmark_mode and not self.zex.light_node:
            self._update_kline(float(price), float(trade_amount))

        self.final_id += 1

    def place(self, tx: bytes) -> bool:
        operation, amount, price, nonce, public = _parse_transaction(tx)
        if price < 0 or amount < 0:
            asyncio.create_task(
                self.zex.order_callback(
                    public.hex(),
                    nonce,
                    self.pair,
                    "buy" if operation == BUY else "sell",
                    amount,
                    price,
                    ExecutionType.REJECTED,
                    "REJECTED",
                    last_filled=Decimal("0"),
                    cumulative_filled=Decimal("0"),
                    last_executed_price=Decimal("0"),
                    transaction_time=int(time.time() * 1000),
                    is_on_orderbook=False,
                    is_maker=True,
                    cumulative_quote_asset_quantity=Decimal(0),  # TODO
                    last_quote_asset_quantity=Decimal(0),  # TODO
                    quote_order_quantity=Decimal(0),  # TODO
                    reject_reason="invalid price or amount",
                )
            )
            return False

        if operation == BUY:
            side = "buy"
            order_book_update_key = "bids"
            order_book = self.bids_order_book
            orders_heap = self.buy_orders
            heap_item = (-price, tx)

            balances_dict = self.quote_token_balances
            balance = Decimal(str(balances_dict.get(public, 0)))

            required = amount * price
        elif operation == SELL:
            side = "sell"
            order_book_update_key = "asks"
            order_book = self.asks_order_book
            orders_heap = self.sell_orders
            heap_item = (price, tx)

            balances_dict = self.base_token_balances
            balance = Decimal(str(balances_dict.get(public, 0)))

            required = amount
        else:
            raise ValueError(f"Unsupported transaction type: {operation}")

        if balance < required:
            logger.debug(
                "Insufficient balance, current balance: {current_balance}, "
                "side: {side}, base token: {base_token}, quote token: {quote_token}",
                current_balance=float(balance),
                side=side,
                base_token=self.base_token,
                quote_token=self.quote_token,
            )

            asyncio.create_task(
                self.zex.order_callback(
                    public.hex(),
                    nonce,
                    self.pair,
                    "buy" if operation == BUY else "sell",
                    amount,
                    price,
                    ExecutionType.REJECTED,
                    "REJECTED",
                    last_filled=Decimal("0"),
                    cumulative_filled=Decimal("0"),
                    last_executed_price=Decimal("0"),
                    transaction_time=int(time.time() * 1000),
                    is_on_orderbook=False,
                    is_maker=True,
                    cumulative_quote_asset_quantity=Decimal(0),  # TODO
                    last_quote_asset_quantity=Decimal(0),  # TODO
                    quote_order_quantity=Decimal(0),  # TODO
                    reject_reason="insufficient balance",
                )
            )
            return False

        heapq.heappush(orders_heap, heap_item)
        with self.order_book_lock:
            if price in order_book:
                order_book[price] += amount
            else:
                order_book[price] = amount
            self._order_book_updates[order_book_update_key][price] = order_book[price]

        balances_dict[public] = balance - required

        self.final_id += 1
        self.zex.amounts[tx] = amount
        self.zex.orders[public][tx] = True

        asyncio.create_task(
            self.zex.order_callback(
                public.hex(),
                nonce,
                self.pair,
                side,
                amount,
                price,
                ExecutionType.NEW,
                "NEW",
                last_filled=Decimal("0"),
                cumulative_filled=Decimal("0"),
                last_executed_price=Decimal("0"),
                transaction_time=int(time.time() * 1000),
                is_on_orderbook=True,
                is_maker=True,
                cumulative_quote_asset_quantity=Decimal(0),  # TODO
                last_quote_asset_quantity=Decimal(0),  # TODO
                quote_order_quantity=Decimal(0),  # TODO
            )
        )
        return True

    def cancel(self, tx: bytes) -> bool:
        public = tx[-97:-64]
        order_slice = tx[2:-97]
        for order in self.zex.orders[public]:
            if order_slice not in order:
                continue
            operation, amount, price, nonce, public = _parse_transaction(order)
            amount = self.zex.amounts.pop(order)
            del self.zex.orders[public][order]
            if operation == BUY:
                self.quote_token_balances[public] += amount * price
                self.buy_orders.remove((-price, order))
                heapq.heapify(self.buy_orders)
                with self.order_book_lock:
                    if amount >= self.bids_order_book[price]:
                        del self.bids_order_book[price]
                        self._order_book_updates["bids"][price] = 0
                    else:
                        self.bids_order_book[price] -= amount
                        self._order_book_updates["bids"][price] = self.bids_order_book[
                            price
                        ]

            else:
                self.base_token_balances[public] += amount
                self.sell_orders.remove((price, order))
                heapq.heapify(self.sell_orders)
                with self.order_book_lock:
                    if amount >= self.asks_order_book[price]:
                        del self.asks_order_book[price]
                        self._order_book_updates["asks"][price] = 0
                    else:
                        self.asks_order_book[price] -= amount
                        self._order_book_updates["asks"][price] = self.asks_order_book[
                            price
                        ]
            self.final_id += 1
            asyncio.create_task(
                self.zex.order_callback(
                    public.hex(),
                    nonce,
                    self.pair,
                    "buy" if operation == BUY else "sell",
                    amount,
                    price,
                    ExecutionType.CANCELED,
                    "CANCELED",
                    last_filled=Decimal("0"),
                    cumulative_filled=Decimal("0"),
                    last_executed_price=Decimal("0"),
                    transaction_time=int(time.time() * 1000),
                    is_on_orderbook=False,
                    is_maker=True,
                    cumulative_quote_asset_quantity=Decimal(0),  # TODO
                    last_quote_asset_quantity=Decimal(0),  # TODO
                    quote_order_quantity=Decimal(0),  # TODO
                )
            )
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
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            return (
                self.kline["Close"].iloc[-1] - self.kline["Open"].iloc[prev_24h_index]
            )
        return self.kline["Close"].iloc[-1] - self.kline["Open"].iloc[0]

    def get_price_change_24h_percent(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span >= ms_in_24h:
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

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

    def get_price_change_7d_percent(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_7d = 7 * 24 * 60 * 60 * 1000
        if total_span > ms_in_7d:
            target_time = self.kline.index[-1] - 7 * 24 * 60 * 60 * 1000
            prev_7d_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            open_price = self.kline["Open"].iloc[prev_7d_index]
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
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            return self.kline["Volume"].iloc[prev_24h_index:].sum()
        return self.kline["Volume"].sum()

    def get_open_time_24h(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span > ms_in_24h:
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            return self.kline.index[prev_24h_index]
        return self.kline.index[0]

    def get_close_time_24h(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span > ms_in_24h:
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            return self.kline["CloseTime"].iloc[prev_24h_index]
        return self.kline["CloseTime"].iloc[0]

    def get_open_24h(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span > ms_in_24h:
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            return self.kline["Open"].iloc[prev_24h_index]
        return self.kline["Open"].iloc[0]

    def get_high_24h(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span > ms_in_24h:
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            return self.kline["High"].iloc[prev_24h_index:].max()
        return self.kline["High"].max()

    def get_low_24h(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span > ms_in_24h:
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            return self.kline["Low"].iloc[prev_24h_index:].min()
        return self.kline["Low"].min()

    def get_trade_num_24h(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span > ms_in_24h:
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            return self.kline["NumberOfTrades"].iloc[prev_24h_index:].sum()
        return self.kline["NumberOfTrades"].sum()

    def _update_buy_order(
        self,
        buy_order: bytes,
        trade_amount: Decimal,
        buy_price: Decimal,
        buy_public: bytes,
    ):
        _, amount, _, nonce, _ = _parse_transaction(buy_order)
        with self.order_book_lock:
            if self.zex.amounts[buy_order] > trade_amount:
                self.bids_order_book[buy_price] -= trade_amount
                self._order_book_updates["bids"][buy_price] = self.bids_order_book[
                    buy_price
                ]
                self.zex.amounts[buy_order] -= trade_amount
                self.final_id += 1

                asyncio.create_task(
                    self.zex.order_callback(
                        buy_public.hex(),
                        nonce,
                        self.pair,
                        "buy",
                        trade_amount,
                        buy_price,
                        ExecutionType.TRADE,
                        "PARTIALLY_FILLED",
                        last_filled=trade_amount,
                        cumulative_filled=amount - self.zex.amounts[buy_order],
                        last_executed_price=buy_price,
                        transaction_time=int(time.time() * 1000),
                        is_on_orderbook=True,
                        is_maker=True,
                        cumulative_quote_asset_quantity=Decimal(0),  # TODO
                        last_quote_asset_quantity=Decimal(0),  # TODO
                        quote_order_quantity=Decimal(0),  # TODO
                    )
                )
            else:
                heapq.heappop(self.buy_orders)
                self._remove_from_order_book("bids", buy_price, trade_amount)
                del self.zex.amounts[buy_order]
                del self.zex.orders[buy_public][buy_order]
                self.final_id += 1
                asyncio.create_task(
                    self.zex.order_callback(
                        buy_public.hex(),
                        nonce,
                        self.pair,
                        "buy",
                        trade_amount,
                        buy_price,
                        ExecutionType.TRADE,
                        "FILLED",
                        last_filled=trade_amount,
                        cumulative_filled=amount,
                        last_executed_price=buy_price,
                        transaction_time=int(time.time() * 1000),
                        is_on_orderbook=False,
                        is_maker=True,
                        cumulative_quote_asset_quantity=Decimal(0),  # TODO
                        last_quote_asset_quantity=Decimal(0),  # TODO
                        quote_order_quantity=Decimal(0),  # TODO
                    )
                )

    def _update_sell_order(
        self,
        sell_order: bytes,
        trade_amount: Decimal,
        sell_price: Decimal,
        sell_public: bytes,
    ):
        _, amount, _, nonce, _ = _parse_transaction(sell_order)
        with self.order_book_lock:
            if self.zex.amounts[sell_order] > trade_amount:
                self.asks_order_book[sell_price] -= trade_amount
                self._order_book_updates["asks"][sell_price] = self.asks_order_book[
                    sell_price
                ]
                self.zex.amounts[sell_order] -= trade_amount
                self.final_id += 1

                asyncio.create_task(
                    self.zex.order_callback(
                        sell_public.hex(),
                        nonce,
                        self.pair,
                        "sell",
                        trade_amount,
                        sell_price,
                        ExecutionType.TRADE,
                        "PARTIALLY_FILLED",
                        last_filled=trade_amount,
                        cumulative_filled=amount - self.zex.amounts[sell_order],
                        last_executed_price=sell_price,
                        transaction_time=int(time.time() * 1000),
                        is_on_orderbook=True,
                        is_maker=True,
                        cumulative_quote_asset_quantity=Decimal(0),  # TODO
                        last_quote_asset_quantity=Decimal(0),  # TODO
                        quote_order_quantity=Decimal(0),  # TODO
                    )
                )
            else:
                heapq.heappop(self.sell_orders)
                self._remove_from_order_book("asks", sell_price, trade_amount)
                del self.zex.amounts[sell_order]
                del self.zex.orders[sell_public][sell_order]
                self.final_id += 1

                # TODO: fill market maker order completely
                asyncio.create_task(
                    self.zex.order_callback(
                        sell_public.hex(),
                        nonce,
                        self.pair,
                        "sell",
                        trade_amount,
                        sell_price,
                        ExecutionType.TRADE,
                        "FILLED",
                        last_filled=trade_amount,
                        cumulative_filled=amount,
                        last_executed_price=sell_price,
                        transaction_time=int(time.time() * 1000),
                        is_on_orderbook=False,
                        is_maker=True,
                        cumulative_quote_asset_quantity=Decimal(0),  # TODO
                        last_quote_asset_quantity=Decimal(0),  # TODO
                        quote_order_quantity=Decimal(0),  # TODO
                    )
                )

    def _remove_from_order_book(self, book_type: str, price: Decimal, amount: Decimal):
        order_book = (
            self.bids_order_book if book_type == "bids" else self.asks_order_book
        )
        if order_book[price] <= amount:
            self._order_book_updates[book_type][price] = 0
            del order_book[price]
        else:
            order_book[price] -= amount
            self._order_book_updates[book_type][price] = order_book[price]

    def _update_balances(
        self,
        buy_public: bytes,
        sell_public: bytes,
        trade_amount: Decimal,
        price: Decimal,
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
        trade_amount: Decimal,
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
