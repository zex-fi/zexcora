import hashlib
import copy
import json
import time
import random
import requests
from struct import pack, unpack
from secp256k1 import PrivateKey, PublicKey
from zex import BUY, SELL, CANCEL, DEPOSIT, WITHDRAW

tokens = {
    'pol:usdt': b'pol' + pack('>I', 0),
    'eth:wbtc': b'eth' + pack('>I', 0)
}

version = pack('>B', 1)

u1_private =      '31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebad'
u2_private =      '31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebac'
monitor_private = 'cd7d94cd90d25d8722087a85e51ce3e5d8d06d98cb9f1c02e93f646c90af0193'

u1 =      PrivateKey(bytes(bytearray.fromhex(u1_private     )), raw=True)
u2 =      PrivateKey(bytes(bytearray.fromhex(u2_private     )), raw=True)
monitor = PrivateKey(bytes(bytearray.fromhex(monitor_private)), raw=True)

pub = lambda u: u.pubkey.serialize()
print(pub(u1).hex())
print(pub(u2).hex())
privs = { pub(u1): u1, pub(u2): u2 }

deposit_usdt = tokens['pol:usdt'][3:] + pack('>d', 1500000000)
deposit_wbtc = tokens['eth:wbtc'][3:] + pack('>d', 1000000   )

buy  = pack('>B', BUY ) + tokens['eth:wbtc'] + tokens['pol:usdt'] + pack('>d', 0.01) + pack('>d', 70000)
sell = pack('>B', SELL) + tokens['eth:wbtc'] + tokens['pol:usdt'] + pack('>d', 0.01) + pack('>d', 70000)


# cancel = chr(CANCEL).encode() + txs[-2][:66]
# txs.insert(3, cancel)

nonces = { pub(u1): 0, pub(u2): 0 }
deposit_nonces = { b'pol': 0, b'eth': 0 }
counter = 0

def deposit(tx):
    global counter
    t = pack('>I', int(time.time()))
    chain  = b'pol'  if tx == deposit_usdt else b'eth'
    public = pub(u1) if tx == deposit_usdt else pub(u2)
    block_range = pack('>QQ', 1, 5)
    count = 10
    chunk = (tx + t + public) * count
    tx = version + pack('>B', DEPOSIT) + chain + block_range + pack('>H', count)
    tx += chunk
    tx += monitor.schnorr_sign(tx, bip340tag='zex')
    tx += pack('>Q', counter)
    counter += 1
    return tx

def order(tx):
    global counter
    tx = version + tx
    name = tx[1]
    public = pub(u2) if name == SELL else pub(u1)
    t = int(time.time())
    tx += pack('>II', t, nonces[public]) + public
    msg = 'v: 1\n'
    msg += f'name: {"buy" if name == BUY else "sell"}\n'
    msg += f'base token: {tx[2:5].decode("ascii")}:{unpack(">I", tx[5:9])[0]}\n'
    msg += f'quote token: {tx[9:12].decode("ascii")}:{unpack(">I", tx[12:16])[0]}\n'
    msg += f'amount: {unpack(">d", tx[16:24])[0]}\n'
    msg += f'price: {unpack(">d", tx[24:32])[0]}\n'
    msg += f't: {t}\n'
    msg += f'nonce: {nonces[public]}\n'
    msg += f'public: {public.hex()}\n'
    msg = '\x19Ethereum Signed Message:\n' + str(len(msg)) + msg
    nonces[public] += 1
    u = privs[public]
    sig = u.ecdsa_sign(msg.encode('ascii'))
    sig = u.ecdsa_serialize_compact(sig)
    tx += sig
    tx += pack('>Q', counter)
    counter += 1
    return tx

def get_txs(n):
    txs = [deposit(deposit_usdt), deposit(deposit_wbtc)]
    for i in range(n):
        txs.append(order(buy))
        txs.append(order(sell))
    return txs

if __name__ == '__main__':
    txs = get_txs(2)
    txs = [tx.decode('latin-1') for tx in txs]
    i = 0
    while True:
        if i >= len(txs): break
        rand = random.randint(10, 100)
        print(f'processing txs {i}:{i+rand} from total {len(txs)} txs')
        requests.post('http://localhost:9513/api/txs', json=txs[i:i+rand])
        i += rand
        time.sleep(1)