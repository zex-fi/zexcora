from collections import deque
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

from eth_utils.address import to_checksum_address
from loguru import logger
import httpx
import pandas as pd

from .callbacks import (
    depth_event,
    kline_event,
    user_deposit_event,
    user_order_event,
    user_withdraw_event,
)
from .chain import ChainState
from .config import settings
from .event_manager import SnapshotManager
from .kline_manager import KlineManager
from .models.transaction import (
    Deposit,
    DepositTransaction,
    WithdrawTransaction,
)
from .proto import zex_pb2
from .singleton import SingletonMeta
from .zex_types import ExecutionType, Order, UserPublic

BTC_DEPOSIT, DEPOSIT, WITHDRAW, BUY, SELL, CANCEL, REGISTER = b"xdwbscr"
TRADES_TTL = 1000


def get_token_name(chain, address):
    """Get the token name for a given chain and contract address."""
    for verified_name, tokens in settings.zex.verified_tokens.items():
        if chain not in tokens:
            continue
        if tokens[chain].contract_address == address:
            return verified_name
    return f"{chain}:{address}"


class StateManager:
    """Manages the overall state of the Zex exchange."""

    def __init__(self):
        self.chain_states: dict[str, ChainState] = {}
        self.assets: dict[str, dict[bytes, Decimal]] = {
            settings.zex.usdt_mainnet: {}
        }  # token -> {public_key -> amount}
        self.user_deposits: dict[bytes, list[Deposit]] = {}
        self.markets: dict[str, Market] = {}

    def ensure_chain_initialized(self, chain: str) -> ChainState:
        """Ensures a chain's state is initialized."""
        if chain not in self.chain_states:
            self.chain_states[chain] = ChainState.create_empty()
        return self.chain_states[chain]

    def ensure_token_initialized(self, token: str, public: bytes):
        """Ensures a token's state is initialized."""
        if token not in self.assets:
            self.assets[token] = {}
        if public not in self.assets[token]:
            self.assets[token][public] = Decimal("0")

    def ensure_market_initialized(
        self, token_name: str, quote_token: str, zex_instance
    ):
        """Ensures a market is initialized."""
        if token_name == quote_token:
            logger.error("base token and quote token can not be the same")
            return None

        pair = f"{token_name}-{quote_token}"
        if pair not in self.markets:
            self.markets[pair] = Market(token_name, quote_token, zex_instance)
        return self.markets[pair]

    def to_protobuf(self, pb_state: zex_pb2.ZexState):
        """Serialize state manager to protobuf."""
        # Serialize chain states
        for chain, chain_state in self.chain_states.items():
            chain_state.to_protobuf(chain, pb_state)

        # Serialize user deposits
        for public, deposits in self.user_deposits.items():
            entry = pb_state.user_deposits.add()
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

        # Serialize assets (balances)
        for token, balances in self.assets.items():
            pb_balance = pb_state.balances[token]
            for public, amount in balances.items():
                entry = pb_balance.balances.add()
                entry.public_key = public
                entry.amount = str(amount)

        # Serialize markets
        for pair, market in self.markets.items():
            pb_market = pb_state.markets[pair]
            pb_market.base_token = market.base_token
            pb_market.quote_token = market.quote_token

            # Serialize order books
            for order in market.buy_orders:
                pb_order = pb_market.buy_orders.add()
                pb_order.price = str(-order[0])  # Negate price for buy orders
                pb_order.tx = order[1][0]
            for order in market.sell_orders:
                pb_order = pb_market.sell_orders.add()
                pb_order.price = str(order[0])
                pb_order.tx = order[1][0]

            # Serialize order book state
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

            # Serialize kline data
            buffer = BytesIO()
            market.kline_manager.kline.to_pickle(buffer)
            pb_market.kline = buffer.getvalue()

    @classmethod
    def from_protobuf(cls, pb_state: zex_pb2.ZexState, zex_instance: "Zex"):
        """Deserialize state manager from protobuf and sets self as Zex's state manager"""
        state_manager = cls()
        zex_instance.state_manager = state_manager

        # Deserialize chain states
        for chain in pb_state.deposits.keys():
            state_manager.chain_states[chain] = ChainState.from_protobuf(
                chain, pb_state
            )

        # Deserialize user deposits
        state_manager.user_deposits = {
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

        # Deserialize assets (balances)
        state_manager.assets = {
            token: {e.public_key: Decimal(e.amount) for e in pb_balance.balances}
            for token, pb_balance in pb_state.balances.items()
        }

        for pair, pb_market in pb_state.markets.items():
            market = Market(pb_market.base_token, pb_market.quote_token, zex_instance)
            market.buy_orders = [
                (-Decimal(o.price), (o.tx, *_parse_transaction_nonce_and_amount(o.tx)))
                for o in pb_market.buy_orders
            ]
            market.sell_orders = [
                (Decimal(o.price), (o.tx, *_parse_transaction_nonce_and_amount(o.tx)))
                for o in pb_market.sell_orders
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
            market.kline_manager.kline = pd.read_pickle(BytesIO(pb_market.kline))
            state_manager.markets[pair] = market

        # Update chain balances from assets
        for token, balances in state_manager.assets.items():
            if ":" in token:  # Non-verified token
                chain, contract = token.split(":")
                if chain in state_manager.chain_states:
                    state_manager.chain_states[chain].balances[contract] = sum(
                        balances.values()
                    )
            else:  # Verified token
                for chain, token_info in settings.zex.verified_tokens.get(
                    token, {}
                ).items():
                    if chain in state_manager.chain_states:
                        state_manager.chain_states[chain].balances[
                            token_info.contract_address
                        ] = sum(balances.values())


class Zex(metaclass=SingletonMeta):
    """Core exchange class handling deposits, withdrawals, and order matching."""

    @classmethod
    def initialize_zex(cls):
        if settings.zex.state_source == "":
            return cls(
                state_dest=settings.zex.state_dest,
                light_node=settings.zex.light_node,
            )
        try:
            response = httpx.get(settings.zex.state_source)
            if response.status_code != 200 or len(response.content) == 0:
                return cls(
                    state_dest=settings.zex.state_dest,
                    light_node=settings.zex.light_node,
                )
        except httpx.ConnectError:
            return cls(
                state_dest=settings.zex.state_dest,
                light_node=settings.zex.light_node,
            )

        data = BytesIO(response.content)
        return cls.load_state(
            data=data,
            state_dest=settings.zex.state_dest,
            light_node=settings.zex.light_node,
        )

    @classmethod
    def load_state(
        cls,
        data: IO[bytes],
        state_dest: str,
        light_node: bool,
    ):
        pb_state = zex_pb2.ZexState()
        pb_state.ParseFromString(data.read())
        return cls.from_protobuf(
            pb_state,
            state_dest,
            light_node,
        )

    @classmethod
    def from_protobuf(
        cls,
        pb_state: zex_pb2.ZexState,
        state_dest: str,
        light_node: bool,
    ):
        zex = cls(
            state_dest,
            light_node,
        )
        zex.last_tx_index = pb_state.last_tx_index

        StateManager.from_protobuf(pb_state, zex)

        # Deserialize state components
        zex._deserialize_amounts(pb_state)
        zex._deserialize_trades(pb_state)
        zex._deserialize_orders(pb_state)
        zex._deserialize_nonces(pb_state)
        zex._deserialize_user_lookups(pb_state)

        # Deserialize user lookups
        zex.public_to_id_lookup = {
            entry.public_key: entry.user_id for entry in pb_state.public_to_id_lookup
        }
        zex.id_to_public_lookup = dict(pb_state.id_to_public_lookup)

        # Set last user ID
        zex.last_user_id = (
            max(zex.public_to_id_lookup.values()) if zex.public_to_id_lookup else 0
        )

        return zex

    def __init__(
        self,
        state_dest: str,
        light_node: bool = False,
        benchmark_mode=False,
    ):
        """Initialize the Zex exchange."""
        self.state_manager = StateManager()
        self.snapshot_manager = SnapshotManager()
        self.client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=5)
        )
        self.event_batch = []

        self._initialize_context()
        self._initialize_callbacks()
        self._initialize_state(state_dest, light_node, benchmark_mode)
        self._add_dummy_data_if_enabled()

    @staticmethod
    def _initialize_context():
        """Set up the Decimal context to trap floating-point operations."""
        c = getcontext()
        c.traps[FloatOperation] = True

    def _initialize_callbacks(
        self,
    ):
        """Initialize callback functions."""
        self.kline_callback = kline_event
        self.order_book_diff_callback = depth_event
        self.order_callback = user_order_event
        self.deposit_callback = user_deposit_event
        self.withdraw_callback = user_withdraw_event

    def _initialize_state(self, state_dest, light_node, benchmark_mode):
        """Initialize the exchange state."""
        self.state_dest = state_dest
        self.light_node = light_node

        # save state every N transactions
        self.save_frequency = settings.zex.state_save_frequency

        self.benchmark_mode = benchmark_mode

        self.last_tx_index = 0
        self.saved_state_index = 0
        self.save_state_tx_index_threshold = self.save_frequency
        self.amounts: dict[Order, Decimal] = {}
        self.trades: dict[UserPublic, deque] = {}
        self.orders: dict[UserPublic, set[bytes]] = {}
        self.public_to_id_lookup: dict[UserPublic, int] = {}
        self.id_to_public_lookup: dict[int, UserPublic] = {}

        self.nonces: dict[bytes, int] = {}
        self.pair_lookup: dict[str, tuple[str, str, str]] = {}

        self.last_user_id_lock = Lock()
        self.last_user_id = 0

    def _add_dummy_data_if_enabled(self):
        """Initialize test mode if enabled."""
        if settings.zex.dummy.fill_dummy:
            self._add_dummy_data()

    def _add_dummy_data(self):
        """Initialize test mode with predefined data."""
        from secp256k1 import PrivateKey

        client_priv = PrivateKey(
            bytes(bytearray.fromhex(settings.zex.dummy.client_private)), raw=True
        )
        client_pub = client_priv.pubkey.serialize()
        self.register_pub(client_pub)

        private_seed_int = int.from_bytes(
            bytearray.fromhex(settings.zex.dummy.bot_private_seed), byteorder="big"
        )

        tokens = {c: [] for c in settings.zex.chains}
        for _, token_details in settings.zex.verified_tokens.items():
            for chain, details in token_details.items():
                tokens[chain].append((details.contract_address, details.decimal))

        for i in range(20):
            bot_private_key = (private_seed_int + i).to_bytes(32, "big")
            bot_priv = PrivateKey(bot_private_key, raw=True)
            bot_pub = bot_priv.pubkey.serialize()
            self.register_pub(bot_pub)

            for idx1, (chain, details) in enumerate(tokens.items()):
                for idx2, (contract_address, decimal) in enumerate(details):
                    tx = DepositTransaction(
                        version=1,
                        operation="d",
                        chain=chain,
                        deposits=[
                            Deposit(
                                tx_hash=f"0x0{idx1}{idx2}{self.public_to_id_lookup[client_pub]}",
                                chain=chain,
                                token_contract=contract_address,
                                amount=Decimal("1_000"),
                                decimal=decimal,
                                time=self.public_to_id_lookup[client_pub],
                                user_id=self.public_to_id_lookup[client_pub],
                                vout=0,
                            ),
                            Deposit(
                                tx_hash=f"0x0{idx1}{idx2}{self.public_to_id_lookup[bot_pub]}",
                                chain=chain,
                                token_contract=contract_address,
                                amount=Decimal("100_000_000"),
                                decimal=decimal,
                                time=self.public_to_id_lookup[bot_pub],
                                user_id=self.public_to_id_lookup[bot_pub],
                                vout=0,
                            ),
                        ],
                    )

                    for deposit in tx.deposits:
                        if not self.validate_deposit(deposit):
                            continue

                        public = self.id_to_public_lookup[deposit.user_id]
                        self.process_deposit(deposit, public)

                        # Initialize related state if needed
                        if public not in self.trades:
                            self.trades[public] = deque()
                        if public not in self.orders:
                            self.orders[public] = set()
                        if public not in self.nonces:
                            self.nonces[public] = 0

                        if deposit.token_name != settings.zex.usdt_mainnet:
                            # Ensure market exists
                            self.state_manager.ensure_market_initialized(
                                deposit.token_name, settings.zex.usdt_mainnet, self
                            )

    def to_protobuf(self) -> zex_pb2.ZexState:
        state = zex_pb2.ZexState()
        state.last_tx_index = self.last_tx_index

        # Serialize state manager
        self.state_manager.to_protobuf(state)

        self._serialize_amounts(state)
        self._serialize_trades(state)
        self._serialize_orders(state)
        self._serialize_nonces(state)
        self._serialize_user_lookups(state)

        # Serialize user lookups
        for public, user_id in self.public_to_id_lookup.items():
            entry = state.public_to_id_lookup.add()
            entry.public_key = public
            entry.user_id = user_id
        state.id_to_public_lookup.update(self.id_to_public_lookup)

        return state

    def _serialize_amounts(self, state: zex_pb2.ZexState):
        """Serialize transaction amounts to protobuf."""
        for tx, amount in self.amounts.items():
            entry = state.amounts.add()
            entry.tx = tx
            entry.amount = str(amount)

    def _serialize_trades(self, state: zex_pb2.ZexState):
        """Serialize user trades to protobuf."""
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

    def _serialize_orders(self, state: zex_pb2.ZexState):
        """Serialize user orders to protobuf."""
        for public, orders in self.orders.items():
            entry = state.orders.add()
            entry.public_key = public
            entry.orders.extend(orders)

    def _serialize_nonces(self, state: zex_pb2.ZexState):
        """Serialize user nonces to protobuf."""
        for public, nonce in self.nonces.items():
            entry = state.nonces.add()
            entry.public_key = public
            entry.nonce = nonce

    def _serialize_user_lookups(self, state: zex_pb2.ZexState):
        """Serialize user ID lookups to protobuf."""
        for public, user_id in self.public_to_id_lookup.items():
            entry = state.public_to_id_lookup.add()
            entry.public_key = public
            entry.user_id = user_id
        state.id_to_public_lookup.update(self.id_to_public_lookup)

    def _deserialize_amounts(self, pb_state: zex_pb2.ZexState):
        """Deserialize transaction amounts from protobuf."""
        self.amounts = {e.tx: Decimal(e.amount) for e in pb_state.amounts}

    def _deserialize_trades(self, pb_state: zex_pb2.ZexState):
        """Deserialize user trades from protobuf."""
        self.trades = {
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

    def _deserialize_orders(self, pb_state: zex_pb2.ZexState):
        """Deserialize user orders from protobuf."""
        self.orders = {e.public_key: set(e.orders) for e in pb_state.orders}

    def _deserialize_nonces(self, pb_state: zex_pb2.ZexState):
        """Deserialize user nonces from protobuf."""
        self.nonces = {e.public_key: e.nonce for e in pb_state.nonces}

    def _deserialize_user_lookups(self, pb_state: zex_pb2.ZexState):
        """Deserialize user ID lookups from protobuf."""
        self.public_to_id_lookup = {
            entry.public_key: entry.user_id for entry in pb_state.public_to_id_lookup
        }
        self.id_to_public_lookup = dict(pb_state.id_to_public_lookup)

    def save_state(self):
        state = self.to_protobuf()
        with open(self.state_dest, "wb") as f:
            f.write(state.SerializeToString())

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
                operation, base_token, quote_token, amount, price, nonce, public = (
                    _parse_transaction(tx)
                )
                pair = f"{base_token}-{quote_token}"

                if public not in self.public_to_id_lookup:
                    logger.debug(
                        "public: {public} not registered",
                        public=public,
                    )

                # This to make sure the log for both missing token is generated
                missing_token = False
                if base_token not in self.state_manager.assets:
                    missing_token = True
                    logger.error(
                        f"can not place order for pair: {pair} since base_token: {base_token} not does not exist"
                    )
                if quote_token not in self.state_manager.assets:
                    missing_token = True
                    logger.error(
                        f"can not place order for pair: {pair} since quote_token: {quote_token} not does not exist"
                    )
                if missing_token:
                    continue

                if not self.validate_nonce(public, nonce):
                    continue

                market = self.state_manager.ensure_market_initialized(
                    base_token, quote_token, self
                )

                logger.debug(
                    "executing tx base: {base_token}, quote: {quote_token}",
                    base_token=base_token,
                    quote_token=quote_token,
                )

                t = int(unix_time())

                # fast route check for instant match
                if market.match_instantly(
                    tx, t, operation, amount, price, nonce, public
                ):
                    modified_pairs.add(pair)
                    continue
                ok = market.place(tx, operation, amount, price, nonce, public)
                if not ok:
                    continue

                modified_pairs.add(pair)

            elif name == CANCEL:
                base_token, quote_token, pair = self._get_tx_pair(tx[1:])
                success = self.state_manager.markets[pair].cancel(tx)
                if success:
                    modified_pairs.add(pair)
            elif name == REGISTER:
                self.register_pub(public=tx[2:35])
            else:
                raise ValueError(f"invalid transaction name {name}")

        if not settings.zex.light_node:
            order_book_and_kline_events = []
            updates = {}
            for pair in modified_pairs:
                order_book_update = self.get_order_book_update(pair)
                kline = self._get_kline(pair)
                order_book_and_kline_events.extend(
                    [
                        x
                        for x in [
                            self.order_book_diff_callback(pair, order_book_update),
                            self.kline_callback(pair, kline),
                        ]
                        if x is not None
                    ]
                )

                updates[pair] = {}
                if len(kline) != 0:
                    updates[pair]["kline"] = kline.iloc[len(kline) - 1].to_dict()
                if len(order_book_update["b"]) != 0 or len(order_book_update["a"]) != 0:
                    updates[pair]["depth"] = {
                        "Ask": order_book_update["a"],
                        "Bid": order_book_update["b"],
                    }

            events = self.event_batch + order_book_and_kline_events

            asyncio.create_task(
                self.client.post(
                    f"{settings.zex.event_distributor}/events",
                    json=events,
                )
            )

            asyncio.create_task(
                self.client.post(
                    f"{settings.zex.state_manager}/updates",
                    json=updates,
                )
            )

            self.event_batch = []

        self.last_tx_index = last_tx_index

        if self.saved_state_index + self.save_frequency < self.last_tx_index:
            self.saved_state_index = self.last_tx_index
            self.save_state()

    def validate_deposit(self, deposit: Deposit) -> bool:
        """Validates a deposit transaction."""
        if deposit.user_id < 1:
            logger.critical(
                f"invalid user id: {deposit.user_id}, tx_hash: {deposit.tx_hash}, "
                f"vout: {deposit.vout}, token_contract: {deposit.token_contract}, "
                f"amount: {deposit.amount}, decimal: {deposit.decimal}"
            )
            return False

        chain_state = self.state_manager.ensure_chain_initialized(deposit.chain)
        if (deposit.tx_hash, deposit.vout) in chain_state.deposits:
            logger.error(
                f"chain: {deposit.chain}, tx_hash: {deposit.tx_hash}, "
                f"vout: {deposit.vout} has already been deposited"
            )
            return False

        return True

    def process_deposit(self, deposit: Deposit, public: bytes):
        """Processes a validated deposit."""
        chain_state = self.state_manager.ensure_chain_initialized(deposit.chain)

        # Update contract decimals
        if deposit.token_contract not in chain_state.contract_decimals:
            chain_state.contract_decimals[deposit.token_contract] = deposit.decimal
        elif chain_state.contract_decimals[deposit.token_contract] != deposit.decimal:
            logger.warning(
                f"decimal for contract {deposit.token_contract} changed from "
                f"{chain_state.contract_decimals[deposit.token_contract]} to {deposit.decimal}"
            )
            chain_state.contract_decimals[deposit.token_contract] = deposit.decimal

        self.state_manager.ensure_token_initialized(deposit.token_name, public)
        if deposit.token_contract not in chain_state.balances:
            chain_state.balances[deposit.token_contract] = Decimal("0")

        # Record deposit
        chain_state.deposits.add((deposit.tx_hash, deposit.vout))
        if public not in self.state_manager.user_deposits:
            self.state_manager.user_deposits[public] = []
        self.state_manager.user_deposits[public].append(deposit)

        # Update balances
        self.state_manager.assets[deposit.token_name][public] += deposit.amount
        chain_state.balances[deposit.token_contract] += deposit.amount

        logger.info(
            f"deposit on chain: {deposit.chain}, token: {deposit.token_name}, "
            f"amount: {deposit.amount} for user: {public}, tx_hash: {deposit.tx_hash}, "
            f"new balance: {self.state_manager.assets[deposit.token_name][public]}"
        )

    # Modified Zex class methods to use the new managers
    def deposit(self, tx: DepositTransaction):
        """Process a deposit transaction."""

        for deposit in tx.deposits:
            if not self.validate_deposit(deposit):
                continue
            if deposit.user_id not in self.id_to_public_lookup:
                logger.critical(f"user id: {deposit.user_id} is not registered")
                continue

            public = self.id_to_public_lookup[deposit.user_id]
            self.process_deposit(deposit, public)

            # Initialize related state if needed
            if public not in self.trades:
                self.trades[public] = deque()
            if public not in self.orders:
                self.orders[public] = set()
            if public not in self.nonces:
                self.nonces[public] = 0

            if deposit.token_name != settings.zex.usdt_mainnet:
                # Ensure market exists
                self.state_manager.ensure_market_initialized(
                    deposit.token_name, settings.zex.usdt_mainnet, self
                )

            if not settings.zex.light_node:
                asyncio.create_task(
                    self.deposit_callback(
                        public.hex(), deposit.chain, deposit.token_name, deposit.amount
                    )
                )

    def is_withdrawable(self, chain, token_name, contract_address, withdraw_amount):
        if token_name not in settings.zex.verified_tokens:
            return True
        if chain not in settings.zex.verified_tokens[token_name]:
            return True

        if chain not in self.state_manager.chain_states:
            logger.error(f"chain={chain} not found")
            return False
        if contract_address not in self.state_manager.chain_states[chain].balances:
            logger.error(
                f"chain={chain}, token={token_name}, contract address={contract_address} not found"
            )
            return False
        balance = self.state_manager.chain_states[chain].balances[contract_address]
        details = settings.zex.verified_tokens[token_name]
        limit = details[chain].balance_withdraw_limit
        return withdraw_amount <= balance or balance > limit

    def validate_withdraw(
        self, tx: WithdrawTransaction
    ) -> tuple[bool, str | None, str | None]:
        """Validates a withdrawal transaction."""
        if tx.amount <= 0:
            logger.debug(f"invalid amount: {tx.amount}")
            return False, None, None

        chain_state = self.state_manager.chain_states.get(tx.chain)
        if not chain_state:
            logger.debug("chain not found")
            return False, None, None

        if chain_state.user_withdraw_nonces.get(tx.public, 0) != tx.nonce:
            logger.debug(
                f"invalid nonce: {chain_state.user_withdraw_nonces.get(tx.public, 0)} != {tx.nonce}"
            )
            return False, None, None

        # Validate token and get contract address
        token_info = settings.zex.verified_tokens.get(tx.token_name)
        if token_info:
            if tx.chain in token_info:
                token = tx.token_name
                token_contract = token_info[tx.chain].contract_address
            else:
                logger.debug(
                    f"invalid chain: {tx.chain} for withdraw of verified token: {tx.token_name}"
                )
                return False, None, None
        else:
            token = tx.token_name
            try:
                _, token_contract = tx.token_name.split(":")
                token_contract = to_checksum_address(token_contract)
            except Exception as e:
                logger.debug(f"invalid token contract address: {e}")
                return False, None, None

        return True, token, token_contract

    def check_balances(
        self, tx: WithdrawTransaction, token: str, token_contract: str
    ) -> bool:
        """Checks if balances are sufficient for withdrawal."""
        chain_state = self.state_manager.chain_states[tx.chain]

        # Check user balance
        balance = self.state_manager.assets[token].get(tx.public, Decimal("0"))
        if balance < tx.amount:
            logger.debug("balance not enough")
            return False

        # Check vault balance
        if token_contract not in chain_state.balances:
            logger.debug("token contract address not found")
            return False
        vault_balance = chain_state.balances[token_contract]
        if vault_balance < tx.amount:
            logger.error(
                f"vault balance: {vault_balance}, withdraw amount: {tx.amount}, "
                f"user balance before deduction: {balance}, vault does not have enough balance"
            )
            return False

        return True

    def process_withdraw(
        self, tx: WithdrawTransaction, token: str, token_contract: str
    ):
        """Processes a validated withdrawal."""
        chain_state = self.state_manager.chain_states[tx.chain]

        # Update balances
        self.state_manager.assets[token][tx.public] -= tx.amount
        chain_state.balances[token_contract] -= tx.amount

        # Update withdrawal records
        if tx.public not in chain_state.user_withdraws:
            chain_state.user_withdraws[tx.public] = []
        chain_state.user_withdraws[tx.public].append(tx)

        # Update nonces
        chain_state.withdraw_nonce += 1
        if tx.public not in chain_state.user_withdraw_nonces:
            chain_state.user_withdraw_nonces[tx.public] = 0
        chain_state.user_withdraw_nonces[tx.public] += 1

        chain_state.withdraws.append(tx)

        logger.info(
            f"withdraw on chain: {tx.chain}, token: {tx.token_name}, "
            f"amount: {tx.amount} for user: {tx.public}, "
            f"new balance: {self.state_manager.assets[tx.token_name][tx.public]}"
        )

    def withdraw(self, tx: WithdrawTransaction):
        """Process a withdrawal transaction."""
        # Validate withdrawal
        valid, token, token_contract = self.validate_withdraw(tx)
        if not valid:
            return

        # Check balances
        if not self.check_balances(tx, token, token_contract):
            return

        # Check if withdrawal is allowed
        if not self.is_withdrawable(tx.chain, token, token_contract, tx.amount):
            logger.debug(
                f"withdraw of token: {token}, contract: {token_contract} is disabled"
            )
            return

        # Process withdrawal
        self.process_withdraw(tx, token, token_contract)

        if not settings.zex.light_node:
            asyncio.create_task(
                self.withdraw_callback(
                    tx.public.hex(), tx.chain, tx.token_name, tx.amount
                )
            )

    def validate_nonce(self, public: bytes, nonce: int) -> bool:
        if self.nonces[public] != nonce:
            logger.debug(
                "Invalid nonce: expected {expected_nonce}, got {nonce} for user: {user_id}",
                expected_nonce=self.nonces[public],
                nonce=nonce,
                user_id=self.public_to_id_lookup[public],
            )
            return False
        self.nonces[public] += 1
        return True

    def get_order_book_update(self, pair: str):
        order_book_update = self.state_manager.markets[pair].get_order_book_update()
        now = int(unix_time() * 1000)
        return {
            "e": "depthUpdate",  # Event type
            "E": now,  # Event time
            "T": now,  # Transaction time
            "s": pair,
            "U": order_book_update["U"],
            "u": order_book_update["u"],
            "pu": order_book_update["pu"],
            "b": [
                [str(p), str(q)] for p, q in order_book_update["bids"].items()
            ],  # Bids to be updated
            "a": [
                [str(p), str(q)] for p, q in order_book_update["asks"].items()
            ],  # Asks to be updated
        }

    def get_order_book(self, pair: str, limit: int):
        if pair not in self.state_manager.markets:
            now = int(unix_time() * 1000)
            return {
                "lastUpdateId": 0,
                "E": now,  # Message output time
                "T": now,  # Transaction time
                "bids": [],
                "asks": [],
            }
        order_book = {
            "bids": deepcopy(self.state_manager.markets[pair].bids_order_book),
            "asks": deepcopy(self.state_manager.markets[pair].asks_order_book),
        }
        last_update_id = self.state_manager.markets[pair].last_update_id
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

    def _get_kline(self, pair: str) -> pd.DataFrame:
        if pair not in self.state_manager.markets:
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
        return self.state_manager.markets[pair].kline_manager.kline

    def get_kline(self, pair: str) -> pd.DataFrame:
        return self.snapshot_manager.get_kline(pair)

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
        if public not in self.state_manager.user_deposits:
            self.state_manager.user_deposits[public] = []

        if public not in self.trades:
            self.trades[public] = deque()
        if public not in self.orders:
            self.orders[public] = set()
        if public not in self.nonces:
            self.nonces[public] = 0

        logger.info(
            "user registered with public: {public}, user id: {user_id}",
            public=public.hex(),
            user_id=self.public_to_id_lookup[public],
        )


def _parse_transaction(tx: bytes) -> tuple[int, str, str, Decimal, Decimal, int, bytes]:
    operation, base_token_len, quote_token_len = struct.unpack(">x B B B", tx[:4])

    order_format = f">{base_token_len}s {quote_token_len}s d d I I 33s"
    order_format_size = struct.calcsize(order_format)
    base_token, quote_token, amount, price, t, nonce, public = struct.unpack(
        order_format, tx[4 : 4 + order_format_size]
    )
    base_token = base_token.decode("ascii")
    quote_token = quote_token.decode("ascii")

    return (
        operation,
        base_token,
        quote_token,
        Decimal(str(amount)),
        Decimal(str(price)),
        nonce,
        public,
    )


def _parse_transaction_nonce_and_amount(
    tx: bytes,
) -> tuple[Decimal, int]:
    base_token_len, quote_token_len = struct.unpack(">x x B B", tx[:4])

    order_format = f">{base_token_len + quote_token_len}x d 12x I 33x"
    order_format_size = struct.calcsize(order_format)
    amount, nonce = struct.unpack(order_format, tx[4 : 4 + order_format_size])

    return nonce, Decimal(str(amount))


class Market:
    def __init__(self, base_token: str, quote_token: str, zex: Zex):
        self.base_token = base_token
        self.quote_token = quote_token
        self.pair = f"{base_token}-{quote_token}"
        self.zex = zex

        self.buy_orders: list[tuple[Decimal, tuple[bytes, int, Decimal]]] = []
        self.sell_orders: list[tuple[Decimal, tuple[bytes, int, Decimal]]] = []
        self.bids_order_book: dict[Decimal, Decimal] = {}
        self.asks_order_book: dict[Decimal, Decimal] = {}
        self._order_book_updates: dict[str, dict[Decimal, Decimal]] = {
            "bids": {},
            "asks": {},
        }
        self.first_id = 0
        self.final_id = 0
        self.last_update_id = 0

        self.kline_manager = KlineManager(self.pair)

        self.base_token_balances = zex.state_manager.assets[base_token]
        self.quote_token_balances = zex.state_manager.assets[quote_token]

    def get_order_book_update(self):
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

    def match_instantly(
        self,
        tx: bytes,
        t: int,
        operation: int,
        amount: Decimal,
        price: Decimal,
        nonce: int,
        public: bytes,
    ) -> bool:
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
            sell_price, (sell_order, sell_order_nonce, sell_order_amount) = (
                self.sell_orders[0]
            )
            trade_amount = min(amount, self.zex.amounts[sell_order])
            if not self.zex.light_node:
                self._record_trade(tx, sell_order, trade_amount, sell_price, t)

            sell_public = sell_order[-97:-64]
            self._update_sell_order(
                sell_order,
                sell_order_nonce,
                sell_order_amount,
                sell_price,
                sell_public,
                trade_amount,
            )
            self._update_balances(public, sell_public, trade_amount, sell_price)
            self.quote_token_balances[public] -= trade_amount * sell_price
            amount -= trade_amount

        if amount > 0:
            # Add remaining amount to buy orders
            self._add_remaining_amount_to_orders(
                "bids", public, nonce, initial_amount, amount, price, tx
            )

            # TODO: send partial fill message for taker order
            if not settings.zex.light_node:
                self.zex.event_batch.append(
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
                        transaction_time=int(time.time() * 1000),
                        is_on_orderbook=True,
                        is_maker=False,
                        cumulative_quote_asset_quantity=Decimal(0),  # TODO
                        last_quote_asset_quantity=Decimal(0),  # TODO
                        quote_order_quantity=Decimal(0),  # TODO
                    )
                )

        else:
            # TODO: send completed message for taker order
            if not settings.zex.light_node:
                self.zex.event_batch.append(
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
                        transaction_time=int(time.time() * 1000),
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
            buy_price, (buy_order, buy_order_nonce, buy_order_amount) = self.buy_orders[
                0
            ]
            buy_price = -buy_price  # Negate because buy prices are stored negatively
            trade_amount = min(amount, self.zex.amounts[buy_order])
            if not self.zex.light_node:
                self._record_trade(buy_order, tx, trade_amount, buy_price, t)

            buy_public = buy_order[-97:-64]
            self._update_buy_order(
                buy_order,
                buy_order_nonce,
                buy_order_amount,
                buy_price,
                buy_public,
                trade_amount,
            )
            self._update_balances(buy_public, public, trade_amount, buy_price)
            self.base_token_balances[public] -= trade_amount

            amount -= trade_amount

        if amount > 0:
            # Add remaining amount to sell orders
            self._add_remaining_amount_to_orders(
                "asks", public, nonce, initial_amount, amount, price, tx
            )

            if not settings.zex.light_node:
                self.zex.event_batch.append(
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
                        transaction_time=int(time.time() * 1000),
                        is_on_orderbook=True,
                        is_maker=False,
                        cumulative_quote_asset_quantity=Decimal(0),  # TODO
                        last_quote_asset_quantity=Decimal(0),  # TODO
                        quote_order_quantity=Decimal(0),  # TODO
                    )
                )

        else:
            if not settings.zex.light_node:
                self.zex.event_batch.append(
                    self.zex.order_callback(
                        public=public.hex(),
                        nonce=nonce,
                        symbol=self.pair,
                        side="sell",
                        amount=initial_amount,
                        price=price,
                        execution_type=ExecutionType.TRADE,
                        order_status="FILLED",
                        last_filled=initial_amount,
                        cumulative_filled=initial_amount,
                        last_executed_price=buy_price,
                        transaction_time=int(time.time() * 1000),
                        is_on_orderbook=True,
                        is_maker=False,
                        cumulative_quote_asset_quantity=Decimal(0),  # TODO
                        last_quote_asset_quantity=Decimal(0),  # TODO
                        quote_order_quantity=Decimal(0),  # TODO
                    )
                )
        return True

    def _add_remaining_amount_to_buy_orders(
        self, public, nonce, initial_amount, remaining_amount, price: Decimal, tx
    ):
        heapq.heappush(self.buy_orders, (-price, (tx, nonce, initial_amount)))
        self.zex.amounts[tx] = remaining_amount
        self.zex.orders[public].add(tx)
        self.quote_token_balances[public] -= remaining_amount * price

        if not settings.zex.light_node:
            if price in self.bids_order_book:
                self.bids_order_book[price] += remaining_amount
            else:
                self.bids_order_book[price] = remaining_amount
            self._order_book_updates["bids"][price] = self.bids_order_book[price]

    def _add_remaining_amount_to_sell_orders(
        self, public, nonce, initial_amount, remaining_amount, price, tx
    ):
        heapq.heappush(self.sell_orders, (price, (tx, nonce, initial_amount)))
        self.zex.amounts[tx] = remaining_amount
        self.zex.orders[public].add(tx)
        self.base_token_balances[public] -= remaining_amount

        if not settings.zex.light_node:
            if price in self.asks_order_book:
                self.asks_order_book[price] += remaining_amount
            else:
                self.asks_order_book[price] = remaining_amount
            self._order_book_updates["asks"][price] = self.asks_order_book[price]

    def _add_remaining_amount_to_orders(
        self,
        order_book_side: Literal["bids", "asks"],
        public,
        nonce,
        initial_amount,
        remaining_amount,
        price,
        tx,
    ):
        match order_book_side:
            case "bids":
                self._add_remaining_amount_to_buy_orders(
                    public, nonce, initial_amount, remaining_amount, price, tx
                )
            case "asks":
                self._add_remaining_amount_to_sell_orders(
                    public, nonce, initial_amount, remaining_amount, price, tx
                )

    def _record_trade(
        self,
        buy_order: bytes,
        sell_order: bytes,
        trade_amount: Decimal,
        price: Decimal,
        t: int,
    ):
        if self.zex.light_node:
            return
        buy_public = buy_order[-97:-64]
        sell_public = sell_order[-97:-64]

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

        if not self.zex.benchmark_mode and not self.zex.light_node:
            self.kline_manager.update_kline(float(price), float(trade_amount))

        self.final_id += 1

    def place(
        self,
        tx: bytes,
        operation: int,
        amount: Decimal,
        price: Decimal,
        nonce: int,
        public: bytes,
    ) -> bool:
        if price <= 0 or amount <= 0:
            if not settings.zex.light_node:
                self.zex.event_batch.append(
                    self.zex.order_callback(
                        public=public.hex(),
                        nonce=nonce,
                        symbol=self.pair,
                        side="buy" if operation == BUY else "sell",
                        amount=amount,
                        price=price,
                        execution_type=ExecutionType.REJECTED,
                        order_status="REJECTED",
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
            heap_item = (-price, (tx, nonce, amount))

            balances_dict = self.quote_token_balances
            balance = balances_dict.get(public, Decimal("0"))

            required = amount * price
        elif operation == SELL:
            side = "sell"
            order_book_update_key = "asks"
            order_book = self.asks_order_book
            orders_heap = self.sell_orders
            heap_item = (price, (tx, nonce, amount))

            balances_dict = self.base_token_balances
            balance = balances_dict.get(public, Decimal("0"))

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

            if not settings.zex.light_node:
                self.zex.event_batch.append(
                    self.zex.order_callback(
                        public=public.hex(),
                        nonce=nonce,
                        symbol=self.pair,
                        side="buy" if operation == BUY else "sell",
                        amount=amount,
                        price=price,
                        execution_type=ExecutionType.REJECTED,
                        order_status="REJECTED",
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

        balances_dict[public] = balance - required

        self.final_id += 1
        self.zex.amounts[tx] = amount
        self.zex.orders[public].add(tx)

        if not settings.zex.light_node:
            if price in order_book:
                order_book[price] += amount
            else:
                order_book[price] = amount
            self._order_book_updates[order_book_update_key][price] = order_book[price]

            self.zex.event_batch.append(
                self.zex.order_callback(
                    public=public.hex(),
                    nonce=nonce,
                    symbol=self.pair,
                    side=side,
                    amount=amount,
                    price=price,
                    execution_type=ExecutionType.NEW,
                    order_status="NEW",
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
            operation, _, _, initial_amount, price, nonce, public = _parse_transaction(
                order
            )
            amount = self.zex.amounts.pop(order)
            self.zex.orders[public].remove(order)
            if operation == BUY:
                self.quote_token_balances[public] += amount * price
                self.buy_orders.remove((-price, (order, nonce, initial_amount)))
                heapq.heapify(self.buy_orders)
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
                self.sell_orders.remove((price, (order, nonce, initial_amount)))
                heapq.heapify(self.sell_orders)
                if amount >= self.asks_order_book[price]:
                    del self.asks_order_book[price]
                    self._order_book_updates["asks"][price] = 0
                else:
                    self.asks_order_book[price] -= amount
                    self._order_book_updates["asks"][price] = self.asks_order_book[
                        price
                    ]
            self.final_id += 1
            if not settings.zex.light_node:
                self.zex.event_batch.append(
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

    def _update_buy_order(
        self,
        buy_order: bytes,
        buy_order_nonce: int,
        buy_order_amount: Decimal,
        buy_price: Decimal,
        buy_public: bytes,
        trade_amount: Decimal,
    ):
        if self.zex.amounts[buy_order] > trade_amount:
            self.zex.amounts[buy_order] -= trade_amount
            self.final_id += 1

            if not settings.zex.light_node:
                self.bids_order_book[buy_price] -= trade_amount
                self._order_book_updates["bids"][buy_price] = self.bids_order_book[
                    buy_price
                ]
                self.zex.event_batch.append(
                    self.zex.order_callback(
                        public=buy_public.hex(),
                        nonce=buy_order_nonce,
                        symbol=self.pair,
                        side="buy",
                        amount=trade_amount,
                        price=buy_price,
                        execution_type=ExecutionType.TRADE,
                        order_status="PARTIALLY_FILLED",
                        last_filled=trade_amount,
                        cumulative_filled=buy_order_amount
                        - self.zex.amounts[buy_order],
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
            del self.zex.amounts[buy_order]
            self.zex.orders[buy_public].remove(buy_order)
            self.final_id += 1
            if not settings.zex.light_node:
                self._remove_from_order_book("bids", buy_price, trade_amount)

                self.zex.event_batch.append(
                    self.zex.order_callback(
                        public=buy_public.hex(),
                        nonce=buy_order_nonce,
                        symbol=self.pair,
                        side="buy",
                        amount=trade_amount,
                        price=buy_price,
                        execution_type=ExecutionType.TRADE,
                        order_status="FILLED",
                        last_filled=trade_amount,
                        cumulative_filled=buy_order_amount,
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
        sell_order_nonce: int,
        sell_order_amount: Decimal,
        sell_price: Decimal,
        sell_public: bytes,
        trade_amount: Decimal,
    ):
        if self.zex.amounts[sell_order] > trade_amount:
            self.zex.amounts[sell_order] -= trade_amount
            self.final_id += 1

            if not settings.zex.light_node:
                self.asks_order_book[sell_price] -= trade_amount
                self._order_book_updates["asks"][sell_price] = self.asks_order_book[
                    sell_price
                ]
                self.zex.event_batch.append(
                    self.zex.order_callback(
                        public=sell_public.hex(),
                        nonce=sell_order_nonce,
                        symbol=self.pair,
                        side="sell",
                        amount=trade_amount,
                        price=sell_price,
                        execution_type=ExecutionType.TRADE,
                        order_status="PARTIALLY_FILLED",
                        last_filled=trade_amount,
                        cumulative_filled=sell_order_amount
                        - self.zex.amounts[sell_order],
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
            del self.zex.amounts[sell_order]
            self.zex.orders[sell_public].remove(sell_order)
            self.final_id += 1

            # TODO: fill market maker order completely
            if not settings.zex.light_node:
                self._remove_from_order_book("asks", sell_price, trade_amount)

                self.zex.event_batch.append(
                    self.zex.order_callback(
                        public=sell_public.hex(),
                        nonce=sell_order_nonce,
                        symbol=self.pair,
                        side="sell",
                        amount=trade_amount,
                        price=sell_price,
                        execution_type=ExecutionType.TRADE,
                        order_status="FILLED",
                        last_filled=trade_amount,
                        cumulative_filled=sell_order_amount,
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

    def _prune_old_trades(self, public: bytes, current_time: int):
        trades = self.zex.trades[public]
        while trades and current_time - trades[0][0] > TRADES_TTL:
            trades.popleft()
