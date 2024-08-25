from struct import unpack

import eth_abi
from eigensdk.crypto.bls.attestation import KeyPair
from eth_hash.auto import keccak
from fastapi import APIRouter, HTTPException
from loguru import logger

from app import BLS_PRIVATE, zex
from app.models.response import (
    BalanceResponse,
    DepositResponse,
    NonceResponse,
    OrderResponse,
    TradeResponse,
    UserIDResponse,
    UserPublicResponse,
)
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
def get_user_public(id: int):
    if id not in zex.id_to_public_lookup:
        return HTTPException(404, {"error": "user not found"})
    public = zex.id_to_public_lookup[id].hex()
    return UserPublicResponse(public=public)


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
