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
from zellular import Zellular
import httpx

from ... import stop_event
from ...config import settings
from ...verify import TransactionVerifier
from ...zex import Zex

zex = Zex.initialize_zex()


def create_real_zellular_instance(app_name: str):
    if settings.zex.sequencer_mode == "eigenlayer":
        resp = httpx.post(
            settings.zex.sequencer_subgraph,
            json='{"query":"{ operators { id socket stake } }"}',
        )
        resp.raise_for_status()
        operators = resp.json()["data"]["operators"]
    elif settings.zex.sequencer_mode == "docker":
        operators = json.loads("""{
    "data": {
        "operators": [
            {
                "id": "0x1e0a6263be1efc4ea0d2c5b9a1e49ac50375c030",
                "public_key_g2": "1 9611278528866057312985157745500177806439047990441641970719150715526228383788 14510296422332084166275589907551577008082509824157021533974616032309609480403 10081477652997729356586307373461973834068770885982023569165073493039390199093 1205130207870954424919762321217866852983647106641519327167552924115584464295",
                "address": "0x1e0a6263be1efc4ea0d2c5b9a1e49ac50375c030",
                "socket": "http://zsequencer-node1:6001",
                "stake": 10
            },
            {
                "id": "0xfbd6c9f44c5a0a2d8423e461a87fccee12942781",
                "public_key_g2": "1 2564456049898491471897001563782187382505864485640732016823408287867963614179 11319803778281346294691548584774975191176177781049043197825920188158404075467 6883987038389898594439008536930343408067598750972752182534728449983371992012 11863261598815579367545344722667576271049210660431455670485947818125672062126",
                "address": "0xfbd6c9f44c5a0a2d8423e461a87fccee12942781",
                "socket": "http://zsequencer-node2:6001",
                "stake": 10
            },
            {
                "id": "0xb99f2b6b30fa1ed6ec2e1049bb6d6fd86bb64dab",
                "public_key_g2": "1 10722094092415951831092083281713777097975657843805414789700230979893472506937 13892874056591023907216140630948185723246894999227161991434043115559319234682 1765457543974974681849480344310374252170324566540342055726528305206357241460 16510337125750125045428789459859581254702063586917971466893230941761056998147",
                "address": "0xb99f2b6b30fa1ed6ec2e1049bb6d6fd86bb64dab",
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
                "id": "0x1e0a6263be1efc4ea0d2c5b9a1e49ac50375c030",
                "public_key_g2": "1 9611278528866057312985157745500177806439047990441641970719150715526228383788 14510296422332084166275589907551577008082509824157021533974616032309609480403 10081477652997729356586307373461973834068770885982023569165073493039390199093 1205130207870954424919762321217866852983647106641519327167552924115584464295",
                "address": "0x1e0a6263be1efc4ea0d2c5b9a1e49ac50375c030",
                "socket": "http://127.0.0.1:6001",
                "stake": 10
            },
            {
                "id": "0xfbd6c9f44c5a0a2d8423e461a87fccee12942781",
                "public_key_g2": "1 2564456049898491471897001563782187382505864485640732016823408287867963614179 11319803778281346294691548584774975191176177781049043197825920188158404075467 6883987038389898594439008536930343408067598750972752182534728449983371992012 11863261598815579367545344722667576271049210660431455670485947818125672062126",
                "address": "0xfbd6c9f44c5a0a2d8423e461a87fccee12942781",
                "socket": "http://127.0.0.1:6002",
                "stake": 10
            },
            {
                "id": "0xb99f2b6b30fa1ed6ec2e1049bb6d6fd86bb64dab",
                "public_key_g2": "1 10722094092415951831092083281713777097975657843805414789700230979893472506937 13892874056591023907216140630948185723246894999227161991434043115559319234682 1765457543974974681849480344310374252170324566540342055726528305206357241460 16510337125750125045428789459859581254702063586917971466893230941761056998147",
                "address": "0xb99f2b6b30fa1ed6ec2e1049bb6d6fd86bb64dab",
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
        if resp.status_code != 200 and resp.json()["error"]["code"] == "is_sequencer":
            continue
        else:
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
    with TransactionVerifier(
        num_processes=settings.zex.verifier_threads
    ) as tx_verifier:
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
    while True:
        try:
            for batch, index in zellular.batches(after=after):
                after = index
                zellular_queue.put((batch, index))
        except Exception as e:
            logger.exception(e)
            continue


def verify_batches(
    zellular_queue: mp.Queue,
    queue: mp.Queue,
):
    with TransactionVerifier(
        num_processes=settings.zex.verifier_threads
    ) as tx_verifier:
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
