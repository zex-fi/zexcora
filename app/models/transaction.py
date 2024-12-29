from decimal import Decimal
from struct import calcsize, unpack

from eth_typing import ChecksumAddress
from eth_utils.address import to_checksum_address
from pydantic import BaseModel

from app.config import settings


def chunkify(lst, n_chunks):
    for i in range(0, len(lst), n_chunks):
        yield lst[i : i + n_chunks]


def get_token_name(chain, address):
    for verified_name, tokens in settings.zex.verified_tokens.items():
        if chain not in tokens:
            continue
        if tokens[chain].contract_address == address:
            return verified_name
    return f"{chain}:{address}"


class Deposit(BaseModel):
    tx_hash: str
    chain: str
    token_contract: ChecksumAddress
    amount: Decimal
    decimal: int
    time: int
    user_id: int
    vout: int

    @property
    def token_name(self):
        return get_token_name(self.chain, self.token_contract)


class DepositTransaction(BaseModel):
    version: int
    operation: str
    chain: str
    deposits: list[Deposit]

    @classmethod
    def from_tx(cls, tx: bytes) -> "DepositTransaction":
        header_format = ">B B 3s H"
        header_size = calcsize(header_format)
        version, operation, chain, count = unpack(header_format, tx[:header_size])
        chain = chain.upper().decode()

        deposit_format = ">66s 42s 32s B I Q B"
        deposit_size = calcsize(deposit_format)
        raw_deposits = list(
            chunkify(tx[header_size : header_size + deposit_size * count], deposit_size)
        )

        deposits = []

        for chunk in raw_deposits:
            tx_hash, token_contract, amount, decimal, t, user_id, vout = unpack(
                deposit_format, chunk[:deposit_size]
            )
            amount = int.from_bytes(amount, byteorder="big")
            tx_hash = tx_hash.decode()

            amount = Decimal(str(amount))
            amount /= 10 ** Decimal(decimal)

            deposits.append(
                Deposit(
                    tx_hash=tx_hash,
                    chain=chain,
                    token_contract=to_checksum_address(token_contract.decode()),
                    amount=amount,
                    decimal=decimal,
                    time=t,
                    user_id=user_id,
                    vout=vout,
                )
            )

        return DepositTransaction(
            version=version,
            operation=operation,
            chain=chain,
            deposits=deposits,
        )


class WithdrawTransaction(BaseModel):
    version: int
    operation: str
    token_chain: str
    # name if token is verified else checksum contract address
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
        version, operation, token_len = unpack(">B B B", tx[:3])

        withdraw_format = f">3s {token_len}s d 20s I I 33s"
        token_chain, token_name, amount, destination, t, nonce, public = unpack(
            withdraw_format, tx[3 : 3 + calcsize(withdraw_format)]
        )
        token_chain = token_chain.decode("ascii")
        token_name = token_name.decode("ascii")

        return WithdrawTransaction(
            version=version,
            operation=chr(operation),
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
