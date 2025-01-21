from decimal import Decimal
from struct import pack
import time

from eth_hash.auto import keccak
from secp256k1 import PrivateKey
import numpy as np
import pytest

from app.config import Token, settings
from app.models.transaction import Deposit, DepositTransaction, WithdrawTransaction
from app.zex import Market, Zex
from app.zex_types import Chain, UserPublic

version = pack(">B", 1)
DEPOSIT, WITHDRAW, BUY, SELL, CANCEL, REGISTER = b"dwbscr"


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


def create_deposit_tx(chain, deposits: list[Deposit]) -> DepositTransaction:
    return DepositTransaction(
        version=1,
        operation="d",
        chain=chain,
        deposits=deposits,
    )


@pytest.fixture(scope="function")
def zex_instance() -> Zex:
    # Mock callbacks
    async def kline_callback(symbol, df):
        pass

    async def depth_callback(symbol, data):
        pass

    async def order_callback(*args):
        pass

    async def deposit_callback(public, chain, token, amount):
        pass

    async def withdraw_callback(public, chain, token, amount):
        pass

    settings.zex.fill_dummy = False
    settings.zex.verified_tokens = {
        "zUSDT": {
            "HOL": Token(
                contract_address="0x325CCd77e71Ac296892ed5C63bA428700ec0f868",
                balance_withdraw_limit=Decimal("1"),
                decimal=6,
            ),
            "SEP": Token(
                contract_address="0x325CCd77e71Ac296892ed5C63bA428700ec0f868",
                balance_withdraw_limit=Decimal("1"),
                decimal=6,
            ),
            "BST": Token(
                contract_address="0x325CCd77e71Ac296892ed5C63bA428700ec0f868",
                balance_withdraw_limit=Decimal("1"),
                decimal=6,
            ),
        },
        "zEIGEN": {
            "HOL": Token(
                contract_address="0x219f1708400bE5b8cC47A56ed2f18536F5Da7EF4",
                balance_withdraw_limit=Decimal("0.01"),
                decimal=18,
            ),
            "SEP": Token(
                contract_address="0x219f1708400bE5b8cC47A56ed2f18536F5Da7EF4",
                balance_withdraw_limit=Decimal("0.01"),
                decimal=18,
            ),
            "BST": Token(
                contract_address="0x219f1708400bE5b8cC47A56ed2f18536F5Da7EF4",
                balance_withdraw_limit=Decimal("0.01"),
                decimal=18,
            ),
        },
        "zWBTC": {
            "HOL": Token(
                contract_address="0x9d84f6e4D734c33C2B6e7a5211780499A71aEf6A",
                balance_withdraw_limit=Decimal("0.00001"),
                decimal=8,
            ),
            "SEP": Token(
                contract_address="0x9d84f6e4D734c33C2B6e7a5211780499A71aEf6A",
                balance_withdraw_limit=Decimal("0.00001"),
                decimal=8,
            ),
            "BST": Token(
                contract_address="0x9d84f6e4D734c33C2B6e7a5211780499A71aEf6A",
                balance_withdraw_limit=Decimal("0.00001"),
                decimal=8,
            ),
        },
    }
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
    yield zex
    Zex.reset(Zex)


@pytest.fixture(scope="module")
def client_private():
    return PrivateKey(
        bytes.fromhex(
            "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        ),
        raw=True,
    )


def test_empty_instance_state(zex_instance: Zex):
    assert len(zex_instance.state_manager.chain_states) == 0
    assert len(zex_instance.state_manager.assets) == 1
    assert len(zex_instance.state_manager.user_deposits) == 0
    assert len(zex_instance.state_manager.markets) == 0


def test_register(zex_instance: Zex, client_private: PrivateKey):
    assert zex_instance.last_user_id == 0
    public = client_private.pubkey.serialize()
    zex_instance.register_pub(public)
    assert zex_instance.last_user_id == 1

    assert len(zex_instance.state_manager.user_deposits) == 1
    assert public in zex_instance.state_manager.user_deposits


@pytest.mark.asyncio(loop_scope="function")
async def test_deposit_for_not_registered_user(zex_instance: Zex):
    deposit = Deposit(
        tx_hash="0x001",
        chain="HOL",
        token_contract="0x325CCd77e71Ac296892ed5C63bA428700ec0f868",
        amount=100.0,
        decimal=6,
        time=int(time.time()),
        user_id=1,
        vout=0,
    )

    zex_instance.deposit(create_deposit_tx("HOL", [deposit]))

    assert len(zex_instance.public_to_id_lookup) == 0
    assert zex_instance.last_user_id == 0
    assert len(zex_instance.state_manager.chain_states) == 1
    assert len(zex_instance.state_manager.assets) == 1
    assert len(zex_instance.state_manager.user_deposits) == 0
    assert len(zex_instance.state_manager.markets) == 0


@pytest.mark.asyncio(loop_scope="function")
async def test_deposit_for_registered_user(
    zex_instance: Zex, client_private: PrivateKey
):
    public = client_private.pubkey.serialize()
    zex_instance.register_pub(public)

    deposit = Deposit(
        tx_hash="0x001",
        chain="HOL",
        token_contract="0x325CCd77e71Ac296892ed5C63bA428700ec0f868",
        amount=100.0,
        decimal=6,
        time=int(time.time()),
        user_id=1,
        vout=0,
    )

    zex_instance.deposit(create_deposit_tx("HOL", [deposit]))

    assert len(zex_instance.state_manager.chain_states) == 1
    assert len(zex_instance.state_manager.assets) == 1
    assert len(zex_instance.state_manager.user_deposits) == 1
    assert public in zex_instance.state_manager.user_deposits
    assert zex_instance.state_manager.user_deposits[public][0] == deposit
    assert len(zex_instance.state_manager.markets) == 0
