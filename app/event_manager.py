from collections import defaultdict
from threading import Lock
import asyncio

import pandas as pd

from .callbacks import depth_event, kline_event


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

    def get_kline(self, pair):
        return self.klines[pair].copy()

    def get_order_book_diff(self, pair):
        return self.order_book_diffs[pair].copy()

    def update_kline_callback(self, pair, kline: pd.DataFrame):
        self.klines[pair] = kline
        msg = kline_event(pair, kline)

    def update_order_book_diff_callback(self, pair, diff: dict):
        self.order_book_diffs[pair] = diff
        msg = depth_event(pair, diff)
