from decimal import Decimal
from struct import unpack

from pydantic import BaseModel


class MarketTransaction:
    def __init__(self, tx: bytes):
        assert len(tx) == 145, f"invalid transaction len(tx): {len(tx)}"
        self.raw_tx = tx

    @property
    def version(self):
        return self.raw_tx[0]

    @property
    def operation(self):
        return self.raw_tx[1]

    @property
    def base_chain(self):
        return self.raw_tx[2:5].upper().decode()

    @property
    def base_token_id(self):
        return unpack(">I", self.raw_tx[5:9])[0]

    @property
    def quote_chain(self):
        return self.raw_tx[9:12].upper().decode()

    @property
    def quote_token_id(self):
        return unpack(">I", self.raw_tx[12:16])[0]

    @property
    def amount(self):
        return unpack(">d", self.raw_tx[16:24])[0]

    @property
    def price(self):
        return unpack(">d", self.raw_tx[24:32])[0]

    @property
    def time(self):
        return unpack(">I", self.raw_tx[32:36])[0]

    @property
    def nonce(self):
        return unpack(">I", self.raw_tx[36:40])[0]

    @property
    def public(self):
        return self.raw_tx[40:73]

    @property
    def signature(self):
        return self.raw_tx[73:137]

    @property
    def index(self):
        return unpack(">Q", self.raw_tx[137:145])[0]

    @property
    def pair(self):
        return f"{self.base_chain}:{self.base_token_id}-{self.quote_chain}:{self.quote_token_id}"

    @property
    def base_token(self):
        return f"{self.base_chain}:{self.base_token_id}"

    @property
    def quote_token(self):
        return f"{self.quote_chain}:{self.quote_token_id}"

    @property
    def order_slice(self):
        return self.raw_tx[2:41]

    def hex(self):
        return self.raw_tx.hex()

    def __lt__(self, other: "MarketTransaction"):
        return self.time < other.time

    def __eq__(self, other):
        if id(self) == id(other):
            return True
        if not isinstance(other, MarketTransaction):
            return False

        return self.signature == other.signature


class Deposit(BaseModel):
    token: str
    amount: Decimal
    time: int


class DepositTransaction(BaseModel):
    version: int
    operation: str
    chain: str
    from_block: int
    to_block: int
    deposits: list[Deposit]
    signature: bytes

    @classmethod
    def from_tx(cls, tx: bytes) -> "DepositTransaction":
        deposits = []
        deposit_count = unpack(">H", tx[21:23])[0]
        for i in range(deposit_count):
            offset = 23 + i * 49
            deposits.append(
                Deposit(
                    token=unpack(">I", tx[offset : offset + 4])[0],
                    amount=unpack(">d", tx[offset + 4 : offset + 8])[0],
                    time=unpack(">I", tx[offset + 8 : offset + 12])[0],
                    public=tx[offset + 12 : offset + 33],
                )
            )

        return DepositTransaction(
            version=tx[0],
            operation=tx[1],
            chain=tx[2:5],
            from_block=unpack(">Q", tx[5:13])[0],
            to_block=unpack(">Q", tx[13:21])[0],
            deposits=deposits,
            signature=tx[-32:],
        )


class WithdrawTransaction(BaseModel):
    version: int
    operation: str
    chain: str
    token_id: int
    amount: float
    dest: str
    time: int
    nonce: int
    public: bytes
    signature: bytes

    raw_tx: bytes | None

    @classmethod
    def from_tx(cls, tx: bytes) -> "WithdrawTransaction":
        assert len(tx) == 142, f"invalid transaction len(tx): {len(tx)}"
        return WithdrawTransaction(
            version=tx[0],
            operation=chr(tx[1]),
            chain=tx[2:5].upper(),
            token_id=unpack(">I", tx[5:9])[0],
            amount=unpack(">d", tx[9:17])[0],
            dest="0x" + tx[17:37].hex(),
            time=unpack(">I", tx[37:41])[0],
            nonce=unpack(">I", tx[41:45])[0],
            public=tx[45:78],
            signature=tx[78:142],
            raw_tx=tx,
        )

    @property
    def internal_token(self):
        return f"{self.chain}:{self.token_id}"

    def hex(self):
        return self.raw_tx.hex()
