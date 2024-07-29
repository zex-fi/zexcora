import asyncio
import time
from collections import deque
from threading import Lock

from fastapi import APIRouter
from loguru import logger

from app import zex

zseq_lock = Lock()
zseq_deque = deque()

router = APIRouter()


@router.get("/ping")
async def ping():
    return {}


@router.get("/time")
async def server_time():
    return {"serverTime": int(time.time() * 1000)}


@router.post("/txs")
def send_txs(txs: list[str]):
    with zseq_lock:
        zseq_deque.extend(txs)
    return {"success": True}


async def process_loop():
    index = 0
    while True:
        if len(zseq_deque) == 0:
            await asyncio.sleep(0.1)
            continue

        with zseq_lock:
            finalized_txs = [
                {"index": index + i, "tx": zseq_deque.popleft()}
                for i in range(len(zseq_deque))
            ]
        index += len(finalized_txs)
        if finalized_txs:
            sorted_numbers = sorted([t["index"] for t in finalized_txs])
            logger.debug(
                f"\nreceive finalized indexes: [{sorted_numbers[0]}, ..., {sorted_numbers[-1]}]",
            )
            txs = [tx["tx"].encode("latin-1") for tx in finalized_txs]
            try:
                zex.process(txs)
            except Exception:
                logger.exception("process loop")
        await asyncio.sleep(0.1)
