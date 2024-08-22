from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ZexState(_message.Message):
    __slots__ = ["markets", "balances", "amounts", "trades", "orders", "withdrawals", "deposited_blocks", "nonces", "pair_lookup", "last_tx_index", "id_lookup"]
    class MarketsEntry(_message.Message):
        __slots__ = ["key", "value"]
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: Market
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[Market, _Mapping]] = ...) -> None: ...
    class BalancesEntry(_message.Message):
        __slots__ = ["key", "value"]
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: Balance
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[Balance, _Mapping]] = ...) -> None: ...
    class WithdrawalsEntry(_message.Message):
        __slots__ = ["key", "value"]
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: Withdrawals
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[Withdrawals, _Mapping]] = ...) -> None: ...
    class DepositedBlocksEntry(_message.Message):
        __slots__ = ["key", "value"]
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: int
        def __init__(self, key: _Optional[str] = ..., value: _Optional[int] = ...) -> None: ...
    MARKETS_FIELD_NUMBER: _ClassVar[int]
    BALANCES_FIELD_NUMBER: _ClassVar[int]
    AMOUNTS_FIELD_NUMBER: _ClassVar[int]
    TRADES_FIELD_NUMBER: _ClassVar[int]
    ORDERS_FIELD_NUMBER: _ClassVar[int]
    WITHDRAWALS_FIELD_NUMBER: _ClassVar[int]
    DEPOSITED_BLOCKS_FIELD_NUMBER: _ClassVar[int]
    NONCES_FIELD_NUMBER: _ClassVar[int]
    PAIR_LOOKUP_FIELD_NUMBER: _ClassVar[int]
    LAST_TX_INDEX_FIELD_NUMBER: _ClassVar[int]
    ID_LOOKUP_FIELD_NUMBER: _ClassVar[int]
    markets: _containers.MessageMap[str, Market]
    balances: _containers.MessageMap[str, Balance]
    amounts: _containers.RepeatedCompositeFieldContainer[AmountEntry]
    trades: _containers.RepeatedCompositeFieldContainer[TradeEntry]
    orders: _containers.RepeatedCompositeFieldContainer[OrderEntry]
    withdrawals: _containers.MessageMap[str, Withdrawals]
    deposited_blocks: _containers.ScalarMap[str, int]
    nonces: _containers.RepeatedCompositeFieldContainer[NonceEntry]
    pair_lookup: _containers.RepeatedCompositeFieldContainer[PairLookupEntry]
    last_tx_index: int
    id_lookup: _containers.RepeatedCompositeFieldContainer[IdLookupEntry]
    def __init__(self, markets: _Optional[_Mapping[str, Market]] = ..., balances: _Optional[_Mapping[str, Balance]] = ..., amounts: _Optional[_Iterable[_Union[AmountEntry, _Mapping]]] = ..., trades: _Optional[_Iterable[_Union[TradeEntry, _Mapping]]] = ..., orders: _Optional[_Iterable[_Union[OrderEntry, _Mapping]]] = ..., withdrawals: _Optional[_Mapping[str, Withdrawals]] = ..., deposited_blocks: _Optional[_Mapping[str, int]] = ..., nonces: _Optional[_Iterable[_Union[NonceEntry, _Mapping]]] = ..., pair_lookup: _Optional[_Iterable[_Union[PairLookupEntry, _Mapping]]] = ..., last_tx_index: _Optional[int] = ..., id_lookup: _Optional[_Iterable[_Union[IdLookupEntry, _Mapping]]] = ...) -> None: ...

class Market(_message.Message):
    __slots__ = ["base_token", "quote_token", "buy_orders", "sell_orders", "bids_order_book", "asks_order_book", "first_id", "final_id", "last_update_id", "kline"]
    BASE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    QUOTE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    BUY_ORDERS_FIELD_NUMBER: _ClassVar[int]
    SELL_ORDERS_FIELD_NUMBER: _ClassVar[int]
    BIDS_ORDER_BOOK_FIELD_NUMBER: _ClassVar[int]
    ASKS_ORDER_BOOK_FIELD_NUMBER: _ClassVar[int]
    FIRST_ID_FIELD_NUMBER: _ClassVar[int]
    FINAL_ID_FIELD_NUMBER: _ClassVar[int]
    LAST_UPDATE_ID_FIELD_NUMBER: _ClassVar[int]
    KLINE_FIELD_NUMBER: _ClassVar[int]
    base_token: str
    quote_token: str
    buy_orders: _containers.RepeatedCompositeFieldContainer[Order]
    sell_orders: _containers.RepeatedCompositeFieldContainer[Order]
    bids_order_book: _containers.RepeatedCompositeFieldContainer[OrderBookEntry]
    asks_order_book: _containers.RepeatedCompositeFieldContainer[OrderBookEntry]
    first_id: int
    final_id: int
    last_update_id: int
    kline: bytes
    def __init__(self, base_token: _Optional[str] = ..., quote_token: _Optional[str] = ..., buy_orders: _Optional[_Iterable[_Union[Order, _Mapping]]] = ..., sell_orders: _Optional[_Iterable[_Union[Order, _Mapping]]] = ..., bids_order_book: _Optional[_Iterable[_Union[OrderBookEntry, _Mapping]]] = ..., asks_order_book: _Optional[_Iterable[_Union[OrderBookEntry, _Mapping]]] = ..., first_id: _Optional[int] = ..., final_id: _Optional[int] = ..., last_update_id: _Optional[int] = ..., kline: _Optional[bytes] = ...) -> None: ...

class Order(_message.Message):
    __slots__ = ["price", "index", "tx"]
    PRICE_FIELD_NUMBER: _ClassVar[int]
    INDEX_FIELD_NUMBER: _ClassVar[int]
    TX_FIELD_NUMBER: _ClassVar[int]
    price: float
    index: int
    tx: bytes
    def __init__(self, price: _Optional[float] = ..., index: _Optional[int] = ..., tx: _Optional[bytes] = ...) -> None: ...

class OrderBookEntry(_message.Message):
    __slots__ = ["price", "amount"]
    PRICE_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_FIELD_NUMBER: _ClassVar[int]
    price: float
    amount: float
    def __init__(self, price: _Optional[float] = ..., amount: _Optional[float] = ...) -> None: ...

class Balance(_message.Message):
    __slots__ = ["balances"]
    BALANCES_FIELD_NUMBER: _ClassVar[int]
    balances: _containers.RepeatedCompositeFieldContainer[BalanceEntry]
    def __init__(self, balances: _Optional[_Iterable[_Union[BalanceEntry, _Mapping]]] = ...) -> None: ...

class BalanceEntry(_message.Message):
    __slots__ = ["public_key", "amount"]
    PUBLIC_KEY_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_FIELD_NUMBER: _ClassVar[int]
    public_key: bytes
    amount: float
    def __init__(self, public_key: _Optional[bytes] = ..., amount: _Optional[float] = ...) -> None: ...

class AmountEntry(_message.Message):
    __slots__ = ["tx", "amount"]
    TX_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_FIELD_NUMBER: _ClassVar[int]
    tx: bytes
    amount: float
    def __init__(self, tx: _Optional[bytes] = ..., amount: _Optional[float] = ...) -> None: ...

class TradeEntry(_message.Message):
    __slots__ = ["public_key", "trades"]
    PUBLIC_KEY_FIELD_NUMBER: _ClassVar[int]
    TRADES_FIELD_NUMBER: _ClassVar[int]
    public_key: bytes
    trades: _containers.RepeatedCompositeFieldContainer[Trade]
    def __init__(self, public_key: _Optional[bytes] = ..., trades: _Optional[_Iterable[_Union[Trade, _Mapping]]] = ...) -> None: ...

class Trade(_message.Message):
    __slots__ = ["t", "amount", "pair", "order_type", "order"]
    T_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_FIELD_NUMBER: _ClassVar[int]
    PAIR_FIELD_NUMBER: _ClassVar[int]
    ORDER_TYPE_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    t: int
    amount: float
    pair: str
    order_type: int
    order: bytes
    def __init__(self, t: _Optional[int] = ..., amount: _Optional[float] = ..., pair: _Optional[str] = ..., order_type: _Optional[int] = ..., order: _Optional[bytes] = ...) -> None: ...

class OrderEntry(_message.Message):
    __slots__ = ["public_key", "orders"]
    PUBLIC_KEY_FIELD_NUMBER: _ClassVar[int]
    ORDERS_FIELD_NUMBER: _ClassVar[int]
    public_key: bytes
    orders: _containers.RepeatedScalarFieldContainer[bytes]
    def __init__(self, public_key: _Optional[bytes] = ..., orders: _Optional[_Iterable[bytes]] = ...) -> None: ...

class Withdrawals(_message.Message):
    __slots__ = ["withdrawals"]
    WITHDRAWALS_FIELD_NUMBER: _ClassVar[int]
    withdrawals: _containers.RepeatedCompositeFieldContainer[WithdrawalEntry]
    def __init__(self, withdrawals: _Optional[_Iterable[_Union[WithdrawalEntry, _Mapping]]] = ...) -> None: ...

class WithdrawalEntry(_message.Message):
    __slots__ = ["public_key", "transactions"]
    PUBLIC_KEY_FIELD_NUMBER: _ClassVar[int]
    TRANSACTIONS_FIELD_NUMBER: _ClassVar[int]
    public_key: bytes
    transactions: _containers.RepeatedCompositeFieldContainer[WithdrawTransaction]
    def __init__(self, public_key: _Optional[bytes] = ..., transactions: _Optional[_Iterable[_Union[WithdrawTransaction, _Mapping]]] = ...) -> None: ...

class WithdrawTransaction(_message.Message):
    __slots__ = ["token", "amount", "nonce", "public", "chain"]
    TOKEN_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_FIELD_NUMBER: _ClassVar[int]
    NONCE_FIELD_NUMBER: _ClassVar[int]
    PUBLIC_FIELD_NUMBER: _ClassVar[int]
    CHAIN_FIELD_NUMBER: _ClassVar[int]
    token: str
    amount: float
    nonce: int
    public: bytes
    chain: str
    def __init__(self, token: _Optional[str] = ..., amount: _Optional[float] = ..., nonce: _Optional[int] = ..., public: _Optional[bytes] = ..., chain: _Optional[str] = ...) -> None: ...

class NonceEntry(_message.Message):
    __slots__ = ["public_key", "nonce"]
    PUBLIC_KEY_FIELD_NUMBER: _ClassVar[int]
    NONCE_FIELD_NUMBER: _ClassVar[int]
    public_key: bytes
    nonce: int
    def __init__(self, public_key: _Optional[bytes] = ..., nonce: _Optional[int] = ...) -> None: ...

class PairLookupEntry(_message.Message):
    __slots__ = ["key", "base_token", "quote_token", "pair"]
    KEY_FIELD_NUMBER: _ClassVar[int]
    BASE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    QUOTE_TOKEN_FIELD_NUMBER: _ClassVar[int]
    PAIR_FIELD_NUMBER: _ClassVar[int]
    key: bytes
    base_token: str
    quote_token: str
    pair: str
    def __init__(self, key: _Optional[bytes] = ..., base_token: _Optional[str] = ..., quote_token: _Optional[str] = ..., pair: _Optional[str] = ...) -> None: ...

class IdLookupEntry(_message.Message):
    __slots__ = ["public_key", "user_id"]
    PUBLIC_KEY_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    public_key: bytes
    user_id: int
    def __init__(self, public_key: _Optional[bytes] = ..., user_id: _Optional[int] = ...) -> None: ...
