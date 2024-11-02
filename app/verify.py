from struct import unpack
import multiprocessing

from eth_hash.auto import keccak
from loguru import logger
from secp256k1 import PublicKey

from . import DEPOSIT_MONITOR_PUB_KEY

DEPOSIT, WITHDRAW, BUY, SELL, CANCEL, REGISTER = b"dwbscr"

monitor_pub = PublicKey(bytes.fromhex(DEPOSIT_MONITOR_PUB_KEY), raw=True)


def order_msg(tx):
    msg = f"""v: {tx[0]}\nname: {"buy" if tx[1] == BUY else "sell"}\nbase token: {tx[2:5].decode("ascii")}:{unpack(">I", tx[5:9])[0]}\nquote token: {tx[9:12].decode("ascii")}:{unpack(">I", tx[12:16])[0]}\namount: {unpack(">d", tx[16:24])[0]}\nprice: {unpack(">d", tx[24:32])[0]}\nt: {unpack(">I", tx[32:36])[0]}\nnonce: {unpack(">I", tx[36:40])[0]}\npublic: {tx[40:73].hex()}\n"""
    msg = "".join(("\x19Ethereum Signed Message:\n", str(len(msg)), msg))
    return msg.encode()


def withdraw_msg(tx):
    msg = f"v: {tx[0]}\n"
    msg += "name: withdraw\n"
    msg += f'token: {tx[2:5].decode("ascii")}:{unpack(">I", tx[5:9])[0]}\n'
    msg += f'amount: {unpack(">d", tx[9:17])[0]}\n'
    msg += f'to: {"0x" + tx[17:37].hex()}\n'
    msg += f't: {unpack(">I", tx[37:41])[0]}\n'
    msg += f'nonce: {unpack(">I", tx[41:45])[0]}\n'
    msg += f"public: {tx[45:78].hex()}\n"
    msg = "\x19Ethereum Signed Message:\n" + str(len(msg)) + msg
    return msg.encode()


def register_msg():
    msg = "Welcome to ZEX."
    msg = "".join(("\x19Ethereum Signed Message:\n", str(len(msg)), msg))
    return msg.encode()


def cancel_msg(tx: bytes):
    msg = f"""v: {tx[0]}\nname: cancel\nslice: {tx[2:41].hex()}\npublic: {tx[41:74].hex()}\n"""
    msg = "".join(("\x19Ethereum Signed Message:\n", str(len(msg)), msg))
    return msg.encode()


def __verify(txs):
    res = [None] * len(txs)
    for i, tx in enumerate(txs):
        name = tx[1]
        if name == DEPOSIT:
            msg = tx[: -(8 + 64)]
            sig = tx[-(8 + 64): -8]
            verified = monitor_pub.schnorr_verify(msg, sig, bip340tag="zex")

        elif name == WITHDRAW:
            msg, pubkey, sig = withdraw_msg(tx), tx[45:78], tx[78: 78 + 64]
            logger.info(f"withdraw request pubkey: {pubkey}")
            pubkey = PublicKey(pubkey, raw=True)
            sig = pubkey.ecdsa_deserialize_compact(sig)
            msg_hash = keccak(msg)
            verified = pubkey.ecdsa_verify(msg_hash, sig, raw=True)

        else:
            if name == CANCEL:
                msg, pubkey, sig = cancel_msg(tx), tx[41:74], tx[74: 74 + 64]
            elif name in (BUY, SELL):
                msg, pubkey, sig = order_msg(tx), tx[40:73], tx[73: 73 + 64]
            elif name == REGISTER:
                msg, pubkey, sig = register_msg(), tx[2:35], tx[35: 35 + 64]
            else:
                res[i] = False
                continue
            pubkey = PublicKey(pubkey, raw=True)
            sig = pubkey.ecdsa_deserialize_compact(sig)
            msg_hash = keccak(msg)
            verified = pubkey.ecdsa_verify(msg_hash, sig, raw=True)

        res[i] = verified
    return res


def chunkify(lst, n_chunks):
    for i in range(0, len(lst), n_chunks):
        yield lst[i: i + n_chunks]


# This is needed to prevent the verfication from crashing
n_chunks = multiprocessing.cpu_count()
pool = multiprocessing.Pool(processes=n_chunks)

def verify(txs):
    chunks = list(chunkify(txs, len(txs) // n_chunks + 1))
    results = pool.map(__verify, chunks)
    # results = [__verify(x) for x in chunks]

    i = 0
    for sublist in results:
        for verified in sublist:
            if not verified:
                txs[i] = None
            i += 1
