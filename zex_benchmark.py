from collections import deque
import random
import time
from secp256k1 import PrivateKey
from bot.bot import ZexBot
from zex import OrderBook, Zex

rng = random.Random(None)

mid_price = 2000

u1_private = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebad"
u2_private = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebac"


def kline_callback(kline):
    pass


def depth_callback(depth):
    pass


def run_maker_only_test():
    public1 = PrivateKey(
        bytes(bytearray.fromhex(u1_private)), raw=True
    ).pubkey.serialize()
    public2 = PrivateKey(
        bytes(bytearray.fromhex(u2_private)), raw=True
    ).pubkey.serialize()
    zex = Zex(
        kline_callback=kline_callback,
        depth_callback=depth_callback,
        benchmark_mode=True,
    )
    order_book = OrderBook("bst:1", "bst:2", zex)
    zex.orderbooks["bst:1-bst:2"] = order_book
    zex.balances["bst:1"] = {}
    zex.balances["bst:1"][public2] = 150000000000000
    zex.balances["bst:2"] = {}
    zex.balances["bst:2"][public1] = 200000000000000

    zex.trades[public1] = deque()
    zex.orders[public1] = {}
    zex.nonces[public1] = 0

    zex.trades[public2] = deque()
    zex.orders[public2] = {}
    zex.nonces[public2] = 0

    buyer_bot = ZexBot(u1_private, "bst", 2, "bst:1-bst:2", "buy", 1)
    seller_bot = ZexBot(u2_private, "bst", 1, "bst:1-bst:2", "sell", 2)

    num_transactions = 100_000
    total_time = 0
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
    zex.process(all_txs)
    end_time = time.time()

    total_time += end_time - start_time

    print(f"\ntotal time {total_time} for {num_transactions} transactions")


def run_taker_only_test():
    public1 = PrivateKey(
        bytes(bytearray.fromhex(u1_private)), raw=True
    ).pubkey.serialize()
    public2 = PrivateKey(
        bytes(bytearray.fromhex(u2_private)), raw=True
    ).pubkey.serialize()
    zex = Zex(
        kline_callback=kline_callback,
        depth_callback=depth_callback,
        benchmark_mode=True,
    )

    order_book = OrderBook("bst:1", "bst:2", zex)
    zex.orderbooks["bst:1-bst:2"] = order_book
    zex.balances["bst:1"] = {}
    zex.balances["bst:1"][public2] = 200000000000000000000
    zex.balances["bst:2"] = {}
    zex.balances["bst:2"][public1] = 200000000000000000000

    zex.trades[public1] = deque()
    zex.orders[public1] = {}
    zex.nonces[public1] = 0

    zex.trades[public2] = deque()
    zex.orders[public2] = {}
    zex.nonces[public2] = 0

    buyer_bot = ZexBot(u1_private, "bst", 2, "bst:1-bst:2", "buy", 1)
    seller_bot = ZexBot(u2_private, "bst", 1, "bst:1-bst:2", "sell", 2)

    num_transactions = 100_000
    total_time = 0
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
    zex.process(all_txs)
    end_time = time.time()

    total_time += end_time - start_time

    print(f"\ntotal time {total_time} for {num_transactions} transactions")


if __name__ == "__main__":
    run_maker_only_test()
    run_taker_only_test()
