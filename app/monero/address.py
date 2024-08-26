import re
import struct
from binascii import hexlify, unhexlify

from . import base58, const, numbers
from .keccak import keccak_256

_ADDR_REGEX = re.compile(
    r"^[123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz]{95}$"
)
_IADDR_REGEX = re.compile(
    r"^[123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz]{106}$"
)


class BaseAddress:
    label = None

    def __init__(self, addr, label=None):
        addr = addr.decode() if isinstance(addr, bytes) else str(addr)
        if not _ADDR_REGEX.match(addr):
            raise ValueError(
                "Address must be 95 characters long base58-encoded string, "
                f"is {addr} ({len(addr)} chars length)"
            )
        self._decode(addr)
        self.label = label or self.label

    def view_key(self):
        """Returns public view key.

        :rtype: str
        """
        return hexlify(self._decoded[33:65]).decode()

    def spend_key(self):
        """Returns public spend key.

        :rtype: str
        """
        return hexlify(self._decoded[1:33]).decode()

    @property
    def net(self):
        return const.NETS[self._valid_netbytes.index(self._decoded[0])]

    def _decode(self, address):
        self._decoded = bytearray(unhexlify(base58.decode(address)))
        checksum = self._decoded[-4:]
        if checksum != keccak_256(self._decoded[:-4]).digest()[:4]:
            raise ValueError(f"Invalid checksum in address {address}")
        if self._decoded[0] not in self._valid_netbytes:
            raise ValueError(
                "Invalid address netbyte {nb}. Allowed values are: {allowed}".format(
                    nb=self._decoded[0],
                    allowed=", ".join(f"{b:02x}" for b in self._valid_netbytes),
                )
            )

    def __repr__(self):
        return base58.encode(hexlify(self._decoded))

    def __eq__(self, other):
        if isinstance(other, BaseAddress | str):
            return str(self) == str(other)
        return super().__eq__(other)

    def __hash__(self):
        return hash(str(self))

    def __format__(self, spec):
        return format(str(self), spec)


class Address(BaseAddress):
    """Monero address.

    Address of this class is the master address for a :class:`Wallet <monero.wallet.Wallet>`.

    :param address: a Monero address as string-like object
    :param label: a label for the address (defaults to `None`)
    """

    _valid_netbytes = const.MASTERADDR_NETBYTES

    def with_payment_id(self, payment_id=0):
        """Integrates payment id into the address.

        :param payment_id: int, hexadecimal string or :class:`PaymentID <monero.numbers.PaymentID>`
                    (max 64-bit long)

        :rtype: `IntegratedAddress`
        :raises: `TypeError` if the payment id is too long
        """
        payment_id = numbers.PaymentID(payment_id)
        if not payment_id.is_short():
            raise TypeError(
                f"Payment ID {payment_id} has more than 64 bits and cannot be integrated"
            )
        prefix = const.INTADDRR_NETBYTES[const.NETS.index(self.net)]
        data = (
            bytearray([prefix])
            + self._decoded[1:65]
            + struct.pack(">Q", int(payment_id))
        )
        checksum = bytearray(keccak_256(data).digest()[:4])
        return IntegratedAddress(base58.encode(hexlify(data + checksum)))


class IntegratedAddress(Address):
    """Monero integrated address.

    A master address integrated with payment id (short one, max 64 bit).
    """

    _valid_netbytes = const.INTADDRR_NETBYTES

    def __init__(self, address):
        address = address.decode() if isinstance(address, bytes) else str(address)
        if not _IADDR_REGEX.match(address):
            raise ValueError(
                "Integrated address must be 106 characters long base58-encoded string, "
                f"is {address} ({len(address)} chars length)"
            )
        self._decode(address)

    def payment_id(self):
        """Returns the integrated payment id.

        :rtype: :class:`PaymentID <monero.numbers.PaymentID>`
        """
        return numbers.PaymentID(hexlify(self._decoded[65:-4]).decode())

    def base_address(self):
        """Returns the base address without payment id.
        :rtype: :class:`Address`
        """
        prefix = const.MASTERADDR_NETBYTES[const.NETS.index(self.net)]
        data = bytearray([prefix]) + self._decoded[1:65]
        checksum = keccak_256(data).digest()[:4]
        return Address(base58.encode(hexlify(data + checksum)))
