import hashlib
import copy
import json
import time
import random
import requests
from struct import pack, unpack
from secp256k1 import PrivateKey, PublicKey
from eth_hash.auto import keccak
from verify import order_msg, withdraw_msg

DEPOSIT, WITHDRAW, BUY, SELL, CANCEL = b"dwbsc"


tokens = {"pol:usdt": b"pol" + pack(">I", 0), "eth:wbtc": b"eth" + pack(">I", 0)}

version = pack(">B", 1)

u1_private = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebad"
u2_private = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebac"
monitor_private = "cd7d94cd90d25d8722087a85e51ce3e5d8d06d98cb9f1c02e93f646c90af0193"

u1 = PrivateKey(bytes(bytearray.fromhex(u1_private)), raw=True)
u2 = PrivateKey(bytes(bytearray.fromhex(u2_private)), raw=True)
monitor = PrivateKey(bytes(bytearray.fromhex(monitor_private)), raw=True)


def pub(u: PrivateKey):
    return u.pubkey.serialize()


print(pub(u1).hex())
print(pub(u2).hex())
privs = {pub(u1): u1, pub(u2): u2}

deposit_usdt = tokens["pol:usdt"][3:] + pack(">d", 1500000000)
deposit_wbtc = tokens["eth:wbtc"][3:] + pack(">d", 1000000)

buy = (
    pack(">B", BUY)
    + tokens["eth:wbtc"]
    + tokens["pol:usdt"]
    + pack(">d", 0.01)
    + pack(">d", 70000)
)
sell = (
    pack(">B", SELL)
    + tokens["eth:wbtc"]
    + tokens["pol:usdt"]
    + pack(">d", 0.02)
    + pack(">d", 71000)
)

# cancel = chr(CANCEL).encode() + txs[-2][:66]
# txs.insert(3, cancel)

nonces = {pub(u1): 0, pub(u2): 0}
withdraw_nonces = {pub(u1): 0, pub(u2): 0}
deposit_nonces = {b"pol": 0, b"eth": 0}
counter = 0


def deposit(tx, pubkey, from_block, to_block):
    global counter
    t = pack(">I", int(time.time()))
    chain = b"pol" if tx == deposit_usdt else b"eth"
    block_range = pack(">QQ", from_block, to_block)
    count = 10
    chunk = (tx + t + pubkey) * count
    tx = version + pack(">B", DEPOSIT) + chain + block_range + pack(">H", count)
    tx += chunk
    tx += monitor.schnorr_sign(tx, bip340tag="zex")
    tx += pack(">Q", counter)
    counter += 1
    return tx


def order(tx):
    global counter
    tx = version + tx
    name = tx[1]
    public = pub(u2) if name == SELL else pub(u1)
    t = int(time.time())
    tx += pack(">II", t, nonces[public]) + public
    msg = order_msg(tx)
    nonces[public] += 1
    u = privs[public]
    sig = u.ecdsa_sign(keccak(msg), raw=True)
    sig = u.ecdsa_serialize_compact(sig)
    tx += sig
    tx += pack(">Q", counter)
    counter += 1
    return tx


def withdraw(token, amount, dest, u):
    global counter
    dest = bytes.fromhex(dest.replace("0x", ""))
    tx = version + pack(">B", WITHDRAW) + token + pack(">d", amount) + dest
    public = pub(u)
    t = int(time.time())
    tx += pack(">II", t, withdraw_nonces[public]) + public
    msg = withdraw_msg(tx)
    withdraw_nonces[public] += 1
    sig = u.ecdsa_sign(keccak(msg), raw=True)
    sig = u.ecdsa_serialize_compact(sig)
    tx += sig
    tx += pack(">Q", counter)
    counter += 1
    return tx


def get_txs(n):
    txs = [
        # deposit(deposit_usdt, pub(u1), 1, 5),
        # deposit(deposit_wbtc, pub(u1), 1, 5),
        # deposit(deposit_usdt, pub(u2), 6, 10),
        # deposit(deposit_wbtc, pub(u2), 6, 10),
    ]
    for i in range(n):
        txs.append(order(buy))
        txs.append(order(sell))
    # txs.append(
    #     withdraw(
    #         tokens["pol:usdt"], 1, "0xE8FB09228d1373f931007ca7894a08344B80901c", u1
    #     )
    # )
    return txs


if __name__ == "__main__":
    txs = get_txs(1)
    txs = [tx.decode("latin-1") for tx in txs]
    i = 0
    print(txs)
    while True:
        if i >= len(txs):
            break
        # rand = random.randint(10, 100)
        rand = 2
        print(f"processing txs {i}:{i+rand} from total {len(txs)} txs")
        requests.post("http://localhost:8000/api/txs", json=txs[i : i + rand])
        i += rand
        time.sleep(0.1)
