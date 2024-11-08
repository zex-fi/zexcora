import time

from loguru import logger
import pandas as pd

from .connection_manager import ConnectionManager


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
