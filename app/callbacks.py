from decimal import Decimal
from enum import Enum
import time

from loguru import logger
import pandas as pd

from .connection_manager import ConnectionManager
from .zex_types import ExecutionType


def kline_event(manager: ConnectionManager):
    async def f(kline_symbol: str, kline: pd.DataFrame):
        if len(kline) == 0:
            return
        subs = manager.subscriptions.copy()
        for channel, clients in subs.items():
            parts = channel.split("@")
            symbol, details = parts[0], parts[1]
            if "kline" not in details or symbol != kline_symbol:
                continue

            now = int(time.time() * 1000)
            last_candle = kline.iloc[len(kline) - 1]
            message = {
                "stream": channel,
                "data": {
                    "e": "kline",  # Event type
                    "E": int(time.time() * 1000),  # Event time
                    "s": symbol,  # Symbol
                    "k": {
                        "t": int(last_candle.name),  # Kline start time
                        "T": last_candle["CloseTime"],  # Kline close time
                        "s": symbol,  # Symbol
                        "i": "1m",  # Interval
                        "f": 100,  # First trade ID
                        "L": 200,  # Last trade ID
                        "o": f"{last_candle['Open']}",  # Open price
                        "c": f"{last_candle['Close']}",  # Close price
                        "h": f"{last_candle['High']}",  # High price
                        "l": f"{last_candle['Low']}",  # Low price
                        "v": f"{last_candle['Volume']}",  # Base asset volume
                        "n": last_candle["NumberOfTrades"],  # Number of trades
                        "x": bool(
                            now >= last_candle["CloseTime"]
                        ),  # Is this kline closed?
                        "q": "1.0000",  # Quote asset volume
                        "V": "500",  # Taker buy base asset volume
                        "Q": "0.500",  # Taker buy quote asset volume
                        "B": "123456",  # Ignore
                    },
                },
            }

            # Copy to avoid modification during iteration
            for ws in clients.copy():
                if ws not in manager.active_connections:
                    manager.remove(ws)
                    continue
                try:
                    await ws.send_json(message)
                except Exception as e:
                    manager.remove(ws)
                    logger.exception(e)

    return f


def depth_event(manager: ConnectionManager):
    async def f(depth_symbol: str, depth: dict):
        subs = manager.subscriptions.copy()
        for channel, clients in subs.items():
            parts = channel.split("@")
            symbol, details = parts[0], parts[1]
            if "depth" not in details or symbol != depth_symbol:
                continue

            # Copy to avoid modification during iteration
            for ws in clients.copy():
                if ws not in manager.active_connections:
                    manager.remove(ws)
                    continue
                try:
                    await ws.send_json({"stream": channel, "data": depth})
                except Exception as e:
                    manager.remove(ws)
                    logger.exception(e)

    return f


def user_order_event(manager: ConnectionManager):
    async def f(
        public: str,
        nonce: int,
        symbol: str,
        side: str,
        amount: Decimal,
        price: Decimal,
        execution_type: ExecutionType,
        order_status: str,
        last_filled: Decimal,
        cumulative_filled: Decimal,
        last_executed_price: Decimal,
        transaction_time: int,
        is_on_orderbook: bool,
        is_maker: bool,
        cumulative_quote_asset_quantity: Decimal,
        last_quote_asset_quantity: Decimal,
        quote_order_quantity: Decimal,
        reject_reason: str = "NONE",
    ):
        subs = manager.subscriptions.copy()
        for channel, clients in subs.items():
            parts = channel.split("@")
            user_public, details = parts[0], parts[1]
            if "executionReport" not in details or user_public != public:
                continue

            for ws in clients.copy():
                if ws not in manager.active_connections:
                    manager.remove(ws)
                    continue
                try:
                    data = {
                        "e": "executionReport",  # Event type
                        "E": int(time.time() * 1000),  # Event time
                        "s": symbol,  # Symbol
                        "c": nonce,  # Client order ID
                        "S": side,  # Side
                        "o": "",  # Order type
                        "f": "GTC",  # Time in force
                        "q": str(amount),  # Order quantity
                        "p": str(price),  # Order price
                        "P": "0.",  # Stop price
                        "F": "0.",  # Iceberg quantity
                        "g": -1,  # OrderListId
                        "C": "",  # Original client order ID; This is the ID of the order being canceled
                        "x": execution_type.value,  # Current execution type
                        "X": order_status,  # Current order status
                        "r": reject_reason,  # Order reject reason; will be an error code.
                        "i": nonce,  # Order ID
                        "l": str(last_filled),  # Last executed quantity
                        "z": str(cumulative_filled),  # Cumulative filled quantity
                        "L": str(last_executed_price),  # Last executed price
                        "n": "0",  # Commission amount
                        "N": None,  # Commission asset
                        "T": transaction_time,  # Transaction time
                        "t": -1,  # Trade ID
                        "I": 8641984,  # Ignore
                        "w": is_on_orderbook,  # Is the order on the book?
                        "m": is_maker,  # Is this trade the maker side?
                        "M": False,  # Ignore
                        "O": 0,  # Order creation time
                        "Z": str(
                            cumulative_quote_asset_quantity
                        ),  # Cumulative quote asset transacted quantity
                        "Y": str(
                            last_quote_asset_quantity
                        ),  # Last quote asset transacted quantity (i.e. lastPrice * lastQty)
                        "Q": str(quote_order_quantity),  # Quote Order Quantity
                        "W": 0,  # Working Time; This is only visible if the order has been placed on the book.
                        "V": "NONE",  # SelfTradePreventionMode
                    }
                    await ws.send_json({"stream": channel, "data": data})
                except Exception as e:
                    manager.remove(ws)
                    logger.exception(e)

    return f


def user_deposit_event(manager: ConnectionManager):
    async def f(public: str, chain: str, name: str, amount: Decimal):
        subs = manager.subscriptions.copy()
        for channel, clients in subs.items():
            parts = channel.split("@")
            user_public, details = parts[0], parts[1]
            if "deposit" not in details or (
                user_public != public and user_public != "all"
            ):
                continue

            for ws in clients.copy():
                if ws not in manager.active_connections:
                    manager.remove(ws)
                    continue
                try:
                    data = {
                        "e": "deposit",  # Event type
                        "E": int(time.time() * 1000),  # Event time
                        "chain": chain,
                        "name": name,
                        "amount": str(amount),
                    }
                    await ws.send_json({"stream": channel, "data": data})
                except Exception as e:
                    manager.remove(ws)
                    logger.exception(e)

    return f


def user_withdraw_event(manager: ConnectionManager):
    async def f(public: str, chain: str, name: str, amount: Decimal):
        subs = manager.subscriptions.copy()
        for channel, clients in subs.items():
            parts = channel.split("@")
            user_public, details = parts[0], parts[1]
            if "withdraw" not in details or (
                user_public != public and user_public != "all"
            ):
                continue

            for ws in clients.copy():
                if ws not in manager.active_connections:
                    manager.remove(ws)
                    continue
                try:
                    data = {
                        "e": "withdraw",  # Event type
                        "E": int(time.time() * 1000),  # Event time
                        "chain": chain,
                        "name": name,
                        "amount": str(amount),
                    }
                    await ws.send_json({"stream": channel, "data": data})
                except Exception as e:
                    manager.remove(ws)
                    logger.exception(e)

    return f
