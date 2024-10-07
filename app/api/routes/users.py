from struct import unpack
import hashlib

from bitcoinutils.keys import P2trAddress, PublicKey
from bitcoinutils.utils import tweak_taproot_pubkey
from fastapi import APIRouter, HTTPException
from loguru import logger
from web3 import Web3

from app import (
    ZEX_BTC_PUBLIC_KEY,
    ZEX_MONERO_PUBLIC_ADDRESS,
    zex,
)
from app.models.response import (
    Addresses,
    BalanceResponse,
    NonceResponse,
    OrderResponse,
    TradeResponse,
    TransferResponse,
    UserAddressesResponse,
    UserIDResponse,
    UserPublicResponse,
    Withdraw,
    WithdrawNonce,
)
from app.models.transaction import Deposit, WithdrawTransaction
from app.monero.address import Address
from app.zex import BUY

from . import CHAIN_CONTRACTS, DECIMALS

router = APIRouter()
light_router = APIRouter()

USDT_MAINNET = "HOL:1"


# @timed_lru_cache(seconds=10)
def _user_balances(user: bytes) -> list[BalanceResponse]:
    result = []
    for token in zex.balances:
        if zex.balances[token].get(user, 0) == 0:
            continue

        balance = zex.balances[token][user]
        result.append(
            BalanceResponse(
                chain=token[0:3],
                token=int(token[4]),
                balance=str(balance),
            )
        )
    return result


@router.get("/user/{public}/balances")
def user_balances(public: str) -> list[BalanceResponse]:
    user = bytes.fromhex(public)
    return _user_balances(user)


@router.get("/user/{public}/trades")
def user_trades(public: str) -> list[TradeResponse]:
    user = bytes.fromhex(public)
    trades = zex.trades.get(user, [])
    resp = {}
    for time, amount, pair, name, tx in trades:
        base_asset, quote_asset = pair.split("-")
        price, nonce = unpack(">d4xI", tx[24:40])
        trade = {
            "name": "buy" if name == BUY else "sell",
            "t": time,
            "base_chain": base_asset[:3],
            "base_token": int(base_asset[4:]),
            "quote_chain": quote_asset[:3],
            "quote_token": int(quote_asset[4:]),
            "amount": amount,
            "price": price,
            "nonce": nonce,
        }
        if nonce in resp:
            resp[nonce]["amount"] += amount
        else:
            resp[nonce] = trade
    return [value for _, value in sorted(resp.items(), key=lambda x: x[0])]


@router.get("/user/{public}/orders")
def user_orders(public: str) -> list[OrderResponse]:
    user = bytes.fromhex(public)
    orders = zex.orders.get(user, {})
    resp = []
    order: bytes
    for order in orders:
        o = {
            "name": "buy" if order[1] == BUY else "sell",
            "base_chain": order[2:5].decode("ascii"),
            "base_token": unpack(">I", order[5:9])[0],
            "quote_chain": order[9:12].decode("ascii"),
            "quote_token": unpack(">I", order[12:16])[0],
            "amount": unpack(">d", order[16:24])[0],
            "price": unpack(">d", order[24:32])[0],
            "t": unpack(">I", order[32:36])[0],
            "nonce": unpack(">I", order[36:40])[0],
            "index": unpack(">Q", order[137:145])[0],
            "slice": order[1:40].hex(),
        }
        resp.append(o)
    return resp


@router.get("/user/{public}/nonce")
def user_nonce(public: str) -> NonceResponse:
    user = bytes.fromhex(public)
    return NonceResponse(nonce=zex.nonces.get(user, 0))


@router.get("/user/{public}/id")
def user_id(public: str):
    user = bytes.fromhex(public)
    if user not in zex.public_to_id_lookup:
        return HTTPException(404, {"error": "user not found"})

    user_id = zex.public_to_id_lookup[user]
    return UserIDResponse(id=user_id)


@router.get("/user/{public}/transfers")
def user_transfers(public: str) -> list[TransferResponse]:
    user = bytes.fromhex(public)
    if user not in zex.deposits:
        return []
    all_deposits = zex.deposits.get(user, []).copy()
    all_withdraws = [
        x for chain in zex.withdraws.keys() for x in zex.withdraws[chain].get(user, [])
    ]

    sorted_transfers: list[WithdrawTransaction | Deposit] = sorted(
        all_deposits + all_withdraws, key=lambda transfer: transfer.time
    )
    return [
        TransferResponse(
            token=t.token,
            amount=t.amount if isinstance(t, Deposit) else -t.amount,
            time=t.time,
        )
        for t in sorted_transfers
    ]


@router.get("/user/{id}/public")
def get_user_public(id: int) -> UserPublicResponse:
    if id not in zex.id_to_public_lookup:
        raise HTTPException(404, {"error": "user not found"})
    public = zex.id_to_public_lookup[id].hex()
    return UserPublicResponse(public=public)


def tagged_hash(data: bytes, tag: str) -> bytes:
    """
    Tagged hashes ensure that hashes used in one context can not be used in another.
    It is used extensively in Taproot

    A tagged hash is: SHA256( SHA256("TapTweak") ||
                              SHA256("TapTweak") ||
                              data
                            )
    """

    tag_digest = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(tag_digest + tag_digest + data).digest()


# to convert hashes to ints we need byteorder BIG...
def b_to_i(b: bytes) -> int:
    """Converts a bytes to a number"""
    return int.from_bytes(b, byteorder="big")


def i_to_b8(i: int) -> bytes:
    """Converts a integer to bytes"""
    return i.to_bytes(8, byteorder="big")


def calculate_tweak(pubkey: PublicKey, user_id: int) -> int:
    """
    Calculates the tweak to apply to the public and private key when required.
    """

    # only the x coordinate is tagged_hash'ed
    key_x = pubkey.to_bytes()[:32]

    tweak = tagged_hash(key_x + i_to_b8(user_id), "TapTweak")

    # we convert to int for later elliptic curve  arithmetics
    tweak_int = b_to_i(tweak)

    return tweak_int


def get_taproot_address(master_public: PublicKey, user_id: int) -> P2trAddress:
    tweak_int = calculate_tweak(master_public, user_id)
    # keep x-only coordinate
    tweak_and_odd = tweak_taproot_pubkey(master_public.key.to_string(), tweak_int)
    pubkey = tweak_and_odd[0][:32]
    is_odd = tweak_and_odd[1]

    return P2trAddress(witness_program=pubkey.hex(), is_odd=is_odd)


btc_master_pubkey = PublicKey(ZEX_BTC_PUBLIC_KEY)
monero_master_address = Address(ZEX_MONERO_PUBLIC_ADDRESS)


@router.get("/user/{public}/addresses")
def get_user_addresses(public: str) -> UserAddressesResponse:
    user = bytes.fromhex(public)
    if user not in zex.public_to_id_lookup:
        raise HTTPException(404, {"error": "user not found"})
    user_id = zex.public_to_id_lookup[user]
    taproot_address = get_taproot_address(btc_master_pubkey, user_id)
    monero_address = monero_master_address.with_payment_id(user_id)
    hol_contract_address = CHAIN_CONTRACTS["HOL"]
    bst_contract_address = CHAIN_CONTRACTS["BST"]
    sep_contract_address = CHAIN_CONTRACTS["SEP"]
    return UserAddressesResponse(
        user=user.hex(),
        addresses=Addresses(
            BTC=taproot_address.to_string(),
            XMR=str(monero_address),
            HOL=hol_contract_address,
            BST=bst_contract_address,
            SEP=sep_contract_address,
        ),
    )


@router.get("/users/latest-id")
def get_latest_user_id():
    return UserIDResponse(id=zex.last_user_id)


@router.get("/user/{public}/withdraws/{chain}/nonce")
def get_withdraw_nonce(public: str, chain: str) -> WithdrawNonce:
    user = bytes.fromhex(public)
    chain = chain.upper()
    if chain not in zex.withdraw_nonces:
        raise HTTPException(404, {"error": f"{chain} not found"})
    return WithdrawNonce(
        chain=chain,
        nonce=zex.withdraw_nonces[chain].get(user, 0),
    )


@router.get("/user/{public}/withdraws/{chain}")
def get_withdraws(public: str, chain: str) -> list[Withdraw]:
    user = bytes.fromhex(public)
    chain = chain.upper()
    if chain not in zex.withdraws:
        raise HTTPException(404, {"error": f"{chain} not found"})
    if user not in zex.withdraws[chain]:
        return []
    return [
        Withdraw(
            chain=w.chain,
            tokenID=w.token_id,
            amount=str(w.amount),
            user=str(int.from_bytes(user[1:], byteorder="big")),
            destination=w.dest,
            t=w.time,
            nonce=w.nonce,
        )
        for w in zex.withdraws[chain][user]
    ]


def user_withdraw(public: str, chain: str, nonce: int):
    if nonce < 0:
        raise HTTPException(400, {"error": "invalid nonce"})

    user = bytes.fromhex(public)

    withdraws = zex.withdraws[chain].get(user, [])
    if nonce >= len(withdraws):
        logger.debug(f"invalid nonce: maximum nonce is {len(withdraws) - 1}")
        raise HTTPException(400, {"error": "invalid nonce"})

    withdraw_tx = withdraws[nonce]

    return Withdraw(
        chain=withdraw_tx.chain,
        tokenID=withdraw_tx.token_id,
        amount=str(int(withdraw_tx.amount * (10 ** DECIMALS[withdraw_tx.token]))),
        user=str(int.from_bytes(user[1:], byteorder="big")),
        destination=Web3.to_checksum_address(withdraw_tx.dest),
        t=withdraw_tx.time,
        nonce=withdraw_tx.nonce,
    )


if zex.light_node:
    light_router.get("/user/{public}/withdraws/{chain}/{nonce}")(user_withdraw)
else:
    router.get("/user/{public}/withdraws/{chain}/{nonce}")(user_withdraw)
