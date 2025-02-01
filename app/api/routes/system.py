from collections import deque
from queue import Empty
from threading import Lock
from urllib.parse import urlparse
import asyncio
import json
import multiprocessing as mp
import time

from eigensdk.crypto.bls import attestation
from fastapi import APIRouter, HTTPException
from loguru import logger
from redis.exceptions import ConnectionError
from zellular import Zellular
import httpx
import redis

from app import stop_event
from app.config import settings
from app.verify import TransactionVerifier
from app.zex import Zex

zex = Zex.initialize_zex()


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
    if settings.zex.sequencer_mode == "eigenlayer":
        resp = httpx.post(
            "https://api.studio.thegraph.com/query/62454/zellular_test/version/latest",
            json='{"query":"{ operators { id socket stake } }"}',
        )
        resp.raise_for_status()
        operators = resp.json()["data"]["operators"]
    elif settings.zex.sequencer_mode == "docker":
        operators = json.loads("""{
    "data": {
        "operators": [
            {
                "id": "0x4c2906574e76b002e757ff957551c4af64ef33b8",
                "public_key_g2": "1 9611278528866057312985157745500177806439047990441641970719150715526228383788 14510296422332084166275589907551577008082509824157021533974616032309609480403 10081477652997729356586307373461973834068770885982023569165073493039390199093 1205130207870954424919762321217866852983647106641519327167552924115584464295",
                "address": "0x4c2906574e76b002e757ff957551c4af64ef33b8",
                "socket": "http://zsequencer-node1:6001",
                "stake": 10
            },
            {
                "id": "0xc46ddcd9998b4f692d2d1d66cf3ba1ff06e7ecd6",
                "public_key_g2": "1 2564456049898491471897001563782187382505864485640732016823408287867963614179 11319803778281346294691548584774975191176177781049043197825920188158404075467 6883987038389898594439008536930343408067598750972752182534728449983371992012 11863261598815579367545344722667576271049210660431455670485947818125672062126",
                "address": "0xc46ddcd9998b4f692d2d1d66cf3ba1ff06e7ecd6",
                "socket": "http://zsequencer-node2:6001",
                "stake": 10
            },
            {
                "id": "0x86dcaa39330c6a1a27273928bb5877bdf6240502",
                "public_key_g2": "1 10722094092415951831092083281713777097975657843805414789700230979893472506937 13892874056591023907216140630948185723246894999227161991434043115559319234682 1765457543974974681849480344310374252170324566540342055726528305206357241460 16510337125750125045428789459859581254702063586917971466893230941761056998147",
                "address": "0x86dcaa39330c6a1a27273928bb5877bdf6240502",
                "socket": "http://zsequencer-node3:6001",
                "stake": 10
            }
        ]
    }
}""")["data"]["operators"]
    else:
        operators = json.loads("""{
    "data": {
        "operators": [
            {
                "id": "0x4c2906574e76b002e757ff957551c4af64ef33b8",
                "public_key_g2": "1 9611278528866057312985157745500177806439047990441641970719150715526228383788 14510296422332084166275589907551577008082509824157021533974616032309609480403 10081477652997729356586307373461973834068770885982023569165073493039390199093 1205130207870954424919762321217866852983647106641519327167552924115584464295",
                "address": "0x4c2906574e76b002e757ff957551c4af64ef33b8",
                "socket": "http://127.0.0.1:6001",
                "stake": 10
            },
            {
                "id": "0xc46ddcd9998b4f692d2d1d66cf3ba1ff06e7ecd6",
                "public_key_g2": "1 2564456049898491471897001563782187382505864485640732016823408287867963614179 11319803778281346294691548584774975191176177781049043197825920188158404075467 6883987038389898594439008536930343408067598750972752182534728449983371992012 11863261598815579367545344722667576271049210660431455670485947818125672062126",
                "address": "0xc46ddcd9998b4f692d2d1d66cf3ba1ff06e7ecd6",
                "socket": "http://127.0.0.1:6002",
                "stake": 10
            },
            {
                "id": "0x86dcaa39330c6a1a27273928bb5877bdf6240502",
                "public_key_g2": "1 10722094092415951831092083281713777097975657843805414789700230979893472506937 13892874056591023907216140630948185723246894999227161991434043115559319234682 1765457543974974681849480344310374252170324566540342055726528305206357241460 16510337125750125045428789459859581254702063586917971466893230941761056998147",
                "address": "0x86dcaa39330c6a1a27273928bb5877bdf6240502",
                "socket": "http://127.0.0.1:6003",
                "stake": 10
            }
        ]
    }
}""")["data"]["operators"]

    base_url = None
    for op in operators:
        result = urlparse(op["socket"])
        resp = httpx.get(f"http://{result.hostname}:{result.port}/node/state")
        resp.raise_for_status()
        state = resp.json()
        if not state["data"]["sequencer"]:
            base_url = op["socket"]
            break
    if not base_url:
        raise ValueError("failed to find an operator")

    zellular = Zellular(app_name, base_url, threshold_percent=2 / 3 * 100)
    if not settings.zex.mainnet:
        aggregated_public_key = attestation.new_zero_g2_point()
        for op in operators:
            public_key_g2 = op["public_key_g2"]
            op["public_key_g2"] = attestation.new_zero_g2_point()
            op["public_key_g2"].setStr(public_key_g2.encode("utf-8"))
            aggregated_public_key += op["public_key_g2"]

        zellular.operators = {operator["id"]: operator for operator in operators}
        zellular.aggregated_public_key = aggregated_public_key

    return zellular


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
    if chain not in zex.state_manager.chain_states:
        raise HTTPException(404, {"error": "chain not found"})
    if (tx_hash, vout) not in zex.state_manager.chain_states[chain].deposits:
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


async def transmit_tx():
    zellular = create_zellular_instance()
    with TransactionVerifier(num_processes=4) as tx_verifier:
        try:
            while not stop_event.is_set():
                if len(zseq_deque) == 0:
                    await asyncio.sleep(settings.zex.tx_transmit_delay)
                    continue

                with zseq_lock:
                    txs = [
                        zseq_deque.popleft().encode("latin-1")
                        for _ in range(len(zseq_deque))
                    ]

                verified_txs = tx_verifier.verify(txs)
                txs = [x.decode("latin-1") for x in verified_txs if x is not None]

                zellular.send(txs)
                await asyncio.sleep(settings.zex.tx_transmit_delay)
        except asyncio.CancelledError:
            logger.warning("Transmit loop was cancelled")
        finally:
            logger.warning("Transmit loop is shutting down")


def pull_batches(
    zellular: Zellular,
    zellular_queue: mp.Queue,
    after: int,
):
    try:
        for batch, index in zellular.batches(after=after):
            after = index
            zellular_queue.put((batch, index))
    finally:
        zellular_queue.put(None)


def verify_batches(
    zellular_queue: mp.Queue,
    queue: mp.Queue,
):
    with TransactionVerifier(num_processes=4) as tx_verifier:
        try:
            while True:
                item = zellular_queue.get()
                if item is None:
                    break
                batch, index = item

                txs: list[str] = json.loads(batch)
                finalized_txs = [x.encode("latin-1") for x in txs]
                verified_txs = tx_verifier.verify(finalized_txs)
                queue.put((verified_txs, index))
        finally:
            queue.put(None)


async def process_loop():
    zellular = create_zellular_instance()
    verbose = settings.zex.verbose

    zellular_queue = mp.Queue(100)
    queue = mp.Queue(100)

    tx_fetcher_process = mp.Process(
        target=pull_batches,
        args=(zellular, zellular_queue, zex.last_tx_index),
    )
    tx_verifier_process = mp.Process(
        target=verify_batches,
        args=(zellular_queue, queue),
    )

    tx_fetcher_process.start()
    tx_verifier_process.start()

    while True:
        if stop_event.is_set():
            tx_fetcher_process.kill()
            tx_verifier_process.kill()
            break

        try:
            item = queue.get(timeout=1)
        except Empty:
            continue

        if item is None:
            stop_event.set()
            logger.warning("got None from queue")
            break

        verified_txs, index = item
        if verbose:
            logger.critical(f"index {index} received from redis")
        try:
            now = time.time()
            zex.process(verified_txs, index)

            # TODO: the for loop takes all the CPU time. the sleep gives time to other tasks to run. find a better solution
            await asyncio.sleep(0)
            logger.warning(time.time() - now)
        except json.JSONDecodeError as e:
            logger.exception(e)
        except ValueError as e:
            logger.exception(e)
