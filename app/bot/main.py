import os
from struct import pack
from threading import Thread

import requests
from secp256k1 import PrivateKey

from app.bot import ZexBot

DEPOSIT, WITHDRAW, BUY, SELL, CANCEL = b"dwbsc"

version = pack(">B", 1)

u1_private = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebad"
u2_private = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebac"
client_private = "f27be51111abb3677c50ffa801bba89480f5686c3205510f00ae67d5b0035875"
monitor_private = "cd7d94cd90d25d8722087a85e51ce3e5d8d06d98cb9f1c02e93f646c90af0193"

monitor = PrivateKey(bytes(bytearray.fromhex(monitor_private)), raw=True)
ip = os.getenv("HOST")
port = int(os.getenv("PORT"))


if __name__ == "__main__":
    client = ZexBot(client_private, "bst", 1, "bst:1-bst:2", "sell", None)
    tx = client.deposit(1000000, b"bst").decode("latin-1")
    with ZexBot.send_tx_lock:
        requests.post(f"http://{ip}:{port}/api/v1/txs", json=[tx])
    client.deposit_token_id = 2
    tx = client.deposit(1500000, b"bst").decode("latin-1")
    with ZexBot.send_tx_lock:
        requests.post(f"http://{ip}:{port}/api/v1/txs", json=[tx])

    buyer_bot = ZexBot(u1_private, "bst", 2, "bst:1-bst:2", "buy", 1)
    seller_bot = ZexBot(u2_private, "bst", 1, "bst:1-bst:2", "sell", 2)
    t1 = Thread(target=buyer_bot.run)
    t2 = Thread(target=seller_bot.run)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
