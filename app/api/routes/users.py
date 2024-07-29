from struct import unpack

import eth_abi
from eigensdk.crypto.bls.attestation import KeyPair
from eth_hash.auto import keccak
from fastapi import APIRouter, HTTPException
from loguru import logger

from app import BLS_PRIVATE, zex
from app.models.response import (
    BalanceResponse,
    NonceResponse,
    OrderResponse,
    TradeResponse,
)
from app.zex import BUY

router = APIRouter()


@router.get("/user/{user}/balances")
def user_balances(user: str) -> list[BalanceResponse]:
    user = bytes.fromhex(user)

    return [
        BalanceResponse(
            chain=token[0:3],
            token=int(token[4]),
            balance=str(zex.balances[token][user]),
        )
        for token in zex.balances
        if zex.balances[token].get(user, 0) > 0
    ]


@router.get("/user/{user}/trades")
def user_trades(user: str) -> list[TradeResponse]:
    user = bytes.fromhex(user)
    trades = zex.trades.get(user, [])
    return [
        {
            "name": "buy" if name == BUY else "sell",
            "t": t,
            "base_chain": pair[0:3],
            "base_token": pair[4],
            "quote_chain": pair[5:8],
            "quote_token": pair[9],
            "amount": amount,
            "price": unpack(">d", tx[24:32])[0],
            "nonce": unpack(">I", tx[36:40])[0],
            "index": unpack(">Q", tx[137:145])[0],
        }
        for t, amount, pair, name, tx in trades
    ]


@router.get("/user/{user}/orders")
def user_orders(user: str) -> list[OrderResponse]:
    user = bytes.fromhex(user)
    orders = zex.orders.get(user, {})
    orders = [
        {
            "name": "buy" if o[1] == BUY else "sell",
            "base_chain": o[2:5].decode("ascii"),
            "base_token": unpack(">I", o[5:9])[0],
            "quote_chain": o[9:12].decode("ascii"),
            "quote_token": unpack(">I", o[12:16])[0],
            "amount": unpack(">d", o[16:24])[0],
            "price": unpack(">d", o[24:32])[0],
            "t": unpack(">I", o[32:36])[0],
            "nonce": unpack(">I", o[36:40])[0],
            "index": unpack(">Q", o[137:145])[0],
        }
        for o in orders
    ]
    return orders


@router.get("/user/{user}/nonce")
def user_nonce(user: str) -> NonceResponse:
    user = bytes.fromhex(user)
    return NonceResponse(nonce=zex.nonces.get(user, 0))


@router.get("/user/{user}/withdrawals/{chain}/{nonce}")
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
