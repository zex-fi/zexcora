import hashlib
from struct import unpack

import eth_abi
from bitcoinutils.keys import P2trAddress, PublicKey
from bitcoinutils.utils import tweak_taproot_pubkey
from eigensdk.crypto.bls.attestation import KeyPair
from eth_hash.auto import keccak
from fastapi import APIRouter, HTTPException
from loguru import logger

from app import BLS_PRIVATE, ZEX_BTC_PUBLIC_KEY, ZEX_MONERO_PUBLIC_ADDRESS, zex
from app.models.response import (
    BalanceResponse,
    DepositResponse,
    NonceResponse,
    OrderResponse,
    TradeResponse,
    UserAddressesResponse,
    UserIDResponse,
    UserPublicResponse,
)
from app.monero.address import Address
from app.zex import BUY

router = APIRouter()
light_router = APIRouter()


@router.get("/user/{public}/balances")
def user_balances(public: str) -> list[BalanceResponse]:
    user = bytes.fromhex(public)

    return [
        BalanceResponse(
            chain=token[0:3],
            token=int(token[4]),
            balance=str(zex.balances[token][user]),
        )
        for token in zex.balances
        if zex.balances[token].get(user, 0) > 0
    ]


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


@router.get("/user/{public}/deposits")
def user_deposits(public: str) -> list[DepositResponse]:
    user = bytes.fromhex(public)
    if user not in zex.deposits:
        return []
    return [
        DepositResponse(
            token=d.token,
            amount=d.amount,
            time=d.time,
        )
        for d in zex.deposits[user]
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
    bst_contract_address = "0xEca9036cFbfD61C952126F233682f9A6f97E4DBD"
    hol_contract_address = "0x3254BEe5c12A3f5c878D0ACEF194A6d611727Df7"
    sep_contract_address = "0xcD04Fb8a4d987dc537345267751EfD271d464F91"
    return UserAddressesResponse(
        BTC=taproot_address.to_string(),
        XMR=str(monero_address),
        BST=bst_contract_address,
        HOL=hol_contract_address,
        SEP=sep_contract_address,
    )


@router.get("/users/latest-id")
def get_latest_user_id():
    return UserIDResponse(id=zex.last_user_id)


def user_withdrawals(user: str, chain: str, nonce: int):
    user = bytes.fromhex(user)
    withdrawals = zex.withdrawals.get(chain, {}).get(user, [])
    nonce = int(nonce)
    if nonce < len(withdrawals):
        logger.debug(f"invalid nonce: maximum nonce is {len(withdrawals) - 1}")
        return HTTPException(400, {"error": "invalid nonce"})

    withdrawal = withdrawals[nonce]
    key = KeyPair.from_string(BLS_PRIVATE)
    encoded = eth_abi.encode(
        ["address", "uint256", "uint256", "uint256"],
        ["0xE8FB09228d1373f931007ca7894a08344B80901c", 0, 1, 0],
    )
    hash_bytes = keccak(encoded)
    signature = key.sign_message(msg_bytes=hash_bytes).to_json()
    return {
        "token": withdrawal.token_id,
        "amount": withdrawal.amount,
        "time": withdrawal.time,
        "nonce": nonce,
        "signature": signature,
    }


if zex.light_node:
    light_router.get("/user/{user}/withdrawals/{chain}/{nonce}")(user_withdrawals)
else:
    router.get("/user/{user}/withdrawals/{chain}/{nonce}")(user_withdrawals)
