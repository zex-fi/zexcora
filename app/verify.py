from hashlib import sha256
from itertools import repeat
from struct import calcsize, unpack
import multiprocessing

from eth_account.messages import encode_defunct
from eth_hash.auto import keccak
from eth_utils.address import to_checksum_address
from loguru import logger
from pyfrost.frost import (
    code_to_pub,
    pub_compress,
    verify_group_signature,
)
from secp256k1 import PublicKey
from web3 import Web3
import numpy as np

from app.singleton import SingletonMeta

from .config import settings

BTC_DEPOSIT, DEPOSIT, WITHDRAW, BUY, SELL, CANCEL, REGISTER = b"xdwbscr"

w3 = Web3()


def order_msg(tx: bytes) -> bytes:
    """Format order message for verification."""
    version, side, base_token_len, quote_token_len = unpack(">B B B B", tx[:4])

    order_format = f">{base_token_len}s {quote_token_len}s d d I I 33s"
    order_format_size = calcsize(order_format)
    base_token, quote_token, amount, price, t, nonce, public = unpack(
        order_format, tx[4 : 4 + order_format_size]
    )
    base_token = base_token.decode("ascii")
    quote_token = quote_token.decode("ascii")
    public = public.hex()

    msg = f"""v: {version}\nname: {"buy" if side == BUY else "sell"}\nbase token: {base_token}\nquote token: {quote_token}\namount: {np.format_float_positional(amount, trim="0")}\nprice: {np.format_float_positional(price, trim="0")}\nt: {t}\nnonce: {nonce}\npublic: {public}\n"""
    msg = "".join(("\x19Ethereum Signed Message:\n", str(len(msg)), msg))
    return msg.encode()


def withdraw_msg(tx: bytes) -> bytes:
    """Format withdrawal message for verification."""
    version, token_len = unpack(">B x B", tx[:3])

    withdraw_format = f">{token_len}s d 20s I I 33s"
    token, amount, to, t, nonce, public = unpack(withdraw_format, tx[4:])

    msg = f"v: {version}\n"
    msg += "name: withdraw\n"
    msg += f"token: {token}\n"
    msg += f"amount: {amount}\n"
    msg += f'to: {"0x" + to.hex()}\n'
    msg += f"t: {t}\n"
    msg += f"nonce: {nonce}\n"
    msg += f"public: {public}\n"
    msg = "\x19Ethereum Signed Message:\n" + str(len(msg)) + msg
    return msg.encode()


def register_msg() -> bytes:
    """Format registration message for verification."""
    msg = "Welcome to ZEX."
    msg = "".join(("\x19Ethereum Signed Message:\n", str(len(msg)), msg))
    return msg.encode()


def cancel_msg(tx: bytes) -> bytes:
    """Format cancellation message for verification."""
    order_tx = tx[2:-33].hex()
    msg = f"""v: {tx[0]}\nname: cancel\nslice: {order_tx}\npublic: {tx[-33:].hex()}\n"""
    msg = "".join(("\x19Ethereum Signed Message:\n", str(len(msg)), msg))
    return msg.encode()


def _verify_single_tx(
    tx: bytes,
    deposit_monitor_pub_key: int,
    deposit_shield_address: str,
    btc_monitor_pub: bytes,
) -> bool:
    """Verify a single transaction."""
    name = tx[1]

    if name == DEPOSIT:
        msg = tx[:-206]
        msg_hash = sha256(msg).hexdigest()
        nonce, frost_sig, ecdsa_sig = unpack(">42s 32s 132s", tx[-206:])

        frost_verified = verify_group_signature(
            {
                "key_type": "ETH",
                "public_key": pub_compress(code_to_pub(int(deposit_monitor_pub_key))),
                "message": msg_hash,
                "signature": int.from_bytes(frost_sig, "big"),
                "nonce": nonce.decode(),
            }
        )

        # Encode the message using Ethereum's signed message structure
        eth_signed_message = encode_defunct(tx[:-206])

        recovered_address = w3.eth.account.recover_message(
            eth_signed_message, signature=bytes.fromhex(ecdsa_sig.decode()[2:])
        )
        ecdsa_verified = recovered_address == deposit_shield_address

        return frost_verified and ecdsa_verified
    elif name == BTC_DEPOSIT:
        msg = tx[:-64]
        sig = tx[-64:]
        pubkey = PublicKey(btc_monitor_pub, raw=True)
        return pubkey.schnorr_verify(msg, sig, bip340tag="zex")
    elif name == WITHDRAW:
        msg, pubkey, sig = withdraw_msg(tx), tx[45:78], tx[78 : 78 + 64]
        logger.info(f"withdraw request pubkey: {pubkey}")
        pubkey = PublicKey(pubkey, raw=True)
        sig = pubkey.ecdsa_deserialize_compact(sig)
        msg_hash = keccak(msg)
        return pubkey.ecdsa_verify(msg_hash, sig, raw=True)
    else:
        if name == CANCEL:
            msg, pubkey, sig = cancel_msg(tx), tx[-97:-64], tx[-64:]
        elif name in (BUY, SELL):
            msg = order_msg(tx)
            pubkey, sig = tx[-97:-64], tx[-64:]
        elif name == REGISTER:
            msg, pubkey, sig = register_msg(), tx[2:35], tx[35 : 35 + 64]
        else:
            return False

        pubkey = PublicKey(pubkey, raw=True)
        sig = pubkey.ecdsa_deserialize_compact(sig)
        msg_hash = keccak(msg)
        return pubkey.ecdsa_verify(msg_hash, sig, raw=True)


def _verify_chunk(
    txs: list[bytes],
    deposit_monitor_pub_key: int,
    deposit_shield_address: str,
    btc_monitor_pub: bytes,
) -> list[bool]:
    """Verify a chunk of transactions."""
    return [
        _verify_single_tx(
            tx,
            deposit_monitor_pub_key,
            deposit_shield_address,
            btc_monitor_pub,
        )
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
        self.deposit_monitor_pub_key = settings.zex.keys.deposit_public_key
        self.deposit_shield_address = to_checksum_address(
            settings.zex.keys.deposit_shield_address
        )
        self.btc_deposit_monitor_pub_key = settings.zex.keys.btc_deposit_public_key
        self.btc_monitor_pub = PublicKey(
            bytes.fromhex(self.btc_deposit_monitor_pub_key), raw=True
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
        return [lst[i : i + chunk_size] for i in range(0, len(lst), chunk_size)]

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
                repeat(self.deposit_shield_address),
                repeat(bytes.fromhex(self.btc_deposit_monitor_pub_key)),
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
