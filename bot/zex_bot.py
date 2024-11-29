from collections import deque
from struct import pack, unpack
from threading import Lock, Thread
import json
import os
import random
import time

from eth_hash.auto import keccak
from secp256k1 import PrivateKey
from websocket import WebSocket, WebSocketApp
import httpx
import numpy as np
import websocket

HOST = os.getenv("ZEX_HOST")
PORT = int(os.getenv("ZEX_PORT"))

assert HOST is not None and PORT is not None, "HOST or PORT is not defined"

BTC_XMR_DEPOSIT, DEPOSIT, WITHDRAW, BUY, SELL, CANCEL, REGISTER = b"xdwbscr"

version = pack(">B", 1)

MAX_ORDERS_COUNT = 5
MIN_ORDER_VALUE = 1


class ZexBot:
    def __init__(
        self,
        private_key: bytes,
        pair: str,
        side: str,
        best_bid: float,
        best_ask: float,
        volume_digits: int,
        price_digits: int,
        lock: Lock,
        seed: int | None = 1,
    ) -> None:
        self.privkey = PrivateKey(private_key, raw=True)
        self.pair = pair
        self.side = side
        self.is_running = False
        self.volume_digits = volume_digits
        self.price_digits = price_digits
        self.lock = lock
        self.rng = random.Random(seed)

        self.pubkey = self.privkey.pubkey.serialize()
        self.user_id: int | None = None
        self.nonce = -1
        self.counter = 0
        self.orders = deque()
        self.websocket: WebSocketApp | None = None

        bids, asks = self.get_order_book()
        self.bids = {price: volume for price, volume in bids if volume != 0}
        self.asks = {price: volume for price, volume in asks if volume != 0}

        if len(self.bids.keys()) == 0:
            self.best_bid = best_bid
        else:
            self.best_bid = max(self.bids.keys())

        if len(self.asks.keys()) == 0:
            self.best_ask = best_ask
        else:
            self.best_ask = min(self.asks.keys())

        self.base_volume = MIN_ORDER_VALUE / self.best_bid

        self.register()
        # self.send_order()

    def on_open_wrapper(self):
        def on_open(ws: WebSocket):
            time.sleep(1)
            ws.send(
                json.dumps(
                    {
                        "method": "SUBSCRIBE",
                        "params": [f"{self.pair}@kline_1m", f"{self.pair}@depth"],
                        "id": 1,
                    }
                )
            )

        return on_open

    def on_message_wrapper(self):
        def on_message(_, msg):
            data = json.loads(msg)
            if "id" in data:
                return
            elif "depth" in data["stream"]:
                for price, qty in data["data"]["b"]:
                    if qty == 0:
                        if price in self.bids:
                            del self.bids[price]
                    else:
                        self.bids[price] = qty
                for price, qty in data["data"]["a"]:
                    if qty == 0:
                        if price in self.asks:
                            del self.asks[price]
                    else:
                        self.asks[price] = qty
                if len(self.bids.keys()) != 0:
                    best_bid_price = max(self.bids.keys())
                    self.best_bid = best_bid_price
                    self.base_volume = MIN_ORDER_VALUE / self.best_bid
                if len(self.asks.keys()) != 0:
                    best_ask_price = min(self.asks.keys())
                    self.best_ask = best_ask_price

                # self.send_order()

        return on_message

    def send_order(self):
        if self.side == "buy" and len(self.bids) == 0:
            price = self.best_ask - (self.best_ask * 0.2 * self.rng.random())
            self.send_order_transaction(price)
        elif self.side == "sell" and len(self.asks) == 0:
            price = self.best_bid + (self.best_bid * 0.2 * self.rng.random())
            self.send_order_transaction(price)

    def send_order_transaction(self, price):
        price = round(price, self.price_digits)
        volume = round(
            self.base_volume + self.rng.random() * self.base_volume / 2,
            self.volume_digits,
        )
        if volume < self.base_volume * 0.001:
            volume = round(self.base_volume, self.volume_digits)
        with self.lock:
            time.sleep(0.2)
            resp = httpx.get(f"http://{HOST}:{PORT}/v1/user/nonce?id={self.user_id}")
            self.nonce = resp.json()["nonce"]
            tx = self.create_order(price, volume, maker=True)
            self.orders.append(tx)
            txs = [tx.decode("latin-1")]

            if len(self.orders) >= MAX_ORDERS_COUNT:
                oldest_tx = self.orders.popleft()
                cancel_tx = self.create_cancel_order(oldest_tx[1:40])
                txs.append(cancel_tx.decode("latin-1"))

            httpx.post(f"http://{HOST}:{PORT}/v1/order", json=txs)

    def get_order_book(self):
        resp = httpx.get(f"http://{HOST}:{PORT}/v1/depth?symbol={self.pair}&limit=500")
        resp.raise_for_status()
        data = resp.json()
        return data["bids"], data["asks"]

    def create_order(
        self,
        price: float | int,
        volume: float,
        maker: bool = False,
        verbose=True,
    ):
        tx = (
            pack(">B", BUY if self.side == "buy" else SELL)
            + self.pair[:3].encode()
            + pack(">I", int(self.pair[4]))
            + self.pair[6:9].encode()
            + pack(">I", int(self.pair[10]))
            + pack(">d", volume)
            + pack(">d", price)
        )
        if verbose:
            print(
                f"pair: {self.pair}, none: {self.nonce}, maker: {maker}, side: {self.side}, price: {price}, vol: {volume}"
            )
        tx = version + tx
        name = tx[1]
        t = int(time.time())
        tx += pack(">II", t, self.nonce) + self.pubkey
        msg = "v: 1\n"
        msg += f'name: {"buy" if name == BUY else "sell"}\n'
        msg += f'base token: {tx[2:5].decode("ascii")}:{unpack(">I", tx[5:9])[0]}\n'
        msg += f'quote token: {tx[9:12].decode("ascii")}:{unpack(">I", tx[12:16])[0]}\n'
        msg += f'amount: {np.format_float_positional(unpack(">d", tx[16:24])[0], trim="0")}\n'
        msg += f'price: {np.format_float_positional(unpack(">d", tx[24:32])[0], trim="0")}\n'
        msg += f"t: {t}\n"
        msg += f"nonce: {self.nonce}\n"
        msg += f"public: {self.pubkey.hex()}\n"
        msg = "\x19Ethereum Signed Message:\n" + str(len(msg)) + msg
        self.nonce += 1
        sig = self.privkey.ecdsa_sign(keccak(msg.encode("ascii")), raw=True)
        sig = self.privkey.ecdsa_serialize_compact(sig)
        tx += sig
        tx += pack(">Q", self.counter)
        self.counter += 1
        return tx

    def create_cancel_order(self, order: bytes):
        tx = version + pack(">B", CANCEL) + order + self.pubkey
        msg = f"""v: {tx[0]}\nname: cancel\nslice: {tx[2:41].hex()}\npublic: {tx[41:74].hex()}\n"""
        msg = "".join(("\x19Ethereum Signed Message:\n", str(len(msg)), msg))

        sig = self.privkey.ecdsa_sign(keccak(msg.encode("ascii")), raw=True)
        sig = self.privkey.ecdsa_serialize_compact(sig)
        tx += sig
        return tx

    def create_register_msg(self):
        """Format registration message for verification."""
        msg = "Welcome to ZEX."
        msg = "".join(("\x19Ethereum Signed Message:\n", str(len(msg)), msg))
        return msg.encode("ascii")

    def register(self):
        tx = version + pack(">B", REGISTER) + self.pubkey
        sig = self.privkey.ecdsa_sign(keccak(self.create_register_msg()), raw=True)
        sig = self.privkey.ecdsa_serialize_compact(sig)
        tx += sig

        httpx.post(f"http://{HOST}:{PORT}/v1/order", json=[tx.decode("latin-1")])
        for _ in range(5):
            resp = httpx.get(
                f"http://{HOST}:{PORT}/v1/user/id?public={self.pubkey.hex()}"
            )
            if resp.status_code != 200:
                time.sleep(0.1)
                continue
            self.user_id = resp.json()["id"]
            break
        if self.user_id is None:
            resp.raise_for_status()

    def run(self):
        websocket.enableTrace(False)
        self.websocket = WebSocketApp(
            f"ws://{HOST}:{PORT}/ws",
            on_open=self.on_open_wrapper(),
            on_message=self.on_message_wrapper(),
        )
        Thread(target=self.websocket.run_forever, kwargs={"reconnect": 5}).start()
        self.is_running = True
        while self.is_running:
            time.sleep(1)
            maker = self.rng.choices([True, False], [0.5, 0.5])[0]
            price = 0
            if maker:
                if self.side == "buy":
                    price = self.best_ask - (self.best_ask * 0.1 * self.rng.random())
                elif self.side == "sell":
                    price = self.best_bid + (self.best_bid * 0.1 * self.rng.random())
            else:
                if self.side == "buy":
                    price = self.best_ask
                elif self.side == "sell":
                    price = self.best_bid
            self.send_order_transaction(price)
