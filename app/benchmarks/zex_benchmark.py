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
from zellular import Zellular
import numpy as np

from ..api.routes.system import create_zellular_instance
from ..config import settings
from ..models.transaction import Deposit, DepositTransaction
from ..verify import TransactionVerifier
from ..zex import Market, Zex

colorama_init()

DEPOSIT, WITHDRAW, BUY, SELL, CANCEL, REGISTER = b"dwbscr"
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
        msg += f"name: {'buy' if name == BUY else 'sell'}\n"
        msg += f"base token: {base_token}\n"
        msg += f"quote token: {quote_token}\n"
        msg += f"amount: {np.format_float_positional(volume, trim='0')}\n"
        msg += f"price: {np.format_float_positional(price, trim='0')}\n"
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


def initialize() -> tuple[Zex, Bot, Bot]:
    public1 = PrivateKey(
        bytes(bytearray.fromhex(u1_private)), raw=True
    ).pubkey.serialize()
    public2 = PrivateKey(
        bytes(bytearray.fromhex(u2_private)), raw=True
    ).pubkey.serialize()

    zex.benchmark_mode = True

    zex.state_manager.assets["zEIGEN"] = {}
    zex.state_manager.assets["zEIGEN"][public2] = 150000000000000
    zex.state_manager.assets["zUSDT"] = {}
    zex.state_manager.assets["zUSDT"][public1] = 200000000000000
    order_book = Market("zEIGEN", "zUSDT", zex)
    zex.state_manager.markets["zEIGEN-zUSDT"] = order_book

    zex.trades[public1] = deque()
    zex.orders[public1] = set()
    zex.nonces[public1] = 0

    zex.trades[public2] = deque()
    zex.orders[public2] = set()
    zex.nonces[public2] = 0

    buyer_bot = Bot(
        bytes.fromhex(u1_private), "zEIGEN-zUSDT", "buy", 2, 2, Lock(), seed=1
    )
    seller_bot = Bot(
        bytes.fromhex(u2_private), "zEIGEN-zUSDT", "sell", 2, 2, Lock(), seed=2
    )

    return zex, buyer_bot, seller_bot


async def test_maker_only():
    zex, buyer_bot, seller_bot = initialize()

    num_transactions = 100_000
    all_txs = [
        tx
        for i in range(num_transactions // 2)
        for tx in [
            buyer_bot.create_order(
                round(rng.uniform(1000, mid_price - 1), 2),
                round(rng.uniform(0.1, 1), 4),
                verbose=False,
            ),
            seller_bot.create_order(
                round(rng.uniform(mid_price + 1, 3000), 2),
                round(rng.uniform(0.1, 1), 4),
                verbose=False,
            ),
        ]
    ]

    print("starting place order benchmark...")
    start_time = time.time()
    zex.process(all_txs, last_tx_index=len(all_txs) - 1)
    end_time = time.time()

    total_time = end_time - start_time

    print(
        f"total time {colored(str(total_time), 'green')} for {colored(str(num_transactions), attrs=['bold'])} transactions"
    )


async def test_taker_only_half_empty_order_book():
    zex, buyer_bot, seller_bot = initialize()

    num_transactions = 100_000
    all_txs = [
        tx
        for i in range(num_transactions // 2)
        for tx in [
            buyer_bot.create_order(
                1234.56,
                0.1,
                verbose=False,
            ),
            seller_bot.create_order(
                1234.56,
                0.1,
                verbose=False,
            ),
        ]
    ]
    zex.deposit(
        DepositTransaction(
            version=1,
            operation="d",
            chain="HOL",
            deposits=[
                Deposit(
                    tx_hash="0x01",
                    chain="HOL",
                    token_contract="0x325CCd77e71Ac296892ed5C63bA428700ec0f868",
                    amount=1_000_000,
                    decimal=6,
                    time=int(time.time()),
                    user_id=1,
                    vout=0,
                ),
                Deposit(
                    tx_hash="0x02",
                    chain="HOL",
                    token_contract="0x219f1708400bE5b8cC47A56ed2f18536F5Da7EF4",
                    amount=1_000_000,
                    decimal=18,
                    time=int(time.time()),
                    user_id=1,
                    vout=0,
                ),
                Deposit(
                    tx_hash="0x03",
                    chain="HOL",
                    token_contract="0x325CCd77e71Ac296892ed5C63bA428700ec0f868",
                    amount=1_000_000,
                    decimal=6,
                    time=int(time.time()),
                    user_id=2,
                    vout=0,
                ),
                Deposit(
                    tx_hash="0x04",
                    chain="HOL",
                    token_contract="0x219f1708400bE5b8cC47A56ed2f18536F5Da7EF4",
                    amount=1_000_000,
                    decimal=18,
                    time=int(time.time()),
                    user_id=2,
                    vout=0,
                ),
            ],
        )
    )

    print("starting half empty order book benchmark...")
    start_time = time.time()

    zex.process(all_txs, last_tx_index=len(all_txs) - 1)

    end_time = time.time()

    total_time = end_time - start_time

    print(
        f"total time {colored(str(total_time), 'green')} for {colored(str(num_transactions), attrs=['bold'])} transactions"
    )


async def test_taker_only_random_volume():
    zex, buyer_bot, seller_bot = initialize()

    num_transactions = 100_000
    all_txs = [
        buyer_bot.create_order(
            mid_price - 1,
            volume=10000,
            verbose=False,
        ),
        seller_bot.create_order(
            mid_price + 1,
            volume=10000,
            verbose=False,
        ),
    ]
    all_txs += [
        tx
        for i in range(num_transactions // 2)
        for tx in [
            buyer_bot.create_order(
                mid_price + 1,
                volume=round(rng.uniform(0.1, 0.5), 4),
                verbose=False,
            ),
            seller_bot.create_order(
                mid_price - 1,
                round(rng.uniform(0.1, 0.5), 4),
                verbose=False,
            ),
        ]
    ]
    print("starting full benchmark...")
    start_time = time.time()
    zex.process(all_txs, last_tx_index=len(all_txs) - 1)
    end_time = time.time()

    total_time = end_time - start_time

    print(
        f"total time {colored(str(total_time), 'green')} for {colored(str(num_transactions), attrs=['bold'])} transactions"
    )


def pull_batches(zellular: Zellular, zellular_queue: mp.Queue, after: int):
    for batch, index in zellular.batches(after=after):
        zellular_queue.put((batch, index))


def verify_batches(zellular_queue: mp.Queue, queue: mp.Queue):
    verifier = TransactionVerifier(num_processes=8)
    while True:
        batch, index = zellular_queue.get()

        txs: list[str] = json.loads(batch)
        finalized_txs = [x.encode("latin-1") for x in txs]
        verified_txs = verifier.verify(finalized_txs)
        queue.put((verified_txs, index))


def test_throughput_taker_only_random_volume():
    settings.zex.sequencer_mode = "local"
    zellular = create_zellular_instance()

    zex, _, _ = initialize()
    zellular_queue = mp.Queue(1000)
    queue = mp.Queue(1000)
    pull_process = mp.Process(target=pull_batches, args=(zellular, zellular_queue, 0))
    verify_process = mp.Process(target=verify_batches, args=(zellular_queue, queue))
    pull_process.start()
    verify_process.start()

    count = 1000
    while True:
        item = queue.get()
        start_time = time.time()

        if item is None:
            break
        if zex.last_tx_index >= count:
            break

        verified_txs, index = item

        zex.last_tx_index = index
        # zex.process(verified_txs, index)

        end_time = time.time()
        total_time = end_time - start_time
        print(
            f"total time {colored(str(total_time), 'green')} for {colored(str(zex.last_tx_index), attrs=['bold'])} transactions"
        )


if __name__ == "__main__":
    # profiler = LineProfiler()
    # # Add all methods to the profiler
    # for name, method in inspect.getmembers(Zex, predicate=inspect.isfunction):
    #     profiler.add_function(method)
    # # Add all methods to the profiler
    # for name, method in inspect.getmembers(Market, predicate=inspect.isfunction):
    #     profiler.add_function(method)
    # profiler.enable_by_count()

    # asyncio.run(test_maker_only())
    # print("------------------------------")
    # asyncio.run(test_taker_only_half_empty_order_book())
    # print("------------------------------")
    # asyncio.run(test_taker_only_random_volume())

    test_throughput_taker_only_random_volume()

    # profiler.disable_by_count()
    # profiler.print_stats(sort=True)
