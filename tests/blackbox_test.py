from struct import pack, unpack
from threading import Thread
import asyncio
import os
import time

from eth_hash.auto import keccak
from fastapi.testclient import TestClient
from secp256k1 import PrivateKey
import numpy as np
import pytest

from app import stop_event

# Import your FastAPI app
from app.api.routes.system import process_loop, transmit_tx
from app.main import app
from app.verify import TransactionVerifier
from app.zex import Zex

DEPOSIT, WITHDRAW, BUY, SELL, CANCEL = b"dwbsc"
version = pack(">B", 1)

private_seed = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebac"
private_seed_int = int.from_bytes(bytearray.fromhex(private_seed), byteorder="big")
app_name = "zex"
client = TestClient(app)


initial_exchange_info = {
    "chains": [],
    "symbols": [],
    "timezone": "UTC",
    "tokens": [],
}


def create_order(
    privkey: PrivateKey,
    pair: str,
    side: str,
    price: float | int,
    volume: float,
    nonce: int,
    counter: int,
    verbose=True,
):
    tx = (
        pack(">B", BUY if side == "buy" else SELL)
        + pair[:3].encode()
        + pack(">I", int(pair[4]))
        + pair[6:9].encode()
        + pack(">I", int(pair[10]))
        + pack(">d", volume)
        + pack(">d", price)
    )
    if verbose:
        print(f"pair: {pair}, side: {side}, price: {price}, vol: {volume}")
    tx = version + tx
    name = tx[1]
    t = int(time.time())
    pubkey = privkey.pubkey.serialize()
    tx += pack(">II", t, nonce) + pubkey
    msg = "v: 1\n"
    msg += f'name: {"buy" if name == BUY else "sell"}\n'
    msg += f'base token: {tx[2:5].decode("ascii")}:{unpack(">I", tx[5:9])[0]}\n'
    msg += f'quote token: {tx[9:12].decode("ascii")}:{unpack(">I", tx[12:16])[0]}\n'
    msg += (
        f'amount: {np.format_float_positional(unpack(">d", tx[16:24])[0], trim="0")}\n'
    )
    msg += (
        f'price: {np.format_float_positional(unpack(">d", tx[24:32])[0], trim="0")}\n'
    )
    msg += f"t: {t}\n"
    msg += f"nonce: {nonce}\n"
    msg += f"public: {pubkey.hex()}\n"
    msg = "\x19Ethereum Signed Message:\n" + str(len(msg)) + msg
    sig = privkey.ecdsa_sign(keccak(msg.encode("ascii")), raw=True)
    sig = privkey.ecdsa_serialize_compact(sig)
    tx += sig
    tx += pack(">Q", counter)
    return tx


def create_cancel_order(privkey: PrivateKey, pubkey: bytes, order: bytes):
    tx = version + pack(">B", CANCEL) + order + pubkey
    msg = f"""v: {tx[0]}\nname: cancel\nslice: {tx[2:41].hex()}\npublic: {tx[41:74].hex()}\n"""
    msg = "".join(("\x19Ethereum Signed Message:\n", str(len(msg)), msg))

    sig = privkey.ecdsa_sign(keccak(msg.encode("ascii")), raw=True)
    sig = privkey.ecdsa_serialize_compact(sig)
    tx += sig
    return tx


@pytest.fixture(scope="session")
def redis_client(request):
    from redis import Redis

    redis_client = Redis(
        os.getenv("REDIS_HOST", "127.0.0.1"),
        int(os.getenv("REDIS_PORT", "7379")),
        db=0,
        password=os.getenv("REDIS_PASSWORD", "zex_super_secure_password"),
    )
    for _ in range(5):
        redis_client.ping()
        time.sleep(1)
    redis_client.flushall()
    return redis_client


@pytest.fixture(scope="package")
def zex_instance():
    zex = Zex()

    verifier = TransactionVerifier(num_processes=4)

    # server = TcpFakeServer(
    #     (os.getenv("REDIS_HOST", "127.0.0.1"), int(os.getenv("REDIS_PORT", "6379")))
    # )
    # t1 = Thread(target=server.serve_forever, daemon=True)
    t2 = Thread(
        target=asyncio.run,
        args=(transmit_tx(verifier),),
    )
    t3 = Thread(
        target=asyncio.run,
        args=(process_loop(verifier),),
    )

    # t1.start()
    t2.start()
    t3.start()

    yield zex

    stop_event.set()

    # server.shutdown()
    verifier.cleanup()
    # t1.join()
    t2.join()
    t3.join()


def test_get_exchange_info(zex_instance, redis_client):
    response = client.get("/v1/exchangeInfo")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "chains" in data
    assert "symbols" in data
    assert "timezone" in data
    assert "tokens" in data
    assert isinstance(data["tokens"], list)


def test_new_market_order(zex_instance: Zex, redis_client):
    assert redis_client.llen(app_name) == 0
    offset = 0
    private_key = (private_seed_int + offset).to_bytes(32, "big")
    privkey = PrivateKey(private_key, raw=True)
    xmr_usdt = "BTC:1-POL:1"
    tx = create_order(
        privkey, xmr_usdt, "buy", 170.2, 0.1, nonce=0, counter=0, verbose=False
    )
    response = client.post("/v1/order", json=[tx.decode("latin-1")])
    assert response.status_code == 200
    assert response.json() == {"success": True}
    time.sleep(5)

    assert redis_client.llen(app_name) == 1
