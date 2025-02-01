from collections import defaultdict
from threading import Lock
import asyncio

import pandas as pd

from app.callbacks import depth_event, kline_event
from app.connection_manager import ConnectionManager

manager = ConnectionManager()


class SnapshotManager:
    def __init__(self):
        self.depth_pair_locks: dict[str, Lock] = defaultdict(Lock)
        self.kline_pair_locks: dict[str, Lock]
        self.klines: dict[str, pd.DataFrame] = defaultdict(
            lambda: pd.DataFrame(
                columns=[
                    "OpenTime",
                    "CloseTime",
                    "Open",
                    "High",
                    "Low",
                    "Close",
                    "Volume",
                    "NumberOfTrades",
                ],
            ).set_index("OpenTime")
        )
        self.order_book_diffs: dict[str, dict] = {}

        self.kline_callback = kline_event(manager)
        self.depth_callback = depth_event(manager)

    def get_kline(self, pair):
        return self.klines[pair].copy()

    def get_order_book_diff(self, pair):
        return self.order_book_diffs[pair].copy()

    def update_kline_callback(self, pair, kline: pd.DataFrame):
        self.klines[pair] = kline
        asyncio.create_task(self.kline_callback(pair, kline))

    def update_order_book_diff_callback(self, pair, diff: dict):
        self.order_book_diffs[pair] = diff
        asyncio.create_task(self.depth_callback(pair, diff))
