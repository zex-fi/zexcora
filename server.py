from typing import Optional
import time
import os
import json
from collections import deque
from threading import Thread, Lock

from contextlib import asynccontextmanager
from struct import unpack, pack

import requests

import pandas as pd
from pydantic import BaseModel
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import asyncio


from zex import Zex, Operation

ZSEQ_HOST = os.environ.get("ZSEQ_HOST")
ZSEQ_PORT = int(os.environ.get("ZSEQ_PORT"))
ZSEQ_URL = f"http://{ZSEQ_HOST}:{ZSEQ_PORT}/node/transactions"


def kline_event(kline: pd.DataFrame):
    if len(kline) == 0:
        return
    subs = manager.subscriptions.copy()
    for channel, clients in subs.items():
        symbol, details = channel.lower().split("@")
        if "kline" not in details:
            continue
        now = int(time.time() * 1000)
        last_candle = kline.iloc[len(kline) - 1]
        message = {
            "stream": channel.lower(),
            "data": {
                "e": "kline",  # Event type
                "E": int(time.time() * 1000),  # Event time
                "s": symbol.upper(),  # Symbol
                "k": {
                    "t": int(last_candle.name),  # Kline start time
                    "T": last_candle["CloseTime"],  # Kline close time
                    "s": symbol.upper(),  # Symbol
                    "i": "1m",  # Interval
                    "f": 100,  # First trade ID
                    "L": 200,  # Last trade ID
                    "o": f"{last_candle['Open']:.2f}",  # Open price
                    "c": f"{last_candle['Close']:.2f}",  # Close price
                    "h": f"{last_candle['High']:.2f}",  # High price
                    "l": f"{last_candle['Low']:.2f}",  # Low price
                    "v": f"{last_candle['Volume']:.2f}",  # Base asset volume
                    "n": last_candle["NumberOfTrades"],  # Number of trades
                    "x": bool(now >= last_candle["CloseTime"]),  # Is this kline closed?
                    "q": "1.0000",  # Quote asset volume
                    "V": "500",  # Taker buy base asset volume
                    "Q": "0.500",  # Taker buy quote asset volume
                    "B": "123456",  # Ignore
                },
            },
        }

        # Copy to avoid modification during iteration
        for ws in clients:
            asyncio.run(broadcast(ws, channel.lower(), message))


def depth_event(depth: dict):
    subs = manager.subscriptions.copy()
    for channel, clients in subs.items():
        symbol, details = channel.lower().split("@")
        if "depth" not in details:
            continue
        # Copy to avoid modification during iteration
        for ws in clients:
            asyncio.run(
                broadcast(
                    ws, channel.lower(), {"stream": channel.lower(), "data": depth}
                )
            )


zex = Zex(kline_callback=kline_event, depth_callback=depth_event)

zseq_lock = Lock()
zseq_deque = deque()


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.subscriptions: dict[str, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

    def subscribe(self, websocket: WebSocket, channel: str):
        if channel not in self.subscriptions:
            self.subscriptions[channel] = set()
        self.subscriptions[channel].add(websocket)
        return f"Subscribed to {channel}"

    def unsubscribe(self, websocket: WebSocket, channel: str):
        if channel in self.subscriptions and websocket in self.subscriptions[channel]:
            self.subscriptions[channel].remove(websocket)
            if not self.subscriptions[channel]:  # Remove channel if empty
                del self.subscriptions[channel]
            return f"Unsubscribed from {channel}"
        return f"Not subscribed to {channel}"


manager = ConnectionManager()


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


async def broadcast(ws: WebSocket, channel: str, message: dict):
    try:
        await ws.send_json(message)
    except Exception as e:
        print(e)
        manager.subscriptions[channel].remove(ws)
        if not manager.subscriptions[channel]:
            del manager.subscriptions[channel]


def process_loop():
    last = 0
    index = 0
    while True:
        # params = {"after": last, "states": ["finalized"]}
        # response = requests.get(ZSEQ_URL, params=params)
        # finalized_txs = response.json().get("data")
        with zseq_lock:
            finalized_txs = [
                {"index": index + i, "tx": zseq_deque.popleft()}
                for i in range(len(zseq_deque))
            ]
        index += len(finalized_txs)
        if finalized_txs:
            last = max(tx["index"] for tx in finalized_txs)
            sorted_numbers = sorted([t["index"] for t in finalized_txs])
            print(
                f"\nreceive finalized indexes: [{sorted_numbers[0]}, ..., {sorted_numbers[-1]}]",
            )
            txs = [tx["tx"].encode("latin-1") for tx in finalized_txs]
            try:
                zex.process(txs)
            except Exception as e:
                print(e)
        time.sleep(0.05)


# Run the broadcaster in the background
@asynccontextmanager
async def lifespan(app: FastAPI):
    # asyncio.create_task(broadcaster())
    Thread(target=process_loop, daemon=True).start()
    yield


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
    return list(zex.queues.keys())


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

    # return base_klines.resample(interval).agg(columns_dict).to_dict()
    return base_klines.to_dict()


@app.get("/orders/{pair}/{name}")
def pair_orders(pair, name):
    pair = pair.split("_")
    pair = (
        pair[0].encode()
        + pack(">I", int(pair[1]))
        + pair[2].encode()
        + pack(">I", int(pair[3]))
    )
    q = zex.queues.get(pair)
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
def user_balances(user):
    user = bytes.fromhex(user)
    return [
        {
            "chain": token[0:3].decode("ascii"),
            "token": unpack(">I", token[3:7])[0],
            "balance": zex.balances[token][user],
        }
        for token in zex.balances
        if zex.balances[token].get(user, 0) > 0
    ]


@app.get("/user/{user}/trades")
def user_trades(user):
    trades = zex.trades.get(bytes.fromhex(user), [])
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
def user_orders(user):
    orders = zex.orders.get(bytes.fromhex(user), {})
    orders = [
        {
            "name": "buy" if o[1] == Operation.BUY else "sell",
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


@app.post("/txs")
def send_txs(txs: list[str]):
    # headers = {"Content-Type": "application/json"}
    # data = {
    #     "transactions": [{"tx": tx} for tx in txs],
    #     "timestamp": int(time.time()),
    # }
    # requests.put(ZSEQ_URL, json.dumps(data), headers=headers)
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
