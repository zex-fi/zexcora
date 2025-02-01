from collections.abc import Generator
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


def test_empty_instance_state(zex_instance: Zex):
    assert len(zex_instance.state_manager.chain_states) == 0
    assert len(zex_instance.state_manager.assets) == 1
    assert len(zex_instance.state_manager.user_deposits) == 0
    assert len(zex_instance.state_manager.markets) == 0


def test_register(zex_instance: Zex, client_private1: PrivateKey):
    assert zex_instance.last_user_id == 0
    public = client_private1.pubkey.serialize()
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
    zex_instance: Zex, client_private1: PrivateKey
):
    public = client_private1.pubkey.serialize()
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


@pytest.mark.asyncio(loop_scope="function")
async def test_buy_limit_order_for_not_registered_user(
    zex_instance: Zex, client_private1: PrivateKey
):
    order = create_order(
        "zEIGEN-zUSDT",
        "buy",
        3.21,
        1.2,
        0,
        client_private1,
    )
    zex_instance.process([order], 0)
    test_empty_instance_state(zex_instance)


@pytest.mark.asyncio(loop_scope="function")
async def test_sell_limit_order_for_not_registered_user(
    zex_instance: Zex, client_private1: PrivateKey
):
    order = create_order(
        "zEIGEN-zUSDT",
        "sell",
        3.21,
        1.2,
        0,
        client_private1,
    )
    zex_instance.process([order], 0)
    test_empty_instance_state(zex_instance)


@pytest.mark.asyncio(loop_scope="function")
async def test_not_enough_balance_buy_limit_order_for_registered_user(
    zex_instance: Zex, client_private1: PrivateKey
):
    public = client_private1.pubkey.serialize()
    zex_instance.register_pub(public)

    deposit_zEIGEN = Deposit(
        tx_hash="0x001",
        chain="HOL",
        token_contract="0x219f1708400bE5b8cC47A56ed2f18536F5Da7EF4",
        amount=10.0,
        decimal=18,
        time=int(time.time()),
        user_id=1,
        vout=0,
    )

    deposit_zUSDT = Deposit(
        tx_hash="0x002",
        chain="HOL",
        token_contract="0x325CCd77e71Ac296892ed5C63bA428700ec0f868",
        amount=100.0,
        decimal=6,
        time=int(time.time()),
        user_id=1,
        vout=0,
    )

    zex_instance.deposit(create_deposit_tx("HOL", [deposit_zEIGEN, deposit_zUSDT]))
    order = create_order(
        "zEIGEN-zUSDT",
        "buy",
        3.21,
        1.5,  # deposit 1 zUSDT and buy 1.5*3.21
        0,
        client_private1,
    )
    zex_instance.process([order], 0)

    assert len(zex_instance.state_manager.chain_states) == 1
    assert len(zex_instance.state_manager.assets) == 2
    assert len(zex_instance.state_manager.user_deposits) == 1
    assert public in zex_instance.state_manager.user_deposits

    assert zex_instance.state_manager.user_deposits[public][0] == deposit_zEIGEN
    assert zex_instance.state_manager.user_deposits[public][1] == deposit_zUSDT

    assert len(zex_instance.state_manager.markets) == 1


@pytest.mark.asyncio(loop_scope="function")
async def test_not_enough_balance_market_buy_order_for_registered_user(
    zex_instance: Zex,
    client_private1: PrivateKey,
    client_private2: PrivateKey,
):
    public1 = client_private1.pubkey.serialize()
    public2 = client_private2.pubkey.serialize()

    zex_instance.register_pub(public1)
    zex_instance.register_pub(public2)

    deposit_zEIGEN = Deposit(
        tx_hash="0x001",
        chain="HOL",
        token_contract="0x219f1708400bE5b8cC47A56ed2f18536F5Da7EF4",
        amount=10.0,
        decimal=18,
        time=int(time.time()),
        user_id=1,
        vout=0,
    )

    deposit_zUSDT = Deposit(
        tx_hash="0x002",
        chain="HOL",
        token_contract="0x325CCd77e71Ac296892ed5C63bA428700ec0f868",
        amount=100.0,
        decimal=6,
        time=int(time.time()),
        user_id=2,
        vout=0,
    )

    zex_instance.deposit(create_deposit_tx("HOL", [deposit_zUSDT, deposit_zEIGEN]))
    limit_order = create_order(
        "zEIGEN-zUSDT",
        "sell",
        3.21,
        5,
        0,
        client_private1,
    )
    market_order = create_order(
        "zEIGEN-zUSDT",
        "buy",
        3.21,
        5,
        0,
        client_private2,
    )
    zex_instance.process([limit_order, market_order], 0)

    assert len(zex_instance.state_manager.chain_states) == 1
    assert len(zex_instance.state_manager.assets) == 2
    assert len(zex_instance.state_manager.user_deposits) == 2
    assert public1 in zex_instance.state_manager.user_deposits
    assert public2 in zex_instance.state_manager.user_deposits

    assert zex_instance.state_manager.user_deposits[public1][0] == deposit_zEIGEN
    assert zex_instance.state_manager.user_deposits[public2][0] == deposit_zUSDT

    assets = zex_instance.state_manager.assets
    assert assets["zUSDT"][public1] == Decimal("5") * Decimal("3.21")
    assert assets["zEIGEN"][public1] == Decimal("10") - Decimal("5")

    assert assets["zUSDT"][public2] == Decimal("100") - Decimal("5") * Decimal("3.21")
    assert assets["zEIGEN"][public2] == Decimal("5")

    assert len(zex_instance.state_manager.markets) == 1
    assert "zEIGEN-zUSDT" in zex_instance.state_manager.markets


@pytest.mark.asyncio(loop_scope="function")
async def test_not_enough_balance_sell_limit_order_for_registered_user(
    zex_instance: Zex, client_private1: PrivateKey
):
    public = client_private1.pubkey.serialize()
    zex_instance.register_pub(public)

    # Deposit zEIGEN
    deposit = Deposit(
        tx_hash="0x001",
        chain="HOL",
        token_contract="0x219f1708400bE5b8cC47A56ed2f18536F5Da7EF4",
        amount=1.0,
        decimal=18,
        time=int(time.time()),
        user_id=1,
        vout=0,
    )

    zex_instance.deposit(create_deposit_tx("HOL", [deposit]))
    order = create_order(
        "zEIGEN-zUSDT",
        "sell",
        3.21,
        1.5,  # deposit 1 zEIGEN and sell 1.5
        0,
        client_private1,
    )
    zex_instance.process([order], 0)


@pytest.mark.asyncio(loop_scope="function")
async def test_not_enough_balance_market_sell_order_for_registered_user(
    zex_instance: Zex,
    client_private1: PrivateKey,
    client_private2: PrivateKey,
):
    public1 = client_private1.pubkey.serialize()
    public2 = client_private2.pubkey.serialize()

    zex_instance.register_pub(public1)
    zex_instance.register_pub(public2)

    deposit_zUSDT = Deposit(
        tx_hash="0x001",
        chain="HOL",
        token_contract="0x325CCd77e71Ac296892ed5C63bA428700ec0f868",
        amount=100.0,
        decimal=6,
        time=int(time.time()),
        user_id=1,
        vout=0,
    )
    deposit_zEIGEN = Deposit(
        tx_hash="0x002",
        chain="HOL",
        token_contract="0x219f1708400bE5b8cC47A56ed2f18536F5Da7EF4",
        amount=10.0,
        decimal=18,
        time=int(time.time()),
        user_id=2,
        vout=0,
    )

    zex_instance.deposit(create_deposit_tx("HOL", [deposit_zUSDT, deposit_zEIGEN]))
    limit_order = create_order(
        "zEIGEN-zUSDT",
        "buy",
        3.21,
        5,
        0,
        client_private1,
    )
    market_order = create_order(
        "zEIGEN-zUSDT",
        "sell",
        3.21,
        5,
        0,
        client_private2,
    )
    zex_instance.process([limit_order, market_order], 0)

    assert len(zex_instance.state_manager.chain_states) == 1
    assert len(zex_instance.state_manager.assets) == 2
    assert len(zex_instance.state_manager.user_deposits) == 2
    assert public1 in zex_instance.state_manager.user_deposits
    assert public2 in zex_instance.state_manager.user_deposits

    assert zex_instance.state_manager.user_deposits[public1][0] == deposit_zUSDT
    assert zex_instance.state_manager.user_deposits[public2][0] == deposit_zEIGEN

    assets = zex_instance.state_manager.assets
    assert assets["zUSDT"][public1] == Decimal("100") - Decimal("5") * Decimal("3.21")
    assert assets["zEIGEN"][public1] == Decimal("5")

    assert assets["zUSDT"][public2] == Decimal("5") * Decimal("3.21")
    assert assets["zEIGEN"][public2] == Decimal("10") - Decimal("5")

    assert len(zex_instance.state_manager.markets) == 1
    assert "zEIGEN-zUSDT" in zex_instance.state_manager.markets


def test_save_state(zex_instance: Zex):
    pass


def test_load_state(zex_instance: Zex):
    pass
