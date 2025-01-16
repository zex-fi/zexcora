from enum import Enum

from eth_typing.evm import HexAddress

type UserPublic = bytes
type Chain = str
type ContractAddress = HexAddress
type Token = str


class ExecutionType(Enum):
    NEW = "NEW"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    TRADE = "TRADE"
    EXPIRED = "EXPIRED"
