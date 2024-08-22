import asyncio
import signal
from struct import pack

import requests
import yaml
from bitcoinlib.services.services import Service
from bitcoinlib.transactions import Output, Transaction
from secp256k1 import PrivateKey
from web3 import Web3
from web3.contract.contract import Contract
from web3.middleware import geth_poa_middleware

IS_RUNNING = True

TOKENS = {
    "BTC": {
        0: 1e8,
    },
    "BST": {
        3: 1e6,
        4: 1e6,
        5: 1e8,
    },
    "SEP": {
        1: 1e6,
        2: 1e6,
        3: 1e8,
    },
    "HOL": {
        1: 1e6,
        2: 1e6,
        3: 1e8,
    },
}


# Function to initialize Web3 instance for each network
def initialize_web3(network) -> tuple[Web3, Contract]:
    web3 = Web3(Web3.HTTPProvider(network["node_url"]))
    web3.middleware_onion.inject(geth_poa_middleware, layer=0)
    contract = web3.eth.contract(
        address=network["contract_address"], abi=network["contract_abi"]
    )
    return web3, contract


# Function to get deposits
async def get_deposits(web3: Web3, contract: Contract, block, block_confirmation):
    latest_block = web3.eth.block_number
    if block > latest_block - block_confirmation:
        return block, []
    failed = True
    while failed and IS_RUNNING:
        try:
            events = contract.events.Deposit.get_logs(
                fromBlock=block, toBlock=latest_block - block_confirmation
            )
            failed = False
        except Exception as e:
            print(e)
            await asyncio.sleep(5)
            continue
    if failed:
        return block, []
    return latest_block - block_confirmation, [dict(event["args"]) for event in events]


def create_tx(
    deposits, chain: str, from_block, to_block, timestamp, monitor: PrivateKey
):
    version = pack(">B", 1)
    chain: bytes = chain.encode()
    block_range = pack(">QQ", from_block, to_block)
    tx = version + b"d" + chain + block_range + pack(">H", len(deposits))
    for deposit in deposits:
        if "public" in deposit:
            public = bytes.fromhex(deposit["public"])
        else:
            prefix = "02" if deposit["pubKeyYParity"] == 0 else "03"
            pubKeyX = f"{deposit['pubKeyX']:#0{32}x}"[2:]
            public = bytes.fromhex(prefix + pubKeyX)
        token_id = deposit["tokenIndex"]
        amount = deposit["amount"] / TOKENS[chain.decode()].get(token_id, 1e18)

        print(token_id, amount, timestamp, "t")

        tx += pack(">IdI", token_id, amount, timestamp)
        tx += public
    tx += monitor.schnorr_sign(tx, bip340tag="zex")
    counter = 0
    tx += pack(">Q", counter)
    return tx


async def run_monitor(network: dict, api_url: str, monitor: PrivateKey):
    web3, contract = initialize_web3(network)
    blocks_confirmation = network["blocks_confirmation"]
    block_duration = network["block_duration"]
    chain = network["chain"]
    sent_block = requests.get(f"{api_url}/{chain}/block/latest").json()["block"]
    processed_block = network["processed_block"]
    if sent_block > processed_block:
        network["processed_block"] = sent_block
        processed_block = sent_block

    while IS_RUNNING:
        latest_block = web3.eth.block_number
        if processed_block >= latest_block - blocks_confirmation:
            await asyncio.sleep(block_duration)
            continue

        to_block, deposits = await get_deposits(
            web3, contract, processed_block, blocks_confirmation
        )
        processed_block = to_block
        if len(deposits) == 0:
            print(f"no event from:{sent_block}, to: {processed_block}")
            continue

        block = web3.eth.get_block(processed_block)
        tx = create_tx(
            deposits,
            chain,
            sent_block + 1,
            processed_block,
            block["timestamp"],
            monitor,
        )
        requests.post(f"{api_url}/txs", json=[tx.decode("latin-1")])
        # to check if request is applied, query latest processed block from zex
        sent_block = requests.get(f"{api_url}/{chain}/block/latest").json()["block"]

        network["processed_block"] = sent_block

    return network


def get_tx_data_output(tx: Transaction):
    for out in tx.outputs:
        if out.script_type != "nulldata":
            continue
        return out.script.commands[1].hex()
    return ""


def get_deposit_output(tx: Transaction, wallet_address: str) -> Output | None:
    outputs: list[Output] = tx.outputs
    for out in outputs:
        if out.address == wallet_address:
            return out
    return None


async def run_monitor_btc(network: dict, api_url: str, monitor: PrivateKey):
    blocks_confirmation = network["blocks_confirmation"]
    block_duration = network["block_duration"]
    chain = network["chain"]
    sent_block = requests.get(f"{api_url}/{chain}/block/latest").json()["block"]
    processed_block = network["processed_block"]
    if sent_block > processed_block:
        network["processed_block"] = sent_block
        processed_block = sent_block

    srv = Service(network="mainnet" if network["mainnet"] else "testnet")
    last_processed_txid = ""

    while IS_RUNNING:
        latest_block = srv.blockcount()
        if processed_block >= latest_block - blocks_confirmation:
            await asyncio.sleep(block_duration)
            continue

        txs: list[Transaction] = srv.gettransactions(
            network["wallet_address"], after_txid=last_processed_txid
        )
        if len(txs) == 0:
            print(f"BTC no event from:{sent_block}, to: {processed_block}")
            continue
        processed_block = srv.blockcount() - blocks_confirmation

        deposits = []
        for tx in txs:
            last_processed_txid = tx.txid
            if tx.confirmations < blocks_confirmation:
                continue

            if all(out.script_type != "nulldata" for out in tx.outputs):
                print(f"found deposit without OP_RETURN data, txid: {tx.txid}")
                continue
            data_output = get_tx_data_output(tx)
            assert data_output != "", "this should never happen"
            if len(data_output) != 33:
                print(f"invalid public key: {data_output}")
                continue

            deposit_output = get_deposit_output(tx, network["wallet_address"])
            assert (
                deposit_output is not None
            ), "none of the ouitputs was a deposit to wallet"

            deposits.append(
                {
                    "public": data_output,
                    "tokenIndex": 0,
                    "amount": deposit_output.value,
                }
            )
        block = srv.getblock(srv.blockcount() - blocks_confirmation, limit=1)
        tx = create_tx(
            deposits,
            chain,
            sent_block + 1,
            processed_block,
            block.time,
            monitor,
        )
        requests.post(f"{api_url}/txs", json=[tx.decode("latin-1")])
        # to check if request is applied, query latest processed block from zex
        sent_block = requests.get(f"{api_url}/{chain}/block/latest").json()["block"]

        network["processed_block"] = sent_block

    return network


async def main():
    # processed_block = web3.eth.block_number - BLOCKS_CONFIRMATION # should be queried from zex
    # print(processed_block)
    # Set up signal handler
    def signal_handler():
        global IS_RUNNING
        IS_RUNNING = False
        print("\nInterrupt received. Stopping tasks...")

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGINT, signal_handler)

    with open("config.yaml") as file:
        config = yaml.safe_load(file)

    networks = config["networks"]
    api_url = config["api_url"]
    monitor_private = config["monitor_private"]
    monitor = PrivateKey(bytes(bytearray.fromhex(monitor_private)), raw=True)

    tasks = []
    for network in networks:
        if network["name"] == "btc":
            t = asyncio.create_task(run_monitor_btc(network, api_url, monitor))
        else:
            t = asyncio.create_task(run_monitor(network, api_url, monitor))
        tasks.append(t)

    try:
        # Wait for all tasks to complete or until interrupted
        results = await asyncio.gather(*tasks, return_exceptions=True)
        config["networks"] = results
        with open("config.yaml", "w") as file:
            yaml.safe_dump(config, file)
    except asyncio.CancelledError:
        print("Tasks were cancelled")


if __name__ == "__main__":
    asyncio.run(main())
