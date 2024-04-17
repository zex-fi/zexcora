import time
import requests
from struct import pack
from web3 import Web3
from secp256k1 import PrivateKey
from web3.middleware import geth_poa_middleware


# Configuration
NODE_URL = "https://data-seed-prebsc-1-s1.bnbchain.org:8545"
CONTRACT_ADDRESS = "0xEca9036cFbfD61C952126F233682f9A6f97E4DBD"
CONTRACT_ABI = '[{"inputs":[{"internalType":"address","name":"_verifier","type":"address"},{"internalType":"uint256","name":"_pubKeyX","type":"uint256"},{"internalType":"uint8","name":"_pubKeyYParity","type":"uint8"}],"stateMutability":"nonpayable","type":"constructor"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"uint256","name":"tokenIndex","type":"uint256"},{"indexed":false,"internalType":"uint256","name":"amount","type":"uint256"},{"indexed":true,"internalType":"uint256","name":"pubKeyX","type":"uint256"},{"indexed":true,"internalType":"uint8","name":"pubKeyYParity","type":"uint8"}],"name":"Deposit","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"previousOwner","type":"address"},{"indexed":true,"internalType":"address","name":"newOwner","type":"address"}],"name":"OwnershipTransferred","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"uint256","name":"pubKeyX","type":"uint256"},{"indexed":true,"internalType":"uint8","name":"pubKeyYParity","type":"uint8"}],"name":"PublicKeySet","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"token","type":"address"},{"indexed":true,"internalType":"address","name":"to","type":"address"},{"indexed":false,"internalType":"uint256","name":"amount","type":"uint256"}],"name":"Withdrawal","type":"event"},{"inputs":[{"internalType":"address","name":"token","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"},{"internalType":"uint256","name":"_publicKeyX","type":"uint256"},{"internalType":"uint8","name":"_pubKeyYParity","type":"uint8"}],"name":"deposit","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"","type":"address"}],"name":"nonces","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"owner","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"pubKeyX","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"pubKeyYParity","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"renounceOwnership","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"_pubKeyX","type":"uint256"},{"internalType":"uint8","name":"_pubKeyYParity","type":"uint8"}],"name":"setPublicKey","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"_verifier","type":"address"}],"name":"setVerifier","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"newOwner","type":"address"}],"name":"transferOwnership","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"verifier","outputs":[{"internalType":"contract ISchnorrVerifier","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"uint256","name":"tokenIndex","type":"uint256"},{"internalType":"uint256","name":"amount","type":"uint256"},{"internalType":"address","name":"dest","type":"address"},{"internalType":"uint256","name":"nonce","type":"uint256"},{"internalType":"uint256","name":"signature","type":"uint256"},{"internalType":"address","name":"nonceTimesGeneratorAddress","type":"address"}],"name":"withdraw","outputs":[],"stateMutability":"nonpayable","type":"function"}]'
BLOCKS_CONFIRMATION = 3
BLOCK_DURATION = 5

# Initialize Web3
web3 = Web3(Web3.HTTPProvider(NODE_URL))
web3.middleware_onion.inject(geth_poa_middleware, layer=0)
contract = web3.eth.contract(address=CONTRACT_ADDRESS, abi=CONTRACT_ABI)

def get_deposits(block):
    latest_block = web3.eth.block_number
    assert block <= latest_block - BLOCKS_CONFIRMATION, 'not confirmed yet'
    events = contract.events.Deposit.create_filter(fromBlock=block, toBlock=block).get_all_entries()
    return [dict(event['args']) for event in events]

monitor_private = 'cd7d94cd90d25d8722087a85e51ce3e5d8d06d98cb9f1c02e93f646c90af0193'
monitor = PrivateKey(bytes(bytearray.fromhex(monitor_private)), raw=True)

def create_tx(deposits, from_block, to_block, timestamp):
    version = pack('>B', 1)
    chain = b'bst'
    block_range = pack('>QQ', from_block, to_block)
    tx = version + b'd' + chain + block_range + pack('>H', len(deposits))
    for deposit in deposits:
        prefix = '02' if deposit['pubKeyYParity'] == 0 else '03'
        pubKeyX = f"{deposit['pubKeyX']:#0{32}x}"[2:]
        public = bytes.fromhex(prefix + pubKeyX)
        print(deposit['tokenIndex'], deposit['amount'], timestamp, 't')
        tx += pack('>IdI', deposit['tokenIndex'], deposit['amount'], timestamp)
        tx += public
    tx += monitor.schnorr_sign(tx, bip340tag='zex')
    counter = 0
    tx += pack('>Q', counter)
    return tx

def main():
    # processed_block = web3.eth.block_number - BLOCKS_CONFIRMATION # should be queried from zex
    # print(processed_block)
    processed_block = 39493054
    sent_block = processed_block

    while True:
        latest_block = web3.eth.block_number
        if processed_block >= latest_block - BLOCKS_CONFIRMATION:
            time.sleep(BLOCK_DURATION)
            continue

        processed_block += 1
        deposits = get_deposits(processed_block)
        if len(deposits) == 0:
            print('no event', processed_block)
            continue

        block = web3.eth.get_block(processed_block)
        tx = create_tx(deposits, sent_block + 1, processed_block, block['timestamp'])
        requests.post('http://localhost:9513/api/txs', json=[tx.decode('latin-1')])
        # to check if request is applied, query latest processed block from zex
        sent_block = processed_block

if __name__ == "__main__":
    main()

