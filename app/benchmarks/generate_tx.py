from collections import deque
from struct import pack
from threading import Lock
import asyncio
import inspect
import json
import multiprocessing as mp
import random
import time

from colorama import init as colorama_init
from eth_hash.auto import keccak
from line_profiler import LineProfiler
from loguru import logger
from secp256k1 import PrivateKey
from termcolor import colored
from tqdm import trange
from zellular import Zellular
import numpy as np

from app.api.routes.system import create_zellular_instance
from app.config import settings
from app.models.transaction import Deposit, DepositTransaction
from app.zex import Market, Zex

colorama_init()

BTC_DEPOSIT, DEPOSIT, WITHDRAW, BUY, SELL, CANCEL, REGISTER = b"xdwbscr"
version = pack(">B", 1)
rng = random.Random(None)

mid_price = 2000

u1_private = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebad"
u2_private = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebac"

logger.remove()
zex = Zex.initialize_zex()


class Bot:
    def __init__(
        self,
        private_key: bytes,
        pair: str,
        side: str,
        volume_digits: int,
        price_digits: int,
        lock: Lock,
        seed: int | None = 1,
    ):
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
        self.nonce = 0

    def create_order(
        self,
        price: float | int,
        volume: float,
        verbose=True,
    ):
        pair = self.pair.replace("-", "")
        base_token, quote_token = self.pair.split("-")
        tx = (
            version
            + pack(">B", BUY if self.side == "buy" else SELL)
            + pack(">B", len(base_token))
            + pack(">B", len(quote_token))
            + pair.encode()
            + pack(">d", volume)
            + pack(">d", price)
        )
        if verbose:
            print(
                f"pair: {self.pair}, none: {self.nonce}, side: {self.side}, price: {price}, vol: {volume}"
            )
        name = tx[1]
        t = int(time.time())
        tx += pack(">II", t, self.nonce) + self.pubkey
        msg = "v: 1\n"
        msg += f'name: {"buy" if name == BUY else "sell"}\n'
        msg += f"base token: {base_token}\n"
        msg += f"quote token: {quote_token}\n"
        msg += f'amount: {np.format_float_positional(volume, trim="0")}\n'
        msg += f'price: {np.format_float_positional(price, trim="0")}\n'
        msg += f"t: {t}\n"
        msg += f"nonce: {self.nonce}\n"
        msg += f"public: {self.pubkey.hex()}\n"
        msg = "\x19Ethereum Signed Message:\n" + str(len(msg)) + msg
        self.nonce += 1
        sig = self.privkey.ecdsa_sign(keccak(msg.encode("ascii")), raw=True)
        sig = self.privkey.ecdsa_serialize_compact(sig)
        tx += sig

        if verbose:
            print(msg)
            print(tx)
        return tx


def generate_transaction_batch(
    zellular: Zellular,
    buyer_bot: Bot,
    seller_bot: Bot,
    batch_size,
    count,
):
    all_txs = [
        [
            tx
            for _ in range(batch_size // 2)
            for tx in [
                buyer_bot.create_order(
                    mid_price + 1,
                    volume=round(rng.uniform(0.1, 0.5), 4),
                    verbose=False,
                ).decode("latin-1"),
                seller_bot.create_order(
                    mid_price - 1,
                    round(rng.uniform(0.1, 0.5), 4),
                    verbose=False,
                ).decode("latin-1"),
            ]
        ]
        for _ in trange(count)
    ]
    input("press enter to start sending tx to zsequencer...")
    start_time = time.time()
    for batch in all_txs:
        zellular.send(batch)
        time.sleep(batch_size / (100_000 / 1.1))
    end_time = time.time()

    total_time = end_time - start_time
    print(
        f"total time {colored(str(total_time), 'green')} for sending {colored(str(len(all_txs)), attrs=['bold'])} batches of transaction"
    )


if __name__ == "__main__":
    settings.zex.sequencer_mode = "local"
    zellular = create_zellular_instance()

    buyer_bot = Bot(
        bytes.fromhex(u1_private), "zEIGEN-zUSDT", "buy", 4, 4, Lock(), seed=1
    )
    seller_bot = Bot(
        bytes.fromhex(u2_private), "zEIGEN-zUSDT", "sell", 4, 4, Lock(), seed=2
    )

    all_txs = [
        buyer_bot.create_order(
            mid_price - 1,
            volume=10000,
            verbose=False,
        ).decode("latin-1"),
        seller_bot.create_order(
            mid_price + 1,
            volume=10000,
            verbose=False,
        ).decode("latin-1"),
    ]
    zellular.send(all_txs)

    count = 1000
    generate_transaction_batch(zellular, buyer_bot, seller_bot, 1000, count)
