from pydantic import BaseModel


class BalanceResponse(BaseModel):
    chain: str
    token: int
    balance: str


class TradeResponse(BaseModel):
    name: str
    t: int
    base_chain: str
    base_token: int
    quote_chain: str
    quote_token: int
    amount: float
    price: float
    nonce: int


class OrderResponse(BaseModel):
    name: str
    base_chain: str
    base_token: int
    quote_chain: str
    quote_token: int
    amount: float
    price: float
    t: int
    nonce: int
    slice: str


class NonceResponse(BaseModel):
    nonce: int


class UserIDResponse(BaseModel):
    id: int


class UserPublicResponse(BaseModel):
    public: str


class Addresses(BaseModel):
    BTC: str
    XMR: str
    BST: str
    HOL: str
    SEP: str


class UserAddressesResponse(BaseModel):
    user: str
    addresses: Addresses


class DepositResponse(BaseModel):
    token: str
    amount: float
    time: int


class Symbol(BaseModel):
    symbol: str
    lastPrice: float
    volume24h: float
    priceChange24h: float
    high24h: float
    low24h: float
    priceChange7D: float


class Token(BaseModel):
    chain: str
    id: int
    chainType: str
    address: str | None
    decimals: int
    price: float  # price is USDT
    change_24h: float
    name: str  # standard name of the token
    symbol: str  # standard representation of a token
    tag: str


class Chain(BaseModel):
    chain: str
    chainType: str


class ExchangeInfoResponse(BaseModel):
    timezone: str
    symbols: list[Symbol]
    tokens: list[Token]
    chains: list[Chain]


class Withdraw(BaseModel):
    chain: str
    tokenID: int
    amount: float
    destination: str
    t: int
    nonce: int


class WithdrawNonce(BaseModel):
    chain: str
    nonce: int


class Signature(BaseModel):
    s: int
    e: int


class WithdrawSignature(BaseModel):
    withdraw: Withdraw
    signature: Signature
    publicNonce: str
