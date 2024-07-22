from typing import Optional
import time
import os
from collections import deque
from threading import Thread, Lock
import asyncio

from contextlib import asynccontextmanager
from struct import unpack, pack

from loguru import logger
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware


from eigensdk.crypto.bls.attestation import KeyPair
from eth_hash.auto import keccak
import eth_abi

from callbacks import depth_event, kline_event
from connection_manager import ConnectionManager
from models.response import BalanceResponse, NonceResponse, OrderResponse, TradeResponse
from zex import Zex, Operation
from verify import pool

# ZSEQ_HOST = os.environ.get("ZSEQ_HOST")
# ZSEQ_PORT = int(os.environ.get("ZSEQ_PORT"))
# ZSEQ_URL = f"http://{ZSEQ_HOST}:{ZSEQ_PORT}/node/transactions"
BLS_PRIVATE = os.environ.get("BLS_PRIVATE")
assert BLS_PRIVATE, "BLS_PRIVATE env variableis not set"

manager = ConnectionManager()

zex = Zex(kline_callback=kline_event(manager), depth_callback=depth_event(manager))

zseq_lock = Lock()
zseq_deque = deque()


class StreamRequest(BaseModel):
    id: int
    method: str
    params: list[str]


class StreamResponse(BaseModel):
    id: int
    result: Optional[str]


class JSONMessageManager:
    @classmethod
    def handle(self, message, websocket: WebSocket, context: dict):
        request = StreamRequest.model_validate_json(message)
        match request.method.upper():
            case "SUBSCRIBE":
                for channel in request.params:
                    manager.subscribe(websocket, channel.lower())
                return StreamResponse(id=request.id, result=None)
            case "UNSUBSCRIBE":
                for channel in request.params:
                    manager.unsubscribe(websocket, channel.lower())
                return StreamResponse(id=request.id, result=None)


async def process_loop():
    index = 0
    while True:
        if len(zseq_deque) == 0:
            await asyncio.sleep(0.1)
            continue

        with zseq_lock:
            finalized_txs = [
                {"index": index + i, "tx": zseq_deque.popleft()}
                for i in range(len(zseq_deque))
            ]
        index += len(finalized_txs)
        if finalized_txs:
            sorted_numbers = sorted([t["index"] for t in finalized_txs])
            logger.debug(
                f"\nreceive finalized indexes: [{sorted_numbers[0]}, ..., {sorted_numbers[-1]}]",
            )
            txs = [tx["tx"].encode("latin-1") for tx in finalized_txs]
            try:
                zex.process(txs)
            except Exception:
                logger.exception("process loop")
        await asyncio.sleep(0.1)


# Run the broadcaster in the background
@asynccontextmanager
async def lifespan(app: FastAPI):
    Thread(target=asyncio.run, args=(process_loop(),), daemon=True).start()
    yield
    pool.close()
    pool.join()


app = FastAPI(lifespan=lifespan, root_path="/api")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/fapi/v1/ping")
async def ping():
    return {}


@app.get("/fapi/v1/time")
async def server_time():
    return {"serverTime": int(time.time() * 1000)}


@app.get("/fapi/v1/depth")
async def depth(symbol: str, limit: int = 500):
    return zex.get_order_book(symbol, limit)


@app.get("/fapi/v1/trades")
async def trades(symbol: str, limit: int = 500):
    raise NotImplementedError()


@app.get("/fapi/v1/historicalTrades")
async def historical_trades(
    symbol: str, limit: int = 500, fromId: Optional[int] = None
):
    raise NotImplementedError()


@app.get("/fapi/v1/pairs")
async def pairs():
    return list(zex.orderbooks.keys())


@app.get("/fapi/v1/aggTrades")
async def agg_trades(
    symbol: str,
    fromId: Optional[int] = None,
    startTime: Optional[int] = None,
    endTime: Optional[int] = None,
    limit: int = 500,
):
    raise NotImplementedError()


@app.get("/fapi/v1/klines")
async def klines(
    symbol: str,
    interval: str,
    startTime: Optional[int] = None,
    endTime: Optional[int] = None,
    limit: int = 500,
):
    base_klines = zex.get_kline(symbol.lower())
    if len(base_klines) == 0:
        return []
    if not startTime:
        startTime = base_klines.index[0]

    if not endTime:
        endTime = base_klines.iloc[-1]["CloseTime"]

    return [
        [
            idx,
            x["Open"],
            x["High"],
            x["Low"],
            x["Close"],
            x["Volume"],
            x["CloseTime"],
            0,
            x["NumberOfTrades"],
            0,
            0,
            -1,
        ]
        for idx, x in base_klines.iterrows()
        if startTime <= idx and endTime >= x["CloseTime"]
    ][-limit:]


@app.get("/orders/{pair}/{name}")
def pair_orders(pair, name):
    pair = pair.split("_")
    pair = (
        pair[0].encode()
        + pack(">I", int(pair[1]))
        + pair[2].encode()
        + pack(">I", int(pair[3]))
    )
    q = zex.orderbooks.get(pair)
    if not q:
        return []
    q = q.buy_orders if name == "buy" else q.sell_orders
    return [
        {
            "amount": unpack(">d", o[16:24])[0],
            "price": unpack(">d", o[24:32])[0],
        }
        for price, index, o in q
    ]


@app.get("/user/{user}/balances")
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


@app.get("/user/{user}/trades")
def user_trades(user: str) -> list[TradeResponse]:
    user = bytes.fromhex(user)
    trades = zex.trades.get(user, [])
    return [
        {
            "name": "buy" if name == Operation.BUY else "sell",
            "t": t,
            "amount": amount,
            "base_chain": pair[0:3].decode("ascii"),
            "base_token": unpack(">I", pair[3:7])[0],
            "quote_chain": pair[7:10].decode("ascii"),
            "quote_token": unpack(">I", pair[10:14])[0],
        }
        for t, amount, pair, name in trades
    ]


@app.get("/user/{user}/orders")
def user_orders(user: str) -> list[OrderResponse]:
    user = bytes.fromhex(user)
    orders = zex.orders.get(user, {})
    orders = [
        {
            "name": "buy" if o[1] == Operation.BUY.value else "sell",
            "base_chain": o[2:5].decode("ascii"),
            "base_token": unpack(">I", o[5:9])[0],
            "quote_chain": o[9:12].decode("ascii"),
            "quote_token": unpack(">I", o[12:16])[0],
            "amount": unpack(">d", o[16:24])[0],
            "price": unpack(">d", o[24:32])[0],
            "t": unpack(">I", o[32:36])[0],
            "nonce": unpack(">I", o[36:40])[0],
            "index": unpack(">Q", o[-8:])[0],
        }
        for o in orders
    ]
    return orders


@app.get("/user/{user}/nonce")
def user_nonce(user: str) -> NonceResponse:
    user = bytes.fromhex(user)
    return NonceResponse(nonce=zex.nonces.get(user, 0))


@app.get("/user/{user}/withdrawals/{chain}/{nonce}")
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


@app.post("/txs")
def send_txs(txs: list[str]):
    with zseq_lock:
        zseq_deque.extend(txs)
    return {"success": True}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    async def receive_messages():
        async for message in websocket.iter_text():
            response = JSONMessageManager.handle(message, websocket, context={})
            await websocket.send_text(response.model_dump_json())

    try:
        await receive_messages()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
