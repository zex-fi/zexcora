from struct import pack
from threading import Thread
import time

from markets import PAIRS
from zex_bot import ZexBot

DEPOSIT, WITHDRAW, BUY, SELL, CANCEL = b"dwbsc"

version = pack(">B", 1)

private_seed = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebac"
private_seed_int = int.from_bytes(bytearray.fromhex(private_seed), byteorder="big")


def new_private(offset):
    return (private_seed_int + offset).to_bytes(32, "big")


def start_threads() -> list[tuple[Thread, ZexBot]]:
    threads: list[tuple[Thread, ZexBot]] = []
    for pair in PAIRS:
        j = len(threads)
        for i in range(0, 2, 2):
            buyer_bot = ZexBot(
                private_key=new_private(j + i),
                pair=pair["pair"],
                side="buy",
                binance_name=pair["binance_name"],
                volume_digits=pair["volume_digits"],
                price_digits=pair["price_digits"],
                seed=i,
            )
            seller_bot = ZexBot(
                private_key=new_private(j + i + 1),
                pair=pair["pair"],
                side="sell",
                binance_name=pair["binance_name"],
                volume_digits=pair["volume_digits"],
                price_digits=pair["price_digits"],
                seed=i + 1,
            )

            t1 = Thread(target=buyer_bot.run)
            t2 = Thread(target=seller_bot.run)
            threads.extend([(t1, buyer_bot), (t2, seller_bot)])

    for t, _ in threads:
        t.start()
        time.sleep(0.5)

    return threads


if __name__ == "__main__":
    threads = start_threads()
    try:
        for t, _ in threads:
            t.join()
    except KeyboardInterrupt:
        print("KeyboardInterrupt received, stopping bots...")
        for _, bot in threads:
            bot.is_running = False

    # Wait for all threads to finish
    for t, _ in threads:
        t.join()
    print("All bots stopped.")
