import os
import time
from struct import pack, unpack
from secp256k1 import PrivateKey
from eth_hash.auto import keccak
import requests

DEPOSIT, WITHDRAW, BUY, SELL, CANCEL = b"dwbsc"

tokens = {"pol:usdt": b"pol" + pack(">I", 0), "eth:wbtc": b"eth" + pack(">I", 0)}

version = pack(">B", 1)

u1_private = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebad"
u2_private = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebac"
# u2_private = "f27be51111abb3677c50ffa801bba89480f5686c3205510f00ae67d5b0035875"
monitor_private = "cd7d94cd90d25d8722087a85e51ce3e5d8d06d98cb9f1c02e93f646c90af0193"

monitor = PrivateKey(bytes(bytearray.fromhex(monitor_private)), raw=True)

ip = os.getenv("HOST")
port = int(os.getenv("PORT"))


privkey = PrivateKey(bytes(bytearray.fromhex(u2_private)), raw=True)
pubkey = privkey.pubkey.serialize()
nonce = 0
counter = 1
price = 5000
volume = 1
tx = (
    pack(">B", SELL)
    + b"eth"
    + pack(">I", 0)
    + b"bst"
    + pack(">I", 1)
    + pack(">d", volume)
    + pack(">d", round(price, 2))
)

tx = version + tx
name = tx[1]
t = int(1720736774)
tx += pack(">II", t, nonce) + pubkey
msg = "v: 1\n"
msg += f'name: {"buy" if name == BUY else "sell"}\n'
msg += f'base token: {tx[2:5].decode("ascii")}:{unpack(">I", tx[5:9])[0]}\n'
msg += f'quote token: {tx[9:12].decode("ascii")}:{unpack(">I", tx[12:16])[0]}\n'
msg += f'amount: {unpack(">d", tx[16:24])[0]}\n'
msg += f'price: {unpack(">d", tx[24:32])[0]}\n'
msg += f"t: {t}\n"
msg += f"nonce: {nonce}\n"
msg += f"public: {pubkey.hex()}\n"
msg = "\x19Ethereum Signed Message:\n" + str(len(msg)) + msg
nonce += 1
print(f"next nonce: {nonce}")
sig = privkey.ecdsa_sign(keccak(msg.encode("ascii")), raw=True)
sig = privkey.ecdsa_serialize_compact(sig)
tx += sig
tx += pack(">Q", counter)
counter += 1
print(f"next counter: {counter}")
requests.post(f"http://{ip}:{port}/api/txs", json=[tx.decode("latin-1")])
print(msg)
print("encoded msg:", msg.encode("ascii"))
print("hashed msg:", keccak(msg.encode("ascii")))
print("signature bytes:", sig)
print("signature hex:", sig.hex())
print(tx.hex())
