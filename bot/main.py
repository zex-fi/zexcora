from struct import pack
from threading import Lock, Thread

from bot import PAIRS, ZexBot

DEPOSIT, WITHDRAW, BUY, SELL, CANCEL = b"dwbsc"

version = pack(">B", 1)

private_seed = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebac"
private_seed_int = int.from_bytes(bytearray.fromhex(private_seed), byteorder="big")


def start_threads() -> list[tuple[Thread, ZexBot]]:
    threads: list[tuple[Thread, ZexBot]] = []
    lock = Lock()
    for pair in PAIRS:
        buyer_bot = ZexBot(
            private_key=private_seed_int.to_bytes(32, "big"),
            pair=pair["pair"],
            side="buy",
            binance_name=pair["binance_name"],
            volume_digits=pair["volume_digits"],
            price_digits=pair["price_digits"],
            lock=lock,
            seed=0,
        )
        seller_bot = ZexBot(
            private_key=private_seed_int.to_bytes(32, "big"),
            pair=pair["pair"],
            side="sell",
            binance_name=pair["binance_name"],
            volume_digits=pair["volume_digits"],
            price_digits=pair["price_digits"],
            lock=lock,
            seed=1,
        )
        print(
            f"buyer id: {buyer_bot.user_id}, seller id: {seller_bot.user_id}, pair: {pair}"
        )
        t1 = Thread(target=buyer_bot.run)
        t2 = Thread(target=seller_bot.run)
        t1.start()
        t2.start()
        threads.extend([(t1, buyer_bot), (t2, seller_bot)])
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
