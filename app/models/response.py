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
    chain: str
    token: str
    txHash: str
    amount: float
    time: int


class Filter(BaseModel):
    filterType: str
    minPrice: str
    maxPrice: str
    tickSize: str
    stepSize: str
    limit: int
    minTrailingAboveDelta: int
    maxTrailingAboveDelta: int
    minTrailingBelowDelta: int
    maxTrailingBelowDelta: int
    bidMultiplierUp: str
    bidMultiplierDown: str
    askMultiplierUp: str
    askMultiplierDown: str
    avgPriceMins: int
    minNotional: str
    applyMinToMarket: bool
    maxNotional: str
    applyMaxToMarket: bool
    maxNumOrders: int


class Symbol(BaseModel):
    symbol: str
    status: str
    baseAsset: str
    baseAssetPrecision: int
    quoteAsset: str
    quotePrecision: int
    quoteAssetPrecision: int
    orderTypes: list[str]
    filters: list[Filter]


class Token(BaseModel):
    chainType: str
    price: float  # price is USDT
    change_24h: float
    name: str  # standard name of the token
    symbol: str  # standard representation of a token


class Chain(BaseModel):
    chain: str
    chainType: str


class ExchangeInfoResponse(BaseModel):
    timezone: str
    serverTime: int
    symbols: list[Symbol]
    tokens: list[Token]
    chains: list[Chain]


class StatisticsMiniResponse(BaseModel):
    symbol: str
    openPrice: str
    highPrice: str
    lowPrice: str
    lastPrice: str
    volume: str
    quoteVolume: str
    openTime: int
    closeTime: int
    firstId: int
    lastId: int
    count: int


class StatisticsFullResponse(StatisticsMiniResponse):
    priceChange: str
    priceChangePercent: str
    weightedAvgPrice: str


class PriceResponse(BaseModel):
    symbol: str
    price: str


class BookTickerResponse(BaseModel):
    symbol: str
    bidPrice: str
    bidQty: str
    askPrice: str
    askQty: str


class TickerResponse(BaseModel):
    symbol: str
    priceChange: str
    priceChangePercent: str
    weightedAvgPrice: str
    openPrice: str
    highPrice: str
    lowPrice: str
    lastPrice: str
    volume: str
    quoteVolume: str
    openTime: int
    closeTime: int
    firstId: int
    lastId: int
    count: int


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
