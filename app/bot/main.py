import os
from struct import pack
from threading import Lock, Thread

from app.bot import ZexBot
from app.bot.markets import QUOTES, BASES, BEST_BIDS, BEST_ASKS

DEPOSIT, WITHDRAW, BUY, SELL, CANCEL = b"dwbsc"

version = pack(">B", 1)

private_seed = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebac"
private_seed_int = int.from_bytes(bytearray.fromhex(private_seed), byteorder="big")

ip = os.getenv("HOST")
port = int(os.getenv("PORT"))


if __name__ == "__main__":
    threads: list[Thread] = []
    bot1_lock = Lock()
    bot2_lock = Lock()
    idx = 0
    for quote_chain, quote_token_ids in QUOTES.items():
        for quote_token_id in quote_token_ids:
            for base_chain, base_token_ids in BASES.items():
                for base_token_id in base_token_ids:
                    buyer_bot = ZexBot(
                        private_key=(private_seed_int + idx).to_bytes(32, "big"),
                        pair=f"{base_chain}:{base_token_id}-{quote_chain}:{quote_token_id}",
                        side="buy",
                        best_bid=BEST_BIDS[base_chain][base_token_id][quote_chain][
                            quote_token_id
                        ],
                        best_ask=BEST_ASKS[base_chain][base_token_id][quote_chain][
                            quote_token_id
                        ],
                        lock=bot1_lock,
                        seed=idx,
                    )
                    seller_bot = ZexBot(
                        private_key=(private_seed_int + idx + 1).to_bytes(32, "big"),
                        pair=f"{base_chain}:{base_token_id}-{quote_chain}:{quote_token_id}",
                        side="sell",
                        best_bid=BEST_BIDS[base_chain][base_token_id][quote_chain][
                            quote_token_id
                        ],
                        best_ask=BEST_ASKS[base_chain][base_token_id][quote_chain][
                            quote_token_id
                        ],
                        lock=bot2_lock,
                        seed=idx + 1,
                    )
                    t1 = Thread(target=buyer_bot.run)
                    t2 = Thread(target=seller_bot.run)
                    t1.start()
                    t2.start()
                    threads.extend([t1, t2])
                    idx += 2
    for t in threads:
        t.join()
