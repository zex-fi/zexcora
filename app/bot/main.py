import os
from struct import pack
from threading import Thread

from app.bot import ZexBot

DEPOSIT, WITHDRAW, BUY, SELL, CANCEL = b"dwbsc"

version = pack(">B", 1)

u1_private = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebad"
u2_private = "31a84594060e103f5a63eb742bd46cf5f5900d8406e2726dedfc61c7cf43ebac"
ip = os.getenv("HOST")
port = int(os.getenv("PORT"))


if __name__ == "__main__":
    buyer_bot = ZexBot(u1_private, "bst", 2, "bst:1-bst:2", "buy", 1)
    seller_bot = ZexBot(u2_private, "bst", 1, "bst:1-bst:2", "sell", 2)
    t1 = Thread(target=buyer_bot.run)
    t2 = Thread(target=seller_bot.run)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
