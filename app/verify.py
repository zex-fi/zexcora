from dataclasses import dataclass
from hashlib import sha256
from itertools import repeat
from struct import calcsize, unpack
from struct import error as struct_error
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

from .config import settings

DEPOSIT, WITHDRAW, BUY, SELL, CANCEL, REGISTER = b"dwbscr"

w3 = Web3()


class MessageFormatError(Exception):
    """Custom exception for message formatting errors."""

    pass


def order_msg(tx: bytes) -> bytes:
    """
    Format order message for verification.

    Args:
        tx: Transaction bytes containing order data

    Returns:
        Formatted message bytes

    Raises:
        MessageFormatError: If message formatting fails
    """
    try:
        if len(tx) < 4:
            raise MessageFormatError("Transaction too short for header")

        # Unpack header
        try:
            version, side, base_token_len, quote_token_len = unpack(">B B B B", tx[:4])
        except struct_error as e:
            raise MessageFormatError(f"Failed to unpack header: {e}")

        # Validate token lengths
        if base_token_len == 0 or quote_token_len == 0:
            raise MessageFormatError("Invalid token length")

        # Create and validate format string
        order_format = f">{base_token_len}s {quote_token_len}s d d I I 33s"
        order_format_size = calcsize(order_format)

        if len(tx) < 4 + order_format_size:
            raise MessageFormatError("Transaction too short for order data")

        # Unpack order data
        try:
            base_token, quote_token, amount, price, t, nonce, public = unpack(
                order_format, tx[4 : 4 + order_format_size]
            )
        except struct_error as e:
            raise MessageFormatError(f"Failed to unpack order data: {e}")

        # Decode tokens
        try:
            base_token = base_token.decode("ascii")
            quote_token = quote_token.decode("ascii")
        except UnicodeDecodeError as e:
            raise MessageFormatError(f"Invalid token encoding: {e}")

        # Validate side
        if side not in (BUY, SELL):
            raise MessageFormatError(f"Invalid order side: {side}")

        # Format message
        try:
            public = public.hex()
            msg = f"""v: {version}
name: {"buy" if side == BUY else "sell"}
base token: {base_token}
quote token: {quote_token}
amount: {np.format_float_positional(amount, trim="0")}
price: {np.format_float_positional(price, trim="0")}
t: {t}
nonce: {nonce}
public: {public}
"""
            msg = "".join(("\x19Ethereum Signed Message:\n", str(len(msg)), msg))
            logger.debug("Order message created successfully", message=msg)
            return msg.encode()
        except Exception as e:
            raise MessageFormatError(f"Failed to format message: {e}")

    except MessageFormatError:
        raise
    except Exception as e:
        raise MessageFormatError(f"Unexpected error formatting order message: {e}")


def withdraw_msg(tx: bytes) -> bytes:
    """
    Format withdrawal message for verification.

    Args:
        tx: Transaction bytes containing withdrawal data

    Returns:
        Formatted message bytes

    Raises:
        MessageFormatError: If message formatting fails
    """
    try:
        if len(tx) < 3:
            raise MessageFormatError("Transaction too short for header")

        # Unpack header
        try:
            version, token_len = unpack(">B x B", tx[:3])
        except struct_error as e:
            raise MessageFormatError(f"Failed to unpack header: {e}")

        # Validate token length
        if token_len == 0:
            raise MessageFormatError("Invalid token length")

        # Create and validate format string
        withdraw_format = f">3s {token_len}s d 20s I I 33s"
        format_size = calcsize(withdraw_format)

        if len(tx) < 3 + format_size:
            raise MessageFormatError("Transaction too short for withdrawal data")

        # Unpack withdrawal data
        try:
            token_chain, token_name, amount, destination, t, nonce, public = unpack(
                withdraw_format, tx[3 : 3 + format_size]
            )
        except struct_error as e:
            raise MessageFormatError(f"Failed to unpack withdrawal data: {e}")

        # Decode tokens
        try:
            token_chain = token_chain.decode("ascii")
            token_name = token_name.decode("ascii")
        except UnicodeDecodeError as e:
            raise MessageFormatError(f"Invalid token encoding: {e}")

        # Format message
        try:
            msg = f"""v: {version}
name: withdraw
token chain: {token_chain}
token name: {token_name}
amount: {amount}
to: 0x{destination.hex()}
t: {t}
nonce: {nonce}
public: {public.hex()}
"""
            msg = "\x19Ethereum Signed Message:\n" + str(len(msg)) + msg
            logger.debug("Withdrawal message created successfully", message=msg)
            return msg.encode()
        except Exception as e:
            raise MessageFormatError(f"Failed to format message: {e}")

    except MessageFormatError:
        raise
    except Exception as e:
        raise MessageFormatError(f"Unexpected error formatting withdrawal message: {e}")


def register_msg() -> bytes:
    """
    Format registration message for verification.

    Returns:
        Formatted message bytes

    Raises:
        MessageFormatError: If message formatting fails
    """
    try:
        msg = "Welcome to ZEX."
        msg = "".join(("\x19Ethereum Signed Message:\n", str(len(msg)), msg))
        logger.debug("Registration message created successfully", message=msg)
        return msg.encode()
    except Exception as e:
        raise MessageFormatError(f"Failed to format registration message: {e}")


def cancel_msg(tx: bytes) -> bytes:
    """
    Format cancellation message for verification.

    Args:
        tx: Transaction bytes containing cancellation data

    Returns:
        Formatted message bytes

    Raises:
        MessageFormatError: If message formatting fails
    """
    try:
        if (
            len(tx) < 99
        ):  # Minimum length check (1 byte version + 1 byte type + minimum order tx + 33 bytes public key)
            raise MessageFormatError("Transaction too short for cancellation data")

        try:
            order_tx = tx[2:-97].hex()
            public_key = tx[-97:-64].hex()
        except Exception as e:
            raise MessageFormatError(f"Failed to hex encode transaction data: {e}")

        try:
            msg = f"""v: {tx[0]}
name: cancel
slice: {order_tx}
public: {public_key}
"""
            msg = "".join(("\x19Ethereum Signed Message:\n", str(len(msg)), msg))
            logger.debug("Cancellation message created successfully", message=msg)
            return msg.encode()
        except Exception as e:
            raise MessageFormatError(f"Failed to format message: {e}")

    except MessageFormatError:
        raise
    except Exception as e:
        raise MessageFormatError(
            f"Unexpected error formatting cancellation message: {e}"
        )


@dataclass
class VerificationResult:
    """Result of transaction verification with detailed error information."""

    is_valid: bool
    error_type: str | None = None
    error_message: str | None = None


def verify_single_tx(
    tx: bytes,
    deposit_monitor_pub_key: int,
    deposit_shield_address: str,
) -> VerificationResult:
    """
    Verify a single transaction with comprehensive error handling.

    Returns:
        VerificationResult containing verification status and error details if any.
    """
    try:
        name = tx[1]
    except IndexError:
        logger.error("Transaction data too short to contain name")
        return VerificationResult(
            is_valid=False,
            error_type="InvalidFormat",
            error_message="Transaction data too short to contain name",
        )

    try:
        if name == DEPOSIT:
            result = _verify_deposit_tx(
                tx, deposit_monitor_pub_key, deposit_shield_address
            )
            if not result.is_valid:
                logger.debug(f"verify deposit failed: {result.error_message}")
            return result
        elif name == WITHDRAW:
            result = _verify_withdraw_tx(tx)
            if not result.is_valid:
                logger.debug(f"verify withdraw failed: {result.error_message}")
            return result
        elif name in (CANCEL, BUY, SELL, REGISTER):
            result = _verify_standard_tx(tx, name)
            if not result.is_valid:
                logger.debug(f"verify order failed: {result.error_message}")
            return result
        else:
            logger.error(f"Unknown transaction type: {name}")
            return VerificationResult(
                is_valid=False,
                error_type="InvalidTransactionType",
                error_message=f"Unknown transaction type: {name}",
            )
    except Exception as e:
        logger.exception(
            "Unexpected error verifying transaction",
            transaction_type=chr(name),
            error=str(e),
        )
        return VerificationResult(
            is_valid=False,
            error_type="UnexpectedError",
            error_message=f"Unexpected error: {str(e)}",
        )


def _verify_deposit_tx(
    tx: bytes, deposit_monitor_pub_key: int, deposit_shield_address: str
) -> VerificationResult:
    """Verify deposit transaction."""
    try:
        msg = tx[:-206]
        msg_hash = sha256(msg).hexdigest()
        nonce, frost_sig, ecdsa_sig = unpack(">42s 32s 132s", tx[-206:])

        # Verify FROST signature
        try:
            frost_verified = verify_group_signature(
                {
                    "key_type": "ETH",
                    "public_key": pub_compress(
                        code_to_pub(int(deposit_monitor_pub_key))
                    ),
                    "message": msg_hash,
                    "signature": int.from_bytes(frost_sig, "big"),
                    "nonce": nonce.decode(),
                }
            )
        except ValueError as e:
            logger.error(f"FROST signature verification failed: {e}")
            return VerificationResult(
                is_valid=False,
                error_type="FROSTVerificationError",
                error_message=f"FROST signature verification failed: {str(e)}",
            )

        # Verify ECDSA signature
        try:
            eth_signed_message = encode_defunct(tx[:-206])
            recovered_address = w3.eth.account.recover_message(
                eth_signed_message, signature=bytes.fromhex(ecdsa_sig.decode()[2:])
            )
            ecdsa_verified = recovered_address == deposit_shield_address
        except ValueError as e:
            logger.error(f"ECDSA signature verification failed: {e}")
            return VerificationResult(
                is_valid=False,
                error_type="ECDSAVerificationError",
                error_message=f"ECDSA signature verification failed: {str(e)}",
            )

        return VerificationResult(is_valid=frost_verified and ecdsa_verified)
    except Exception as e:
        logger.exception(f"Error verifying deposit: {e}")
        return VerificationResult(
            is_valid=False,
            error_type="DepositVerificationError",
            error_message=f"Error verifying deposit: {str(e)}",
        )


def _verify_withdraw_tx(tx: bytes) -> VerificationResult:
    """Verify withdrawal transaction."""
    try:
        msg, pubkey, sig = withdraw_msg(tx), tx[-97:-64], tx[-64:]
        logger.debug(f"Withdraw request pubkey: {pubkey.hex()}")
        pubkey = PublicKey(pubkey, raw=True)
        sig = pubkey.ecdsa_deserialize_compact(sig)
        msg_hash = keccak(msg)
        return VerificationResult(is_valid=pubkey.ecdsa_verify(msg_hash, sig, raw=True))
    except Exception as e:
        logger.exception(f"Error verifying withdrawal: {e}")
        return VerificationResult(
            is_valid=False,
            error_type="WithdrawVerificationError",
            error_message=f"Error verifying withdrawal: {str(e)}",
        )


def _verify_standard_tx(tx: bytes, tx_type: int) -> VerificationResult:
    """Verify standard transactions (CANCEL, BUY, SELL, REGISTER)."""
    try:
        if tx_type == CANCEL:
            msg, pubkey, sig = cancel_msg(tx), tx[-97:-64], tx[-64:]
        elif tx_type in (BUY, SELL):
            msg = order_msg(tx)
            pubkey, sig = tx[-97:-64], tx[-64:]
        elif tx_type == REGISTER:
            msg, pubkey, sig = register_msg(), tx[2:35], tx[35 : 35 + 64]
        else:
            logger.error(f"Unsupported transaction type: {chr(tx_type)}")
            return VerificationResult(
                is_valid=False,
                error_type="InvalidTransactionType",
                error_message=f"Unsupported transaction type: {chr(tx_type)}",
            )

        pubkey = PublicKey(pubkey, raw=True)
        sig = pubkey.ecdsa_deserialize_compact(sig)
        msg_hash = keccak(msg)
        is_verified = pubkey.ecdsa_verify(msg_hash, sig, raw=True)

        if not is_verified:
            logger.error(
                "Failed to verify transaction",
                transaction_type=chr(tx_type),
                pubkey=pubkey.serialize().hex(),
            )

        return VerificationResult(is_valid=is_verified)
    except Exception as e:
        logger.exception(
            f"Error verifying {chr(tx_type)} transaction: {e}",
            transaction_type=chr(tx_type),
        )
        return VerificationResult(
            is_valid=False,
            error_type="StandardTxVerificationError",
            error_message=f"Error verifying {chr(tx_type)} transaction: {str(e)}",
        )


def _verify_chunk(
    txs: list[bytes],
    deposit_monitor_pub_key: int,
    deposit_shield_address: str,
) -> list[bool]:
    """Verify a chunk of transactions."""
    return [
        verify_single_tx(
            tx,
            deposit_monitor_pub_key,
            deposit_shield_address,
        ).is_valid
        for tx in txs
    ]


class TransactionVerifier:
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
