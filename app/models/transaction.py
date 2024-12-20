from decimal import Decimal
from struct import calcsize, unpack

from pydantic import BaseModel


class Deposit(BaseModel):
    chain: str
    name: str
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
    token_chain: str
    token_name: str
    amount: Decimal
    destination: str
    time: int
    nonce: int
    public: bytes
    signature: bytes

    raw_tx: bytes | None

    @classmethod
    def from_tx(cls, tx: bytes) -> "WithdrawTransaction":
        version, token_len = unpack(">B x B", tx[:3])

        withdraw_format = f">3s {token_len}s d 20s I I 33s"
        token_chain, token_name, amount, destination, t, nonce, public = unpack(
            withdraw_format, tx[3 : 3 + calcsize(withdraw_format)]
        )
        token_chain = token_chain.decode("ascii")
        token_name = token_name.decode("ascii")

        return WithdrawTransaction(
            version=tx[0],
            operation=chr(tx[1]),
            token_chain=token_chain,
            token_name=token_name,
            amount=Decimal(str(amount)),
            destination="0x" + destination.hex(),
            time=t,
            nonce=nonce,
            public=public,
            signature=tx[-64:],
            raw_tx=tx,
        )

    def hex(self):
        return self.raw_tx.hex()
