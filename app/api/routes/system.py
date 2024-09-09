import asyncio
import json
import time
from collections import deque
from threading import Lock

import requests
import zellular
from fastapi import APIRouter, HTTPException
from loguru import logger

from app import zex
from app.verify import verify

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
    app_name = "simple_app"

    with open("/tmp/zellular_dev_net/nodes.json") as f:
        operators = json.load(f)

    base_url = None
    for op_id, op in operators.items():
        state = requests.get(f"{op['socket']}/node/state").json()
        if not state["data"]["sequencer"]:
            base_url = op["socket"]
            break
    if not base_url:
        raise ValueError("failed to find an operator")

    while True:
        if len(zseq_deque) == 0:
            await asyncio.sleep(0.1)
            continue

        with zseq_lock:
            txs = [
                zseq_deque.popleft().encode("latin-1") for _ in range(len(zseq_deque))
            ]

        verify(txs)
        txs = [x.decode("latin-1") for x in txs if x is not None]

        resp = requests.put(f"{base_url}/node/{app_name}/batches", json=txs)
        await asyncio.sleep(0.1)


async def process_loop():
    from eigensdk.crypto.bls import attestation

    app_name = "simple_app"

    with open("/tmp/zellular_dev_net/nodes.json") as f:
        operators = json.load(f)

    base_url = None
    for op_id, op in operators.items():
        state = requests.get(f"{op['socket']}/node/state").json()
        if not state["data"]["sequencer"]:
            base_url = op["socket"]
            break
    if not base_url:
        raise ValueError("failed to find an operator")

    aggregated_public_key = attestation.new_zero_g2_point()
    for address, operator in operators.items():
        public_key_g2 = operator["public_key_g2"]
        operator["public_key_g2"] = attestation.new_zero_g2_point()
        operator["public_key_g2"].setStr(public_key_g2.encode("utf-8"))
        aggregated_public_key += operator["public_key_g2"]

    verifier = zellular.Verifier(app_name, base_url)
    verifier.operators = operators
    verifier.aggregated_public_key = aggregated_public_key

    for batch, index in verifier.batches():
        txs: list[str] = json.loads(batch)
        # sorted_numbers = sorted([t["index"] for t in finalized_txs])
        # logger.debug(
        #     f"\nreceive finalized indexes: [{sorted_numbers[0]}, ..., {sorted_numbers[-1]}]",
        # )

        finalized_txs = [x.encode("latin-1") for x in txs]
        try:
            zex.process(finalized_txs, index)

            # TODO: the for loop takes all the CPU time. the sleep gve time to other tasks to run. find a better solution
            await asyncio.sleep(0)
        except Exception:
            logger.exception("process loop")
