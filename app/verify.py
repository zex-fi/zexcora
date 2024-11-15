from hashlib import sha256
from itertools import repeat
from struct import unpack
import multiprocessing
import os

from eth_hash.auto import keccak
from loguru import logger
from pyfrost.frost import (
    code_to_pub,
    pub_compress,
    verify_group_signature,
)
from secp256k1 import PublicKey
import numpy as np

from app.singleton import SingletonMeta

BTC_XMR_DEPOSIT, DEPOSIT, WITHDRAW, BUY, SELL, CANCEL, REGISTER = b"xdwbscr"


def order_msg(tx: bytes) -> bytes:
    """Format order message for verification."""
    msg = f"""v: {tx[0]}\nname: {"buy" if tx[1] == BUY else "sell"}\nbase token: {tx[2:5].decode("ascii")}:{unpack(">I", tx[5:9])[0]}\nquote token: {tx[9:12].decode("ascii")}:{unpack(">I", tx[12:16])[0]}\namount: {np.format_float_positional(unpack(">d", tx[16:24])[0], trim="0")}\nprice: {np.format_float_positional(unpack(">d", tx[24:32])[0], trim="0")}\nt: {unpack(">I", tx[32:36])[0]}\nnonce: {unpack(">I", tx[36:40])[0]}\npublic: {tx[40:73].hex()}\n"""
    msg = "".join(("\x19Ethereum Signed Message:\n", str(len(msg)), msg))
    return msg.encode()


def withdraw_msg(tx: bytes) -> bytes:
    """Format withdrawal message for verification."""
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


def register_msg() -> bytes:
    """Format registration message for verification."""
    msg = "Welcome to ZEX."
    msg = "".join(("\x19Ethereum Signed Message:\n", str(len(msg)), msg))
    return msg.encode()


def cancel_msg(tx: bytes) -> bytes:
    """Format cancellation message for verification."""
    msg = f"""v: {tx[0]}\nname: cancel\nslice: {tx[2:41].hex()}\npublic: {tx[41:74].hex()}\n"""
    msg = "".join(("\x19Ethereum Signed Message:\n", str(len(msg)), msg))
    return msg.encode()


def _verify_single_tx(
        tx: bytes,
        deposit_monitor_pub_key: int,
        btc_xmr_monitor_pub: bytes,
) -> bool:
    """Verify a single transaction."""
    name = tx[1]

    if name == DEPOSIT:
        msg = tx[:-74]
        msg_hash = sha256(msg).hexdigest()
        nonce, sig = unpack(">42s32s", tx[-74:])

        return verify_group_signature(
            {
                "key_type": "ETH",
                "public_key": pub_compress(code_to_pub(int(deposit_monitor_pub_key))),
                "message": msg_hash,
                "signature": int.from_bytes(sig, "big"),
                "nonce": nonce.decode(),
            }
        )

    elif name == BTC_XMR_DEPOSIT:
        msg = tx[:-64]
        sig = tx[-64:]
        pubkey = PublicKey(btc_xmr_monitor_pub, raw=True)
        return pubkey.schnorr_verify(msg, sig, bip340tag="zex")

    elif name == WITHDRAW:
        msg, pubkey, sig = withdraw_msg(tx), tx[45:78], tx[78: 78 + 64]
        logger.info(f"withdraw request pubkey: {pubkey}")
        pubkey = PublicKey(pubkey, raw=True)
        sig = pubkey.ecdsa_deserialize_compact(sig)
        msg_hash = keccak(msg)
        return pubkey.ecdsa_verify(msg_hash, sig, raw=True)

    else:
        if name == CANCEL:
            msg, pubkey, sig = cancel_msg(tx), tx[41:74], tx[74: 74 + 64]
        elif name in (BUY, SELL):
            msg, pubkey, sig = order_msg(tx), tx[40:73], tx[73: 73 + 64]
        elif name == REGISTER:
            msg, pubkey, sig = register_msg(), tx[2:35], tx[35: 35 + 64]
        else:
            return False

        pubkey = PublicKey(pubkey, raw=True)
        sig = pubkey.ecdsa_deserialize_compact(sig)
        msg_hash = keccak(msg)
        return pubkey.ecdsa_verify(msg_hash, sig, raw=True)


def _verify_chunk(
        txs: list[bytes], deposit_monitor_pub_key: int, btc_xmr_monitor_pub: bytes
) -> list[bool]:
    """Verify a chunk of transactions."""
    return [
        _verify_single_tx(tx, deposit_monitor_pub_key, btc_xmr_monitor_pub)
        for tx in txs
    ]


class TransactionVerifier(metaclass=SingletonMeta):
    def __init__(self, num_processes: int | None = None):
        """
        Initialize the TransactionVerifier with a multiprocessing pool.

        Args:
            num_processes: Number of processes to use. Defaults to CPU count if None.
        """
        self.num_processes = num_processes or multiprocessing.cpu_count()
        self.pool = multiprocessing.Pool(processes=self.num_processes)

        # Initialize environment variables
        self.deposit_monitor_pub_key = os.getenv("DEPOSIT_MONITOR_PUB_KEY")
        self.btc_xmr_deposit_monitor_pub_key = os.getenv(
            "BTC_XMR_DEPOSIT_MONITOR_PUB_KEY"
        )
        self.btc_xmr_monitor_pub = PublicKey(
            bytes.fromhex(self.btc_xmr_deposit_monitor_pub_key), raw=True
        )

    def __enter__(self):
        """Context manager entry point."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point - ensures proper cleanup of the pool."""
        self.cleanup()

    def cleanup(self):
        """Clean up resources by closing and joining the multiprocessing pool."""
        if hasattr(self, "pool"):
            self.pool.close()
            self.pool.join()

    @staticmethod
    def _chunkify(lst: list, n_chunks: int) -> list[list]:
        """Split a list into n roughly equal chunks."""
        chunk_size = len(lst) // n_chunks + 1
        return [lst[i: i + chunk_size] for i in range(0, len(lst), chunk_size)]

    def verify(self, txs: list[bytes]) -> list[bytes | None]:
        """
        Verify a list of transactions using multiple processes.

        Args:
            txs: List of transactions to verify

        Returns:
            List of verified transactions (None for invalid transactions)
        """
        chunks = self._chunkify(txs, self.num_processes)

        results = self.pool.starmap(
            _verify_chunk,
            zip(
                chunks,
                repeat(int(self.deposit_monitor_pub_key)),
                repeat(bytes.fromhex(self.btc_xmr_deposit_monitor_pub_key)),
            ),
        )

        verified_txs = txs.copy()
        i = 0
        for chunk_results in results:
            for verified in chunk_results:
                if not verified:
                    verified_txs[i] = None
                i += 1

        return verified_txs
