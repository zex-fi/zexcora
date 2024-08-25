import asyncio
import hashlib
import signal
from pprint import pprint
from struct import pack

import requests
import yaml
from bitcoinlib.services.services import Service
from bitcoinlib.transactions import Output, Transaction
from bitcoinutils.keys import P2trAddress, PublicKey
from bitcoinutils.utils import tweak_taproot_pubkey
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
async def get_deposits(contract: Contract, from_block, to_block):
    failed = True
    while failed and IS_RUNNING:
        try:
            events = contract.events.Deposit.get_logs(
                fromBlock=from_block, toBlock=to_block
            )
            failed = False
        except Exception as e:
            print(e)
            await asyncio.sleep(5)
            continue
    if failed:
        return None
    return [dict(event["args"]) for event in events]


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

    try:
        while IS_RUNNING:
            latest_block = web3.eth.block_number
            if processed_block >= latest_block - blocks_confirmation:
                await asyncio.sleep(block_duration)
                continue

            deposits = await get_deposits(
                contract,
                processed_block + 1,
                latest_block - blocks_confirmation,
            )
            if deposits is None:
                print(f"{chain} failed to get_logs from contract")
                continue

            if len(deposits) == 0:
                print(
                    f"{chain} no event from: {processed_block+1}, to: {latest_block-blocks_confirmation}"
                )
                processed_block = latest_block - blocks_confirmation
                continue
            processed_block = latest_block - blocks_confirmation

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

            sent_block = requests.get(f"{api_url}/{chain}/block/latest").json()["block"]
            while sent_block != processed_block and IS_RUNNING:
                print(
                    f"{chain} deposit is not yet applied, server desposited block: {sent_block}, script processed block: {processed_block}"
                )
                await asyncio.sleep(2)

                sent_block = requests.get(f"{api_url}/{chain}/block/latest").json()[
                    "block"
                ]
                continue
    except asyncio.CancelledError:
        pass

    network["processed_block"] = processed_block
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


def tagged_hash(data: bytes, tag: str) -> bytes:
    """
    Tagged hashes ensure that hashes used in one context can not be used in another.
    It is used extensively in Taproot

    A tagged hash is: SHA256( SHA256("TapTweak") ||
                              SHA256("TapTweak") ||
                              data
                            )
    """

    tag_digest = hashlib.sha256(tag.encode()).digest()
    return hashlib.sha256(tag_digest + tag_digest + data).digest()


# to convert hashes to ints we need byteorder BIG...
def b_to_i(b: bytes) -> int:
    """Converts a bytes to a number"""
    return int.from_bytes(b, byteorder="big")


def i_to_b8(i: int) -> bytes:
    """Converts a integer to bytes"""
    return i.to_bytes(8, byteorder="big")


def calculate_tweak(pubkey: PublicKey, user_id: int) -> int:
    """
    Calculates the tweak to apply to the public and private key when required.
    """

    # only the x coordinate is tagged_hash'ed
    key_x = pubkey.to_bytes()[:32]

    tweak = tagged_hash(key_x + i_to_b8(user_id), "TapTweak")

    # we convert to int for later elliptic curve  arithmetics
    tweak_int = b_to_i(tweak)

    return tweak_int


def get_taproot_address(master_public: PublicKey, user_id: int) -> P2trAddress:
    tweak_int = calculate_tweak(master_public, user_id)
    # keep x-only coordinate
    tweak_and_odd = tweak_taproot_pubkey(master_public.key.to_string(), tweak_int)
    pubkey = tweak_and_odd[0][:32]
    is_odd = tweak_and_odd[1]

    return P2trAddress(witness_program=pubkey.hex(), is_odd=is_odd)


async def run_monitor_btc(network: dict, api_url: str, monitor: PrivateKey):
    blocks_confirmation = network["blocks_confirmation"]
    block_duration = network["block_duration"]
    chain = network["chain"]
    sent_block = requests.get(f"{api_url}/{chain}/block/latest").json()["block"]
    processed_block = network["processed_block"]
    if sent_block > processed_block:
        network["processed_block"] = sent_block
        processed_block = sent_block

    master_pub = PublicKey.from_hex(network["public_key"])
    srv = Service(network="mainnet" if network["mainnet"] else "testnet")

    latest_user_id = 0
    all_taproot_addresses: dict[str, str] = {}

    try:
        while IS_RUNNING:
            latest_block_num = srv.blockcount()
            if processed_block > latest_block_num - blocks_confirmation:
                await asyncio.sleep(block_duration)
                continue

            new_latest_user_id = requests.get(f"{api_url}/users/latest-id").json()["id"]
            if latest_user_id != new_latest_user_id:
                for i in range(latest_user_id + 1, new_latest_user_id + 1):
                    taproot_pub = get_taproot_address(master_pub, i)

                    if i == 1:
                        print(f"God user taproot address: {taproot_pub.to_string()}")
                    public = requests.get(f"{api_url}/user/{i}/public").json()["public"]
                    all_taproot_addresses[taproot_pub.to_string()] = public

                latest_user_id = new_latest_user_id

            latest_block = srv.getblock(processed_block + 1, parse_transactions=False)
            if latest_block is False:
                print(f"{chain} get block failed")
                await asyncio.sleep(2)
                continue

            seen_txs = set()
            deposits = []
            count = 0
            # Iterate through transactions in the block
            while count != latest_block.tx_count:
                limit = 25
                page = (count // limit) + 1
                block = srv.getblock(
                    processed_block + 1,
                    parse_transactions=True,
                    page=page,
                    limit=limit,
                )
                if block is False:
                    await asyncio.sleep(10)
                    continue

                tx: Transaction
                for tx in block.transactions:
                    if tx.txid in seen_txs:
                        continue
                    seen_txs.add(tx.txid)
                    count += 1

                    # Check if any output address matches our list of Taproot addresses
                    out: Output
                    for out in tx.outputs:
                        if out.address in all_taproot_addresses:
                            deposits.append(
                                {
                                    "public": all_taproot_addresses[out.address],
                                    "tokenIndex": 0,
                                    "amount": out.value,
                                }
                            )
                await asyncio.sleep(0.1)  # give time to other tasks

            if len(deposits) == 0:
                print(f"{chain} no deposit in block: {processed_block}")
                processed_block += 1
                continue
            processed_block += 1

            tx = create_tx(
                deposits,
                chain,
                sent_block + 1,
                processed_block,
                latest_block.time,
                monitor,
            )
            requests.post(f"{api_url}/txs", json=[tx.decode("latin-1")])
            # to check if request is applied, query latest processed block from zex

            sent_block = requests.get(f"{api_url}/{chain}/block/latest").json()["block"]
            while sent_block != processed_block and IS_RUNNING:
                print(
                    f"{chain} deposit is not yet applied, server desposited block: {sent_block}, script processed block: {processed_block}"
                )
                await asyncio.sleep(2)

                sent_block = requests.get(f"{api_url}/{chain}/block/latest").json()[
                    "block"
                ]
                continue
    except asyncio.CancelledError:
        pass

    network["processed_block"] = processed_block
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
    loop.add_signal_handler(signal.SIGTERM, signal_handler)

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
        print(results)
        config["networks"] = results
        pprint(config, indent=2)
        # with open("config.yaml", "w") as file:
        #     yaml.safe_dump(config)
    except asyncio.CancelledError:
        print("Tasks were cancelled")
    finally:
        # Ensure all tasks are properly cancelled
        for task in tasks:
            if not task.done():
                task.cancel()

        # Wait for all tasks to be cancelled
        await asyncio.gather(*tasks, return_exceptions=True)

        print("All tasks have been stopped. Exiting program.")


if __name__ == "__main__":
    asyncio.run(main())
