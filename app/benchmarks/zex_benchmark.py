from collections import deque
from threading import Lock
import random
import time

from colorama import init as colorama_init
from secp256k1 import PrivateKey
from termcolor import colored

from app import zex
from app.zex import Market, Zex
from bot import ZexBot

colorama_init()

rng = random.Random(None)

mid_price = 2000

u1_private = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebad"
u2_private = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebac"


def initialize() -> tuple[Zex, ZexBot, ZexBot]:
    public1 = PrivateKey(
        bytes(bytearray.fromhex(u1_private)), raw=True
    ).pubkey.serialize()
    public2 = PrivateKey(
        bytes(bytearray.fromhex(u2_private)), raw=True
    ).pubkey.serialize()

    zex.benchmark_mode = True

    zex.assets["LINK"] = {}
    zex.assets["LINK"][public2] = 150000000000000
    zex.assets["USDT"] = {}
    zex.assets["USDT"][public1] = 200000000000000
    order_book = Market("LINK", "USDT", zex)
    zex.markets["LINK-USDT"] = order_book

    zex.trades[public1] = deque()
    zex.orders[public1] = {}
    zex.nonces[public1] = 0

    zex.trades[public2] = deque()
    zex.orders[public2] = {}
    zex.nonces[public2] = 0

    buyer_bot = ZexBot(bytes.fromhex(u1_private), "LINK-USDT", "buy", 169, 171, 5, 4)
    seller_bot = ZexBot(bytes.fromhex(u2_private), "LINK-USDT", "sell", 169, 171, 5, 4)

    return zex, buyer_bot, seller_bot


def test_maker_only():
    zex, buyer_bot, seller_bot = initialize()

    num_transactions = 100_000
    all_txs = [
        tx
        for i in range(num_transactions // 2)
        for tx in [
            buyer_bot.create_order(
                round(rng.uniform(1000, mid_price - 1), 2),
                round(rng.uniform(0.1, 1), 4),
                maker=True,
                verbose=False,
            ),
            seller_bot.create_order(
                round(rng.uniform(mid_price + 1, 3000), 2),
                round(rng.uniform(0.1, 1), 4),
                maker=True,
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


def test_taker_only_half_empty_order_book():
    zex, buyer_bot, seller_bot = initialize()

    num_transactions = 100_000
    all_txs = [
        tx
        for i in range(num_transactions // 2)
        for tx in [
            buyer_bot.create_order(
                1234.56,
                0.1,
                maker=True,
                verbose=False,
            ),
            seller_bot.create_order(
                1234.56,
                0.1,
                maker=True,
                verbose=False,
            ),
        ]
    ]

    print("starting half empty order book benchmark...")
    start_time = time.time()
    zex.process(all_txs, last_tx_index=len(all_txs) - 1)
    end_time = time.time()

    total_time = end_time - start_time

    print(
        f"total time {colored(str(total_time), 'green')} for {colored(str(num_transactions), attrs=['bold'])} transactions"
    )


def test_taker_only_random_volume():
    zex, buyer_bot, seller_bot = initialize()

    num_transactions = 100_000
    all_txs = [
        buyer_bot.create_order(
            mid_price - 1,
            volume=10000,
            maker=False,
            verbose=False,
        ),
        seller_bot.create_order(
            mid_price + 1,
            volume=10000,
            maker=False,
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
                maker=False,
                verbose=False,
            ),
            seller_bot.create_order(
                mid_price - 1,
                round(rng.uniform(0.1, 0.5), 4),
                maker=False,
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


if __name__ == "__main__":
    # test_maker_only()
    # print("------------------------------")
    test_taker_only_half_empty_order_book()
    # print("------------------------------")
    # test_taker_only_random_volume()
