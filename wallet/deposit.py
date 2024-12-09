from pprint import pprint
from struct import pack
import asyncio
import hashlib
import signal

from bitcoinrpc import BitcoinRPC, RPCError
from bitcoinutils.keys import P2trAddress, PublicKey
from bitcoinutils.setup import setup
from bitcoinutils.utils import tweak_taproot_pubkey
from secp256k1 import PrivateKey
import httpx
import yaml

setup("mainnet")

IS_RUNNING = True

TOKENS = {
    "BTC": {
        "0x" + "0" * 40: 8,
    }
}


def create_tx(deposits, chain: str, timestamp, monitor: PrivateKey):
    header_format = ">B B 3s H"
    version = 1
    chain: bytes = chain.encode()

    tx = pack(
        header_format,
        version,
        int.from_bytes(b"x", "big"),
        chain,
        len(deposits),
    )
    for deposit in deposits:
        tx_hash: str = "0x"+deposit["tx_hash"]
        vout: int = deposit["vout"]
        user_id: int = deposit["user_id"]
        token_address: str = "0x" + "0" * 40
        amount: int = deposit["amount"]
        decimal = int(TOKENS[chain.decode()].get(token_address, 18))

        print(token_address, amount, decimal, timestamp)

        tx += pack(
            ">66s 42s 32s B I Q B",
            tx_hash.encode(),
            token_address.encode(),
            amount.to_bytes(32, byteorder="big"),
            decimal,
            timestamp,
            user_id,
            vout,
        )
    tx += monitor.schnorr_sign(tx, bip340tag="zex")
    return tx


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
    """Converts an integer to bytes"""
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
    processed_block = network["start_block"]

    rpc = BitcoinRPC.from_config(network["node_url"], None)

    master_pub = PublicKey.from_hex(network["public_key"])

    latest_user_id = 0
    all_taproot_addresses: dict[str, int] = {}

    try:
        while IS_RUNNING:
            try:
                latest_block_num = await rpc.getblockcount()
            except (httpx.ReadTimeout, RPCError) as e:
                print(f"{chain} error {e}")
                await asyncio.sleep(10)
                continue
            if processed_block >= latest_block_num - (blocks_confirmation - 1):
                print(f"{chain} waiting for new block")
                await asyncio.sleep(block_duration)
                continue

            new_latest_user_id = httpx.get(f"{api_url}/users/latest-id").json()["id"]
            if latest_user_id != new_latest_user_id:
                for i in range(latest_user_id + 1, new_latest_user_id + 1):
                    taproot_pub = get_taproot_address(master_pub, i)

                    if i == 1:
                        print(f"God user taproot address: {taproot_pub.to_string()}")
                    all_taproot_addresses[taproot_pub.to_string()] = i

                latest_user_id = new_latest_user_id

            try:
                block_hash = await rpc.getblockhash(processed_block + 1)
                latest_block = await rpc.getblock(block_hash, 2)
            except (httpx.ReadTimeout, RPCError) as e:
                print(f"{chain} error {e}")
                await asyncio.sleep(10)
                continue

            seen_txs = set()
            deposits = []

            # Iterate through transactions in the block
            for tx in latest_block["tx"]:
                if tx["txid"] in seen_txs:
                    continue
                seen_txs.add(tx["txid"])

                # Check if any output address matches our list of Taproot addresses
                for out in tx["vout"]:
                    if "address" not in out["scriptPubKey"]:
                        continue

                    address = out["scriptPubKey"]["address"]
                    if address in all_taproot_addresses:
                        deposits.append(
                            {
                                "tx_hash": tx["txid"],
                                "vout": out["n"],
                                "user_id": all_taproot_addresses[address],
                                "tokenIndex": "0x" + "0" * 40,
                                "amount": int(
                                    out["value"]
                                    * (10 ** TOKENS["BTC"]["0x" + "0" * 40])
                                ),
                            }
                        )
                        print(f"found deposit to address: {address}")
                await asyncio.sleep(0)  # give time to other tasks

            processed_block += 1
            if len(deposits) == 0:
                print(f"{chain} no deposit in block: {processed_block}")
                continue

            tx = create_tx(
                deposits,
                chain,
                latest_block["time"],
                monitor,
            )
            httpx.post(f"{api_url}/deposit", json=[tx.decode("latin-1")])
            # to check if request is applied, query latest processed block from zex

    except asyncio.CancelledError:
        pass

    return network


async def main():
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
            print("invalid network")
            continue
        tasks.append(t)

    try:
        # Wait for all tasks to complete or until interrupted
        results = await asyncio.gather(*tasks, return_exceptions=False)
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
        await asyncio.gather(*tasks, return_exceptions=False)

        print("All tasks have been stopped. Exiting program.")


if __name__ == "__main__":
    asyncio.run(main())
