from pydantic import BaseModel


class UserAssetResponse(BaseModel):
    asset: str
    free: str
    locked: str
    freeze: str
    withdrawing: str


class TradeResponse(BaseModel):
    name: str
    t: int
    base_token: str
    quote_token: str
    amount: float
    price: float
    nonce: int


class OrderResponse(BaseModel):
    name: str
    base_token: str
    quote_token: str
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
    EVM: str


class UserAddressesResponse(BaseModel):
    user: str
    addresses: Addresses


class TransferResponse(BaseModel):
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
    chainType: str
    decimals: int
    price: float  # price is USDT
    change_24h: float
    name: str  # standard name of the token
    symbol: str  # standard representation of a token


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
    tokenContract: str
    amount: str
    destination: str
    t: int
    nonce: int


class WithdrawNonce(BaseModel):
    chain: str
    nonce: int
