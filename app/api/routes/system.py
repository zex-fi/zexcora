from collections import deque
from threading import Lock
from urllib.parse import urlparse
import asyncio
import json
import time

from fastapi import APIRouter, HTTPException
from loguru import logger
from redis.exceptions import ConnectionError
from zellular import Zellular
import httpx
import redis

from app import stop_event, zex
from app.config import settings
from app.verify import TransactionVerifier


class MockZellular:
    def __init__(self, app_name: str, base_url: str, threshold_percent: float = 67):
        self.app_name = app_name
        self.base_url = base_url
        self.threshold_percent = threshold_percent
        self.offset = 0
        self.len_threshold = 1_000
        host, port = base_url.split(":")
        self.r = redis.Redis(
            host=host,
            port=port,
            db=0,
            password=settings.zex.redis.password,
        )

    def is_connected(self):
        try:
            self.r.ping()
            return True
        except (ConnectionError, ConnectionRefusedError) as e:
            logger.exception(e)
            return False

    def batches(self, after=0):
        assert after >= 0, "after should be equal or bigger than 0"
        if after != 0:
            self.offset = after - self.r.llen(self.app_name)

        while not stop_event.is_set():
            batches = self.r.lrange(
                self.app_name, after - self.offset, after - self.offset + 100
            )
            for batch in batches:
                after += 1
                yield batch, after
            if after - self.offset >= self.len_threshold:
                self.r.lpop(self.app_name, after)
                self.offset = after
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


def create_mock_zellular_instance(app_name: str):
    base_url = settings.zex.redis.url
    zellular = MockZellular(app_name, base_url, threshold_percent=2 / 3 * 100)

    while not zellular.is_connected():
        logger.warning("waiting for redis...")
        time.sleep(1)

    return zellular


def create_real_zellular_instance(app_name: str):
    resp = httpx.post(
        "https://api.studio.thegraph.com/query/62454/zellular_test/version/latest",
        json='{"query":"{ operators { id socket stake } }"}',
    )
    resp.raise_for_status()
    operators = resp.json()["data"]["operators"]

    base_url = None
    for _, op in operators.items():
        sequencer_port = 15781
        result = urlparse(op["socket"])
        resp = httpx.get(f"{result.hostname}:{sequencer_port}/node/state")
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
    if settings.zex.use_redis:
        return create_mock_zellular_instance(app_name)
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


@router.get("/status/deposit")
def get_deposit_status(chain: str, tx_hash: str, vout: int = 0):
    if chain not in zex.deposits:
        raise HTTPException(404, {"error": "chain not found"})
    if (tx_hash, vout) not in zex.deposits[chain]:
        raise HTTPException(404, {"error": "transaction not found"})
    return {"status": "complete"}


@router.post("/register")
def register(txs: list[str]):
    with zseq_lock:
        zseq_deque.extend(txs)
    return {"success": True}


@router.post("/order")
def new_order(txs: list[str]):
    with zseq_lock:
        zseq_deque.extend(txs)
    return {"success": True}


@router.delete("/order")
def cancel_order(txs: list[str]):
    with zseq_lock:
        zseq_deque.extend(txs)
    return {"success": True}


@router.post("/deposit")
def send_txs(txs: list[str]):
    with zseq_lock:
        zseq_deque.extend(txs)
    return {"success": True}


@router.post("/withdraw")
def new_withdraw(txs: list[str]):
    with zseq_lock:
        zseq_deque.extend(txs)
    return {"success": True}


async def transmit_tx(tx_verifier: TransactionVerifier):
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

            verified_txs = tx_verifier.verify(txs)
            txs = [x.decode("latin-1") for x in verified_txs if x is not None]

            zellular.send(txs)
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        logger.warning("Transmit loop was cancelled")
    finally:
        logger.warning("Transmit loop is shutting down")


async def process_loop(tx_verifier: TransactionVerifier):
    verifier = create_zellular_instance()
    verbose = settings.zex.verbose

    for batch, index in verifier.batches(after=zex.last_tx_index):
        if verbose:
            logger.critical(f"index {index} received from redis")
        try:
            txs: list[str] = json.loads(batch)
            finalized_txs = [x.encode("latin-1") for x in txs]
            verified_txs = tx_verifier.verify(finalized_txs)
            zex.process(verified_txs, index)

            # TODO: the for loop takes all the CPU time. the sleep gives time to other tasks to run. find a better solution
            await asyncio.sleep(0)
        except json.JSONDecodeError as e:
            logger.exception(e)
        except ValueError as e:
            logger.exception(e)

        if stop_event.is_set():
            break
