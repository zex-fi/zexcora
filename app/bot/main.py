import os
from struct import pack
from threading import Lock, Thread

from app.bot import ZexBot

DEPOSIT, WITHDRAW, BUY, SELL, CANCEL = b"dwbsc"

version = pack(">B", 1)

u1_private = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebad"
u2_private = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebac"
ip = os.getenv("HOST")
port = int(os.getenv("PORT"))


if __name__ == "__main__":
    threads: list[Thread] = []
    bot1_lock = Lock()
    bot2_lock = Lock()
    idx = 0
    for quote_chain in ["HOL"]:
        for quote_token_id in [1, 2, 3, 4]:
            for base_chain, token_ids in [
                ("BST", [1, 2, 3, 4, 5, 6]),
                ("SEP", [1, 2, 3, 4]),
            ]:
                for base_token_id in token_ids:
                    print(
                        f"{base_chain}:{base_token_id}-{quote_chain}:{quote_token_id}"
                    )
                    buyer_bot = ZexBot(
                        u1_private,
                        f"{base_chain}:{base_token_id}-{quote_chain}:{quote_token_id}",
                        "buy",
                        bot1_lock,
                        idx,
                    )
                    seller_bot = ZexBot(
                        u2_private,
                        f"{base_chain}:{base_token_id}-{quote_chain}:{quote_token_id}",
                        "sell",
                        bot2_lock,
                        idx + 1,
                    )
                    t1 = Thread(target=buyer_bot.run)
                    t2 = Thread(target=seller_bot.run)
                    t1.start()
                    t2.start()
                    threads.extend([t1, t2])
                    idx += 2
    for t in threads:
        t.join()
