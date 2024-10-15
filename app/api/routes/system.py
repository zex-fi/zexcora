from collections import deque
from threading import Lock
import asyncio
import json
import os
import time

from eigensdk.crypto.bls import attestation
from fastapi import APIRouter, HTTPException
from loguru import logger
from redis.exceptions import ConnectionError
from zellular import Zellular
import httpx
import redis

from app import stop_event, zex
from app.verify import verify


class MockZellular:
    def __init__(self, app_name: str, base_url: str, threshold_percent=67):
        self.app_name = app_name
        self.base_url = base_url
        self.threshold_percent = threshold_percent
        host, port = base_url.split(":")
        self.r = redis.Redis(
            host=host, port=port, db=0, password=os.getenv("REDIS_PASSWORD", None)
        )

    def is_connected(self):
        try:
            self.r.ping()
            return True
        except (ConnectionError, ConnectionRefusedError):
            return False

    def batches(self, after=0):
        assert after >= 0, "after should be equal or bigger than 0"
        while True:
            batches = self.r.lrange(self.app_name, after, after + 100)
            for batch in batches:
                after += 1
                yield batch, after
            time.sleep(0.1)

    def get_last_finalized(self):
        return {"index": self.r.llen(self.app_name)}

    def send(self, batch, blocking=False):
        self.r.rpush(self.app_name, json.dumps(batch))
        if not blocking:
            return
        index = self.get_last_finalized()["index"]

        for received_batch, idx in self.batches(after=index):
            received_batch = json.loads(received_batch)
            if batch == received_batch:
                return idx


def create_mock_zellular_insance(app_name: str):
    base_url = os.getenv("REDIS_URL")
    zellular = MockZellular(app_name, base_url, threshold_percent=2 / 3 * 100)

    while not zellular.is_connected():
        logger.warning("waiting for redis...")
        time.sleep(1)

    return zellular


def create_real_zellular_instance(app_name: str):
    with open("./nodes.json") as f:
        operators = json.load(f)

    base_url = None
    for _, op in operators.items():
        resp = httpx.get(f"{op['socket']}/node/state")
        resp.raise_for_status()
        state = resp.json()
        if not state["data"]["sequencer"]:
            base_url = op["socket"]
            break
    if not base_url:
        raise ValueError("failed to find an operator")

    return Zellular(app_name, base_url, threshold_percent=2 / 3 * 100)


def create_zellular_instance():
    app_name = "zex"
    if os.getenv("USE_REDIS"):
        return create_mock_zellular_insance(app_name)
    return create_real_zellular_instance(app_name)


zseq_lock = Lock()
zseq_deque = deque()

router = APIRouter()


@router.get("/ping")
async def ping():
    return {}


@router.get("/time")
async def server_time():
    return {"serverTime": int(time.time() * 1000)}


@router.get("/{chain}/block/latest")
def get_latest_deposited_block(chain: str):
    if chain not in zex.deposited_blocks:
        raise HTTPException(404, {"error": "chain not found"})
    return {"block": zex.deposited_blocks[chain]}


@router.post("/txs")
def send_txs(txs: list[str]):
    with zseq_lock:
        zseq_deque.extend(txs)
    return {"success": True}


async def transmit_tx():
    zellular = create_zellular_instance()

    try:
        while not stop_event.is_set():
            if len(zseq_deque) == 0:
                await asyncio.sleep(0.1)
                continue

            with zseq_lock:
                txs = [
                    zseq_deque.popleft().encode("latin-1")
                    for _ in range(len(zseq_deque))
                ]

            verify(txs)
            txs = [x.decode("latin-1") for x in txs if x is not None]

            zellular.send(txs)
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        logger.warning("Transmit loop was cancelled")
    finally:
        logger.warning("Transmit loop is shutting down")


async def process_loop():
    verifier = create_zellular_instance()

    with open("./nodes.json") as f:
        operators = json.load(f)
    aggregated_public_key = attestation.new_zero_g2_point()
    for _, operator in operators.items():
        public_key_g2 = operator["public_key_g2"]
        operator["public_key_g2"] = attestation.new_zero_g2_point()
        operator["public_key_g2"].setStr(public_key_g2.encode("utf-8"))
        aggregated_public_key += operator["public_key_g2"]
    verifier.operators = operators
    verifier.aggregated_public_key = aggregated_public_key

    verbose = True if os.getenv("TEST_MODE") else False

    for batch, index in verifier.batches(after=zex.last_tx_index):
        if verbose:
            logger.critical(f"index {index} received from redis")
        try:
            txs: list[str] = json.loads(batch)
            finalized_txs = [x.encode("latin-1") for x in txs]
            zex.process(finalized_txs, index)

            # TODO: the for loop takes all the CPU time. the sleep gives time to other tasks to run. find a better solution
            await asyncio.sleep(0)
        except json.JSONDecodeError as e:
            logger.exception(e)
        except ValueError as e:
            logger.exception(e)

        if stop_event.is_set():
            break
