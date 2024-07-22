from collections import deque
import time
from zex import OrderBook, Zex


def kline_callback(kline):
    pass


def depth_callback(depth):
    pass


if __name__ == "__main__":
    public1 = b"\x02\x08v\x02\xe7\x1a\x82wzz\x9c#Kf\x8a\x1d\xc9B\xc9\xa2\x9b\xf3\x1c\x93\x11T\xeb3\x1c!\xb6\xf6\xfd"
    public2 = b"\x03\x8c\xb5\xa2\x9c \xc2]\xb6Gb\x83\x13\xa9\n\xc3\xe51\x86\xcc&\x8f\xff\x91\xb0\xe0:*+\x18\xba\xa5P"
    zex = Zex(kline_callback=kline_callback, depth_callback=depth_callback)
    order_book = OrderBook("eth:0", "pol:0", zex)
    zex.orderbooks["eth:0-pol:0"] = order_book
    zex.balances["eth:0"] = {}
    zex.balances["eth:0"][public2] = 150000000000000
    zex.balances["pol:0"] = {}
    zex.balances["pol:0"][public1] = 200000000000000

    zex.trades[public1] = deque()
    zex.orders[public1] = {}
    zex.nonces[public1] = 0

    zex.trades[public2] = deque()
    zex.orders[public2] = {}
    zex.nonces[public2] = 0

    num_runs = 100
    total_time = 0
    for _ in range(num_runs):
        tx = (
            '\x01beth\x00\x00\x00\x00pol\x00\x00\x00\x00?\x84záG®\x14{@ñ\x17\x00\x00\x00\x00\x00f\x9bð|\x00\x00\x00\x00\x02\x08v\x02ç\x1a\x82wzz\x9c#Kf\x8a\x1dÉBÉ¢\x9bó\x1c\x93\x11Të3\x1c!¶öý/\x8cun\x11\x97i¼dÈÝþ\x06R\x06\x8b\x07ðý[fuÊD\x82\x13\x1f^ÀGô¯\ró´\x96Èµ\x91cPÑ\xad\x81\x87\x020*Î¬õ\x1d\x92\x8a"¯\x99r\x95TJ;,É\x00\x00\x00\x00\x00\x00\x00\x00'.encode(
                "latin-1"
            ),
            "\x01seth\x00\x00\x00\x00pol\x00\x00\x00\x00?\x94záG®\x14{@ñU\x80\x00\x00\x00\x00f\x9bð|\x00\x00\x00\x00\x03\x8cµ¢\x9c Â]¶Gb\x83\x13©\nÃå1\x86Ì&\x8fÿ\x91°à:*+\x18º¥P[\x99\x8fj[Ú3§$Z\x8a`/\x19~ho\x89;³8¡Q³7¢.\x80YR¢\x83cúZ\x0bDÆPá\x84\x01f¦ðRù Å)\x9c¡ÊwêP|*\x14(\x8e@\tÌ\x00\x00\x00\x00\x00\x00\x00\x01".encode(
                "latin-1"
            ),
        )
        start_time = time.time()
        zex.process([tx[i % len(tx)] for i in range(10000)])
        end_time = time.time()

        total_time += end_time - start_time

    average_time = total_time / num_runs
    print(
        f"\ntotal time {total_time}, Average time over {num_runs} runs: {average_time:.4f} seconds"
    )
