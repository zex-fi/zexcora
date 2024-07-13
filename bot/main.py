import os
import json
from threading import Thread, Lock
import time
import random
from typing import Optional
import requests
from struct import pack, unpack
from secp256k1 import PrivateKey
from eth_hash.auto import keccak
from websocket import WebSocket, WebSocketApp
import websocket

DEPOSIT, WITHDRAW, BUY, SELL, CANCEL = b"dwbsc"

version = pack(">B", 1)

u1_private = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebad"
u2_private = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebac"
monitor_private = "cd7d94cd90d25d8722087a85e51ce3e5d8d06d98cb9f1c02e93f646c90af0193"

monitor = PrivateKey(bytes(bytearray.fromhex(monitor_private)), raw=True)
ip = os.getenv("HOST")
port = int(os.getenv("PORT"))


class ZexBot:
    send_tx_lock = Lock()
    last_block_range = 41993101

    def __init__(
        self,
        private_key: str,
        deposit_chain: str,
        deposit_token_id: int,
        pair: str,
        side: str,
        seed: Optional[int] = 1,
    ) -> None:
        self.privkey = PrivateKey(bytes(bytearray.fromhex(private_key)), raw=True)
        self.deposit_chain = deposit_chain
        self.deposit_token_id = deposit_token_id
        self.pair = pair
        self.side = side
        self.rng = random.Random(seed)
        self.pubkey = self.privkey.pubkey.serialize()
        self.nonce = 0
        self.counter = 0
        self.orders = set()
        self.websocket = WebSocketApp(
            f"ws://{ip}:{port}/ws",
            on_open=self.on_open_wrapper(),
            on_message=self.on_messsage_wrapper(),
        )
        self.bids = {5000.0: 0.1}
        self.best_bid = (5000.0, 0.1)
        self.asks = {5000.0: 0.15}
        self.best_ask = (5000.0, 0.15)

    def on_open_wrapper(self):
        def on_open(ws: WebSocket):
            time.sleep(1)
            print("making deposit")
            ws.send(
                json.dumps(
                    {
                        "method": "SUBSCRIBE",
                        "params": [f"{self.pair}@kline_1m", f"{self.pair}@depth"],
                        "id": 1,
                    }
                )
            )
            if self.side == "buy":
                tx1 = self.deposit(
                    1_000_000,
                    self.deposit_chain.encode(),
                ).decode("latin-1")
                # tx2 = self.create_order(2000, 0.001, False).decode("latin-1")
                with ZexBot.send_tx_lock:
                    requests.post(f"http://{ip}:{port}/api/txs", json=[tx1])
            elif self.side == "sell":
                tx1 = self.deposit(
                    1_500_000,
                    self.deposit_chain.encode(),
                ).decode("latin-1")
                # tx2 = self.create_order(2000, 0.0015, False).decode("latin-1")
                with ZexBot.send_tx_lock:
                    requests.post(f"http://{ip}:{port}/api/txs", json=[tx1])

        return on_open

    def on_messsage_wrapper(self):
        def on_message(ws, msg):
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
                best_bid_price = sorted(self.bids.keys())[-1]
                self.best_bid = (best_bid_price, self.bids[best_bid_price])
                best_ask_price = sorted(self.asks.keys())[0]
                self.best_ask = (best_ask_price, self.asks[best_ask_price])
                print("self.best_bid", self.best_bid)
                print("self.best_ask", self.best_ask)
            # elif "kline" in data["stream"]:
            #     self.close_price = float(data["data"]["k"]["c"])

        return on_message

    def deposit(self, amount: int, chain: bytes):
        t = pack(">I", int(time.time()))

        range_start = ZexBot.last_block_range
        range_end = ZexBot.last_block_range
        ZexBot.last_block_range = range_end + 1

        block_range = pack(">QQ", range_start, range_end)

        count = 2
        tx = pack(">I", self.deposit_token_id) + pack(">d", amount)
        chunk = (tx + t + self.pubkey) * count
        tx = version + pack(">B", DEPOSIT) + chain + block_range + pack(">H", count)
        tx += chunk
        tx += monitor.schnorr_sign(tx, bip340tag="zex")
        tx += pack(">Q", self.counter)
        self.counter += 1
        return tx

    def create_order(self, price: float, volume: float = None, maker: bool = False):
        if self.side == "buy":
            # price = price - (self.rng.random() * 0.01 * price) if maker else price
            # volume = self.rng.random() * 0.1 if volume is None else volume
            tx = (
                pack(">B", BUY)
                + self.pair[:3].encode()
                + pack(">I", int(self.pair[4]))
                + self.pair[6:9].encode()
                + pack(">I", int(self.pair[10]))
                + pack(">d", volume)
                + pack(">d", price)
            )
        elif self.side == "sell":
            # price = price + (self.rng.random() * 0.01 * price) if maker else price
            # volume = self.rng.random() * 0.1 if volume is None else volume
            tx = (
                pack(">B", SELL)
                + self.pair[:3].encode()
                + pack(">I", int(self.pair[4]))
                + self.pair[6:9].encode()
                + pack(">I", int(self.pair[10]))
                + pack(">d", volume)
                + pack(">d", price)
            )
        print(f"maker: {maker}, side: {self.side}, price: {price}, vol: {volume}")
        tx = version + tx
        name = tx[1]
        t = int(time.time())
        tx += pack(">II", t, self.nonce) + self.pubkey
        msg = "v: 1\n"
        msg += f'name: {"buy" if name == BUY else "sell"}\n'
        msg += f'base token: {tx[2:5].decode("ascii")}:{unpack(">I", tx[5:9])[0]}\n'
        msg += f'quote token: {tx[9:12].decode("ascii")}:{unpack(">I", tx[12:16])[0]}\n'
        msg += f'amount: {unpack(">d", tx[16:24])[0]}\n'
        msg += f'price: {unpack(">d", tx[24:32])[0]}\n'
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

    def run(self):
        websocket.enableTrace(False)
        Thread(target=self.websocket.run_forever, kwargs={"reconnect": 5}).start()
        while True:
            time.sleep(4)
            maker = self.rng.choices([True, False], [0.75, 0.25])[0]
            price = 0
            if maker:
                if self.side == "buy":
                    price = self.best_ask[0] - (
                        self.best_ask[0] * 0.01 * self.rng.random()
                    )
                elif self.side == "sell":
                    price = self.best_bid[0] + (
                        self.best_bid[0] * 0.01 * self.rng.random()
                    )
            else:
                if self.side == "buy":
                    price = self.best_ask[0]
                elif self.side == "sell":
                    price = self.best_bid[0]
            price = round(price, 2)
            print(price)
            volume = round(self.rng.random() * 0.01, 4)
            while volume < 0.0001:
                volume = round(self.rng.random() * 0.01, 4)

            tx = self.create_order(price, volume, maker=maker).decode("latin-1")
            with ZexBot.send_tx_lock:
                requests.post(f"http://{ip}:{port}/api/txs", json=[tx])


if __name__ == "__main__":
    buyer_bot = ZexBot(u1_private, "bst", 2, "bst:1-bst:2", "buy", None)
    seller_bot = ZexBot(u2_private, "bst", 1, "bst:1-bst:2", "sell", None)
    t1 = Thread(target=buyer_bot.run)
    t2 = Thread(target=seller_bot.run)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
