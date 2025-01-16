from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ZexState(_message.Message):
    __slots__ = ("markets", "balances", "amounts", "trades", "orders", "withdraws_on_chain", "user_withdraws_on_chain", "user_withdraw_nonce_on_chain", "withdraw_nonce_on_chain", "deposits", "nonces", "last_tx_index", "user_deposits", "public_to_id_lookup", "id_to_public_lookup", "contract_decimal_on_chain")
    class MarketsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: Market
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[Market, _Mapping]] = ...) -> None: ...
    class BalancesEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: Balance
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[Balance, _Mapping]] = ...) -> None: ...
    class WithdrawsOnChainEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: WithdrawsOnChain
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[WithdrawsOnChain, _Mapping]] = ...) -> None: ...
    class UserWithdrawsOnChainEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: UserWithdraws
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[UserWithdraws, _Mapping]] = ...) -> None: ...
    class UserWithdrawNonceOnChainEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: WithdrawNonceOnChain
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[WithdrawNonceOnChain, _Mapping]] = ...) -> None: ...
    class WithdrawNonceOnChainEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: int
        def __init__(self, key: _Optional[str] = ..., value: _Optional[int] = ...) -> None: ...
    class DepositsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: DepositsOnChain
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[DepositsOnChain, _Mapping]] = ...) -> None: ...
    class IdToPublicLookupEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: int
        value: bytes
        def __init__(self, key: _Optional[int] = ..., value: _Optional[bytes] = ...) -> None: ...
    class ContractDecimalOnChainEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: ContractDecimalOnChain
        def __init__(self, key: _Optional[str] = ..., value: _Optional[_Union[ContractDecimalOnChain, _Mapping]] = ...) -> None: ...
    MARKETS_FIELD_NUMBER: _ClassVar[int]
    BALANCES_FIELD_NUMBER: _ClassVar[int]
    AMOUNTS_FIELD_NUMBER: _ClassVar[int]
    TRADES_FIELD_NUMBER: _ClassVar[int]
    ORDERS_FIELD_NUMBER: _ClassVar[int]
    WITHDRAWS_ON_CHAIN_FIELD_NUMBER: _ClassVar[int]
    USER_WITHDRAWS_ON_CHAIN_FIELD_NUMBER: _ClassVar[int]
    USER_WITHDRAW_NONCE_ON_CHAIN_FIELD_NUMBER: _ClassVar[int]
    WITHDRAW_NONCE_ON_CHAIN_FIELD_NUMBER: _ClassVar[int]
    DEPOSITS_FIELD_NUMBER: _ClassVar[int]
    NONCES_FIELD_NUMBER: _ClassVar[int]
    LAST_TX_INDEX_FIELD_NUMBER: _ClassVar[int]
    USER_DEPOSITS_FIELD_NUMBER: _ClassVar[int]
    PUBLIC_TO_ID_LOOKUP_FIELD_NUMBER: _ClassVar[int]
    ID_TO_PUBLIC_LOOKUP_FIELD_NUMBER: _ClassVar[int]
    CONTRACT_DECIMAL_ON_CHAIN_FIELD_NUMBER: _ClassVar[int]
    markets: _containers.MessageMap[str, Market]
    balances: _containers.MessageMap[str, Balance]
    amounts: _containers.RepeatedCompositeFieldContainer[AmountEntry]
    trades: _containers.RepeatedCompositeFieldContainer[TradeEntry]
    orders: _containers.RepeatedCompositeFieldContainer[OrderEntry]
    withdraws_on_chain: _containers.MessageMap[str, WithdrawsOnChain]
    user_withdraws_on_chain: _containers.MessageMap[str, UserWithdraws]
    user_withdraw_nonce_on_chain: _containers.MessageMap[str, WithdrawNonceOnChain]
    withdraw_nonce_on_chain: _containers.ScalarMap[str, int]
    deposits: _containers.MessageMap[str, DepositsOnChain]
    nonces: _containers.RepeatedCompositeFieldContainer[NonceEntry]
    last_tx_index: int
    user_deposits: _containers.RepeatedCompositeFieldContainer[UserDepositEntry]
    public_to_id_lookup: _containers.RepeatedCompositeFieldContainer[IDLookupEntry]
    id_to_public_lookup: _containers.ScalarMap[int, bytes]
    contract_decimal_on_chain: _containers.MessageMap[str, ContractDecimalOnChain]
    def __init__(self, markets: _Optional[_Mapping[str, Market]] = ..., balances: _Optional[_Mapping[str, Balance]] = ..., amounts: _Optional[_Iterable[_Union[AmountEntry, _Mapping]]] = ..., trades: _Optional[_Iterable[_Union[TradeEntry, _Mapping]]] = ..., orders: _Optional[_Iterable[_Union[OrderEntry, _Mapping]]] = ..., withdraws_on_chain: _Optional[_Mapping[str, WithdrawsOnChain]] = ..., user_withdraws_on_chain: _Optional[_Mapping[str, UserWithdraws]] = ..., user_withdraw_nonce_on_chain: _Optional[_Mapping[str, WithdrawNonceOnChain]] = ..., withdraw_nonce_on_chain: _Optional[_Mapping[str, int]] = ..., deposits: _Optional[_Mapping[str, DepositsOnChain]] = ..., nonces: _Optional[_Iterable[_Union[NonceEntry, _Mapping]]] = ..., last_tx_index: _Optional[int] = ..., user_deposits: _Optional[_Iterable[_Union[UserDepositEntry, _Mapping]]] = ..., public_to_id_lookup: _Optional[_Iterable[_Union[IDLookupEntry, _Mapping]]] = ..., id_to_public_lookup: _Optional[_Mapping[int, bytes]] = ..., contract_decimal_on_chain: _Optional[_Mapping[str, ContractDecimalOnChain]] = ...) -> None: ...

class Market(_message.Message):
    __slots__ = ("base_token", "quote_token", "buy_orders", "sell_orders", "bids_order_book", "asks_order_book", "first_id", "final_id", "last_update_id", "kline")
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
    __slots__ = ("price", "tx")
    PRICE_FIELD_NUMBER: _ClassVar[int]
    TX_FIELD_NUMBER: _ClassVar[int]
    price: str
    tx: bytes
    def __init__(self, price: _Optional[str] = ..., tx: _Optional[bytes] = ...) -> None: ...

class OrderBookEntry(_message.Message):
    __slots__ = ("price", "amount")
    PRICE_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_FIELD_NUMBER: _ClassVar[int]
    price: str
    amount: str
    def __init__(self, price: _Optional[str] = ..., amount: _Optional[str] = ...) -> None: ...

class Balance(_message.Message):
    __slots__ = ("balances",)
    BALANCES_FIELD_NUMBER: _ClassVar[int]
    balances: _containers.RepeatedCompositeFieldContainer[BalanceEntry]
    def __init__(self, balances: _Optional[_Iterable[_Union[BalanceEntry, _Mapping]]] = ...) -> None: ...

class BalanceEntry(_message.Message):
    __slots__ = ("public_key", "amount")
    PUBLIC_KEY_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_FIELD_NUMBER: _ClassVar[int]
    public_key: bytes
    amount: str
    def __init__(self, public_key: _Optional[bytes] = ..., amount: _Optional[str] = ...) -> None: ...

class AmountEntry(_message.Message):
    __slots__ = ("tx", "amount")
    TX_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_FIELD_NUMBER: _ClassVar[int]
    tx: bytes
    amount: str
    def __init__(self, tx: _Optional[bytes] = ..., amount: _Optional[str] = ...) -> None: ...

class TradeEntry(_message.Message):
    __slots__ = ("public_key", "trades")
    PUBLIC_KEY_FIELD_NUMBER: _ClassVar[int]
    TRADES_FIELD_NUMBER: _ClassVar[int]
    public_key: bytes
    trades: _containers.RepeatedCompositeFieldContainer[Trade]
    def __init__(self, public_key: _Optional[bytes] = ..., trades: _Optional[_Iterable[_Union[Trade, _Mapping]]] = ...) -> None: ...

class Trade(_message.Message):
    __slots__ = ("t", "amount", "pair", "order_type", "order")
    T_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_FIELD_NUMBER: _ClassVar[int]
    PAIR_FIELD_NUMBER: _ClassVar[int]
    ORDER_TYPE_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    t: int
    amount: str
    pair: str
    order_type: int
    order: bytes
    def __init__(self, t: _Optional[int] = ..., amount: _Optional[str] = ..., pair: _Optional[str] = ..., order_type: _Optional[int] = ..., order: _Optional[bytes] = ...) -> None: ...

class OrderEntry(_message.Message):
    __slots__ = ("public_key", "orders")
    PUBLIC_KEY_FIELD_NUMBER: _ClassVar[int]
    ORDERS_FIELD_NUMBER: _ClassVar[int]
    public_key: bytes
    orders: _containers.RepeatedScalarFieldContainer[bytes]
    def __init__(self, public_key: _Optional[bytes] = ..., orders: _Optional[_Iterable[bytes]] = ...) -> None: ...

class UserWithdrawEntry(_message.Message):
    __slots__ = ("public_key", "raw_txs")
    PUBLIC_KEY_FIELD_NUMBER: _ClassVar[int]
    RAW_TXS_FIELD_NUMBER: _ClassVar[int]
    public_key: bytes
    raw_txs: _containers.RepeatedScalarFieldContainer[bytes]
    def __init__(self, public_key: _Optional[bytes] = ..., raw_txs: _Optional[_Iterable[bytes]] = ...) -> None: ...

class UserWithdraws(_message.Message):
    __slots__ = ("withdraws",)
    WITHDRAWS_FIELD_NUMBER: _ClassVar[int]
    withdraws: _containers.RepeatedCompositeFieldContainer[UserWithdrawEntry]
    def __init__(self, withdraws: _Optional[_Iterable[_Union[UserWithdrawEntry, _Mapping]]] = ...) -> None: ...

class WithdrawsOnChain(_message.Message):
    __slots__ = ("raw_txs",)
    RAW_TXS_FIELD_NUMBER: _ClassVar[int]
    raw_txs: _containers.RepeatedScalarFieldContainer[bytes]
    def __init__(self, raw_txs: _Optional[_Iterable[bytes]] = ...) -> None: ...

class WithdrawNonceEntry(_message.Message):
    __slots__ = ("public_key", "nonce")
    PUBLIC_KEY_FIELD_NUMBER: _ClassVar[int]
    NONCE_FIELD_NUMBER: _ClassVar[int]
    public_key: bytes
    nonce: int
    def __init__(self, public_key: _Optional[bytes] = ..., nonce: _Optional[int] = ...) -> None: ...

class WithdrawNonceOnChain(_message.Message):
    __slots__ = ("nonces",)
    NONCES_FIELD_NUMBER: _ClassVar[int]
    nonces: _containers.RepeatedCompositeFieldContainer[WithdrawNonceEntry]
    def __init__(self, nonces: _Optional[_Iterable[_Union[WithdrawNonceEntry, _Mapping]]] = ...) -> None: ...

class DepositEntry(_message.Message):
    __slots__ = ("tx_hash", "vout")
    TX_HASH_FIELD_NUMBER: _ClassVar[int]
    VOUT_FIELD_NUMBER: _ClassVar[int]
    tx_hash: str
    vout: int
    def __init__(self, tx_hash: _Optional[str] = ..., vout: _Optional[int] = ...) -> None: ...

class DepositsOnChain(_message.Message):
    __slots__ = ("deposits",)
    DEPOSITS_FIELD_NUMBER: _ClassVar[int]
    deposits: _containers.RepeatedCompositeFieldContainer[DepositEntry]
    def __init__(self, deposits: _Optional[_Iterable[_Union[DepositEntry, _Mapping]]] = ...) -> None: ...

class UserDepositEntry(_message.Message):
    __slots__ = ("public_key", "deposits")
    PUBLIC_KEY_FIELD_NUMBER: _ClassVar[int]
    DEPOSITS_FIELD_NUMBER: _ClassVar[int]
    public_key: bytes
    deposits: _containers.RepeatedCompositeFieldContainer[Deposit]
    def __init__(self, public_key: _Optional[bytes] = ..., deposits: _Optional[_Iterable[_Union[Deposit, _Mapping]]] = ...) -> None: ...

class Deposit(_message.Message):
    __slots__ = ("tx_hash", "chain", "token_contract", "amount", "decimal", "time", "user_id", "vout")
    TX_HASH_FIELD_NUMBER: _ClassVar[int]
    CHAIN_FIELD_NUMBER: _ClassVar[int]
    TOKEN_CONTRACT_FIELD_NUMBER: _ClassVar[int]
    AMOUNT_FIELD_NUMBER: _ClassVar[int]
    DECIMAL_FIELD_NUMBER: _ClassVar[int]
    TIME_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    VOUT_FIELD_NUMBER: _ClassVar[int]
    tx_hash: str
    chain: str
    token_contract: str
    amount: str
    decimal: int
    time: int
    user_id: int
    vout: int
    def __init__(self, tx_hash: _Optional[str] = ..., chain: _Optional[str] = ..., token_contract: _Optional[str] = ..., amount: _Optional[str] = ..., decimal: _Optional[int] = ..., time: _Optional[int] = ..., user_id: _Optional[int] = ..., vout: _Optional[int] = ...) -> None: ...

class NonceEntry(_message.Message):
    __slots__ = ("public_key", "nonce")
    PUBLIC_KEY_FIELD_NUMBER: _ClassVar[int]
    NONCE_FIELD_NUMBER: _ClassVar[int]
    public_key: bytes
    nonce: int
    def __init__(self, public_key: _Optional[bytes] = ..., nonce: _Optional[int] = ...) -> None: ...

class IDLookupEntry(_message.Message):
    __slots__ = ("public_key", "user_id")
    PUBLIC_KEY_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    public_key: bytes
    user_id: int
    def __init__(self, public_key: _Optional[bytes] = ..., user_id: _Optional[int] = ...) -> None: ...

class ContractToIDOnChainEntry(_message.Message):
    __slots__ = ("chain", "contract_to_id")
    class ContractToIdEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: int
        def __init__(self, key: _Optional[str] = ..., value: _Optional[int] = ...) -> None: ...
    CHAIN_FIELD_NUMBER: _ClassVar[int]
    CONTRACT_TO_ID_FIELD_NUMBER: _ClassVar[int]
    chain: str
    contract_to_id: _containers.ScalarMap[str, int]
    def __init__(self, chain: _Optional[str] = ..., contract_to_id: _Optional[_Mapping[str, int]] = ...) -> None: ...

class IDToContractOnChainEntry(_message.Message):
    __slots__ = ("chain", "id_to_contract")
    class IdToContractEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: int
        value: str
        def __init__(self, key: _Optional[int] = ..., value: _Optional[str] = ...) -> None: ...
    CHAIN_FIELD_NUMBER: _ClassVar[int]
    ID_TO_CONTRACT_FIELD_NUMBER: _ClassVar[int]
    chain: str
    id_to_contract: _containers.ScalarMap[int, str]
    def __init__(self, chain: _Optional[str] = ..., id_to_contract: _Optional[_Mapping[int, str]] = ...) -> None: ...

class ContractDecimalOnChain(_message.Message):
    __slots__ = ("contract_decimal",)
    class ContractDecimalEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: int
        def __init__(self, key: _Optional[str] = ..., value: _Optional[int] = ...) -> None: ...
    CONTRACT_DECIMAL_FIELD_NUMBER: _ClassVar[int]
    contract_decimal: _containers.ScalarMap[str, int]
    def __init__(self, contract_decimal: _Optional[_Mapping[str, int]] = ...) -> None: ...
