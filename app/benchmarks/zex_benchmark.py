from collections import deque
from threading import Lock
import asyncio
import random
import time

from colorama import init as colorama_init
from secp256k1 import PrivateKey
from termcolor import colored

from app.models.transaction import Deposit, DepositTransaction
from app.zex import Market, Zex
from bot import ZexBot

colorama_init()

rng = random.Random(None)

mid_price = 2000

u1_private = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebad"
u2_private = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebac"

zex = Zex.initialize_zex()


def initialize() -> tuple[Zex, ZexBot, ZexBot]:
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
    zex.orders[public1] = {}
    zex.nonces[public1] = 0

    zex.trades[public2] = deque()
    zex.orders[public2] = {}
    zex.nonces[public2] = 0

    buyer_bot = ZexBot(
        bytes.fromhex(u1_private), "zEIGEN-zUSDT", "EIGENUSDT", "buy", 2, 2, Lock()
    )
    seller_bot = ZexBot(
        bytes.fromhex(u2_private),
        "zEIGEN-zUSDT",
        "EIGENUSDT",
        "sell",
        2,
        2,
        Lock(),
    )

    return zex, buyer_bot, seller_bot


async def test_maker_only():
    zex, buyer_bot, seller_bot = initialize()
    buyer_bot.update_nonce()
    seller_bot.update_nonce()

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


async def test_taker_only_half_empty_order_book():
    zex, buyer_bot, seller_bot = initialize()
    buyer_bot.update_nonce()
    seller_bot.update_nonce()

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


def test_taker_only_random_volume():
    zex, buyer_bot, seller_bot = initialize()
    buyer_bot.update_nonce()
    seller_bot.update_nonce()

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
    asyncio.run(test_maker_only())
    # print("------------------------------")
    # asyncio.run(test_taker_only_half_empty_order_book())
    # print("------------------------------")
    # test_taker_only_random_volume()
