from decimal import Decimal
from struct import pack
import asyncio
import time

from eth_hash.auto import keccak
from secp256k1 import PrivateKey
import numpy as np
import pytest

from app.connection_manager import ConnectionManager
from app.models.transaction import Deposit, DepositTransaction, WithdrawTransaction
from app.zex import Market, Zex
from app.zex_types import Chain, Token, UserPublic


@pytest.fixture(scope="package")
def manager():
    return ConnectionManager()


@pytest.fixture
def zex_instance():
    # Mock callbacks
    def kline_callback(symbol, df):
        pass

    def depth_callback(symbol, data):
        pass

    def order_callback(*args):
        pass

    def deposit_callback(public, chain, token, amount):
        pass

    def withdraw_callback(public, chain, token, amount):
        pass

    zex = Zex(
        kline_callback,
        depth_callback,
        order_callback,
        deposit_callback,
        withdraw_callback,
        state_dest="test_state.bin",
        light_node=False,
        benchmark_mode=False,
    )
    return zex


@pytest.fixture
def market_instance(zex_instance):
    base_token = "BTC"
    quote_token = "USDT"
    market = Market(base_token, quote_token, zex_instance)
    return market


@pytest.fixture
def deposit_transaction():
    return DepositTransaction(
        version=1,
        operation="d",
        chain="POL",
        deposits=[
            Deposit(
                tx_hash="tx_hash_1",
                chain="POL",
                token_contract="0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
                amount=Decimal("100"),
                decimal=6,
                time=1234567890,
                user_id=3,
                vout=0,
            ),
        ],
    )


@pytest.fixture
def withdraw_transaction(private1: PrivateKey):
    pubkey1 = private1.pubkey.serialize()
    return WithdrawTransaction(
        version=1,
        operation="w",
        destination="0x90ab0764297b9add0d96e36eee8e917b54faa770",
        time=1234567890,
        signature="signature",
        raw_tx="raw_tx",
        public=pubkey1,
        chain="POL",
        token_name="USDT",
        amount=Decimal("50"),
        nonce=0,
    )


version = pack(">B", 1)
BTC_DEPOSIT, DEPOSIT, WITHDRAW, BUY, SELL, CANCEL, REGISTER = b"xdwbscr"


def create_order(
    pair: str,
    side: str,
    price: float | int,
    volume: float,
    nonce: int,
    privkey: PrivateKey,
):
    pubkey = privkey.pubkey.serialize()
    base_token, quote_token = pair.split("-")
    pair = pair.replace("-", "")
    tx = (
        version
        + pack(">B", BUY if side == "buy" else SELL)
        + pack(">B", len(base_token))
        + pack(">B", len(quote_token))
        + pair.replace("-", "").encode()
        + pack(">d", volume)
        + pack(">d", price)
    )

    name = tx[1]
    t = int(time.time())
    tx += pack(">II", t, nonce) + pubkey
    msg = "v: 1\n"
    msg += f'name: {"buy" if name == BUY else "sell"}\n'
    msg += f"base token: {base_token}\n"
    msg += f"quote token: {quote_token}\n"
    msg += f'amount: {np.format_float_positional(volume, trim="0")}\n'
    msg += f'price: {np.format_float_positional(price, trim="0")}\n'
    msg += f"t: {t}\n"
    msg += f"nonce: {nonce}\n"
    msg += f"public: {pubkey.hex()}\n"
    msg = "\x19Ethereum Signed Message:\n" + str(len(msg)) + msg
    sig = privkey.ecdsa_sign(keccak(msg.encode("ascii")), raw=True)
    sig = privkey.ecdsa_serialize_compact(sig)
    tx += sig

    return tx


@pytest.fixture
def private1():
    return PrivateKey(
        int.from_bytes(
            bytearray.fromhex(
                "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf000001"
            ),
            byteorder="big",
        ).to_bytes(32, "big"),
        raw=True,
    )


@pytest.fixture
def private2():
    return PrivateKey(
        int.from_bytes(
            bytearray.fromhex(
                "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf000002"
            ),
            byteorder="big",
        ).to_bytes(32, "big"),
        raw=True,
    )


@pytest.fixture
def sell_btc_transaction(private1):
    return create_order(
        pair="BTC-USDT",
        side="sell",
        price=95000,
        volume=0.001,
        nonce=0,
        privkey=private1,
    )


@pytest.fixture
def buy_btc_transaction(private2):
    return create_order(
        pair="BTC-USDT",
        side="buy",
        price=95000,
        volume=0.001,
        nonce=0,
        privkey=private2,
    )


@pytest.mark.asyncio
async def test_deposit(zex_instance: Zex, private1: PrivateKey, deposit_transaction):
    # Register a user
    pubkey1 = private1.pubkey.serialize()
    zex_instance.register_pub(pubkey1)

    # Perform deposit
    zex_instance.deposit(deposit_transaction)

    # Allow the event loop to process the callback
    await asyncio.sleep(0.1)

    # Assertions
    assert zex_instance.state_manager.assets["USDT"][pubkey1] == Decimal("100")
    assert zex_instance.state_manager.chain_states["POL"].balances[
        "0xc2132D05D31c914a87C6611C10748AEb04B58e8F"
    ] == Decimal("6100")
    assert len(zex_instance.state_manager.user_deposits[pubkey1]) == 1


@pytest.mark.asyncio
async def test_withdraw(zex_instance: Zex, private1: PrivateKey, withdraw_transaction):
    pubkey1 = private1.pubkey.serialize()
    # Register a user and set initial balance
    zex_instance.register_pub(pubkey1)
    zex_instance.state_manager.assets["USDT"][pubkey1] = Decimal("100")
    zex_instance.state_manager.chain_states["POL"].balances[
        "0xc2132D05D31c914a87C6611C10748AEb04B58e8F"
    ] = Decimal("100")

    # Perform withdraw
    zex_instance.withdraw(withdraw_transaction)

    # Allow the event loop to process the callback
    await asyncio.sleep(0.1)

    # Assertions
    assert zex_instance.state_manager.assets["USDT"][pubkey1] == Decimal("50")
    assert zex_instance.state_manager.chain_states["POL"].balances[
        "0xc2132D05D31c914a87C6611C10748AEb04B58e8F"
    ] == Decimal("50")
    assert (
        len(zex_instance.state_manager.chain_states["POL"].user_withdraws[pubkey1]) == 1
    )


@pytest.mark.asyncio
async def test_cancel(
    market_instance: Market,
    private2: PrivateKey,
    buy_btc_transaction,
    zex_instance: Zex,
):
    pubkey2 = private2.pubkey.serialize()
    # Register a user and place an order
    zex_instance.register_pub(pubkey2)
    market_instance.place(buy_btc_transaction)

    # Cancel the order
    success = market_instance.cancel(buy_btc_transaction)

    # Assertions
    assert success
    assert buy_btc_transaction not in zex_instance.orders[pubkey2]
    assert len(market_instance.buy_orders) == 0


@pytest.mark.asyncio
async def test_match_instantly(
    market_instance: Market,
    private1: PrivateKey,
    sell_btc_transaction,
    private2: PrivateKey,
    buy_btc_transaction,
    zex_instance: Zex,
):
    pubkey1 = private1.pubkey.serialize()
    pubkey2 = private2.pubkey.serialize()
    # Register users and set initial balances
    zex_instance.register_pub(pubkey1)
    zex_instance.register_pub(pubkey2)
    zex_instance.state_manager.assets["BTC"][pubkey1] = Decimal("0.01")
    zex_instance.state_manager.assets["USDT"][pubkey2] = Decimal("10000")

    # Place a sell order
    market_instance.place(sell_btc_transaction)

    # Place a buy order that matches instantly
    matched = market_instance.match_instantly(buy_btc_transaction, 1234567890)

    # Assertions
    assert matched
    assert zex_instance.state_manager.assets["BTC"][pubkey1] == Decimal("0")
    assert zex_instance.state_manager.assets["USDT"][pubkey2] == Decimal("9000")


@pytest.mark.asyncio
async def test_place(
    market_instance: Market,
    private2: PrivateKey,
    buy_btc_transaction,
    zex_instance: Zex,
):
    pubkey2 = private2.pubkey.serialize()
    # Register a user and set initial balance
    zex_instance.register_pub(pubkey2)
    zex_instance.state_manager.assets["USDT"][pubkey2] = Decimal("10000")

    # Place a buy order
    success = market_instance.place(buy_btc_transaction)

    # Assertions
    assert success
    assert buy_btc_transaction in zex_instance.orders[pubkey2]
    assert len(market_instance.buy_orders) == 1
    assert zex_instance.state_manager.assets["USDT"][pubkey2] == Decimal("9000")
