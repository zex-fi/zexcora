from struct import pack
from threading import Lock, Thread

from bot import PAIRS, ZexBot

DEPOSIT, WITHDRAW, BUY, SELL, CANCEL = b"dwbsc"

version = pack(">B", 1)

private_seed = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebac"
private_seed_int = int.from_bytes(bytearray.fromhex(private_seed), byteorder="big")


def start_threads() -> list[tuple[Thread, ZexBot]]:
    threads: list[tuple[Thread, ZexBot]] = []
    bot1_lock = Lock()
    bot2_lock = Lock()
    idx = 0
    for base_chain, x in PAIRS.items():
        for base_token_id, y in x.items():
            for quote_chain, z in y.items():
                for quote_token_id, bid_ask_digits in z.items():
                    print(
                        f"{base_chain}:{base_token_id}-{quote_chain}:{quote_token_id}"
                    )
                    buyer_bot = ZexBot(
                        private_key=(private_seed_int + idx).to_bytes(32, "big"),
                        pair=f"{base_chain}:{base_token_id}-{quote_chain}:{quote_token_id}",
                        side="buy",
                        best_bid=bid_ask_digits["bid"],
                        best_ask=bid_ask_digits["ask"],
                        volume_digits=bid_ask_digits["volume_digits"],
                        price_digits=bid_ask_digits["price_digits"],
                        lock=bot1_lock,
                        seed=idx,
                    )
                    seller_bot = ZexBot(
                        private_key=(private_seed_int + idx + 1).to_bytes(32, "big"),
                        pair=f"{base_chain}:{base_token_id}-{quote_chain}:{quote_token_id}",
                        side="sell",
                        best_bid=bid_ask_digits["bid"],
                        best_ask=bid_ask_digits["ask"],
                        volume_digits=bid_ask_digits["volume_digits"],
                        price_digits=bid_ask_digits["price_digits"],
                        lock=bot2_lock,
                        seed=idx + 1,
                    )
                    t1 = Thread(target=buyer_bot.run)
                    t2 = Thread(target=seller_bot.run)
                    t1.start()
                    t2.start()
                    threads.extend([(t1, buyer_bot), (t2, seller_bot)])
                    idx += 2
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
