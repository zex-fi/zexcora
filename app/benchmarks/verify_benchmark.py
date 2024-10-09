import time

from app.verify import verify


def benchmark_multiprocessing(*args):
    # print(len(*args))
    start_time = time.time()
    verify(*args)
    end_time = time.time()
    return end_time - start_time


if __name__ == "__main__":
    num_runs = 10
    total_time = 0
    tx = (
        "\x01beth\x00\x00\x00\x00pol\x00\x00\x00\x00?\x84záG®\x14{"
        "@ñ\x17\x00\x00\x00\x00\x00f\x9bð|\x00\x00\x00\x00\x02\x08v\x02ç\x1a\x82wzz\x9c#Kf\x8a\x1dÉBÉ¢\x9bó\x1c\x93"
        "\x11Të3\x1c!¶öý/\x8cun\x11\x97i¼dÈÝþ\x06R\x06\x8b\x07ðý["
        'fuÊD\x82\x13\x1f^ÀGô¯\ró´\x96Èµ\x91cPÑ\xad\x81\x87\x020*Î¬õ\x1d\x92\x8a"¯\x99r\x95TJ;,'
        "É\x00\x00\x00\x00\x00\x00\x00\x00".encode("latin-1"),
        "\x01seth\x00\x00\x00\x00pol\x00\x00\x00\x00?\x94záG®\x14{"
        "@ñU\x80\x00\x00\x00\x00f\x9bð|\x00\x00\x00\x00\x03\x8cµ¢\x9c Â]¶Gb\x83\x13©\nÃå1\x86Ì&\x8fÿ\x91°à:*+\x18º¥P["
        "\x99\x8fj[Ú3§$Z\x8a`/\x19~ho\x89;³8¡Q³7¢.\x80YR¢\x83cúZ\x0bDÆPá\x84\x01f¦ðRù Å)\x9c¡ÊwêP|*\x14("
        "\x8e@\tÌ\x00\x00\x00\x00\x00\x00\x00\x01".encode("latin-1"),
    )
    for _ in range(num_runs):
        run_time = benchmark_multiprocessing([tx[i % len(tx)] for i in range(10000)])
        total_time += run_time
        # print(f"Run time: {run_time:.4f} seconds")

    average_time = total_time / num_runs
    print(
        f"\ntotal time {total_time}, Average time over {num_runs} runs: {average_time:.4f} seconds"
    )
