from time import time as unix_time

import pandas as pd


def get_current_1m_open_time():
    now = int(unix_time())
    open_time = now - now % 60
    return open_time * 1000


class KlineManager:
    def __init__(self, pair: str):
        self.pair = pair
        self.kline = pd.DataFrame(
            columns=[
                "OpenTime",
                "CloseTime",
                "Open",
                "High",
                "Low",
                "Close",
                "Volume",
                "NumberOfTrades",
            ]
        ).set_index("OpenTime")

    def get_last_price(self):
        if len(self.kline) == 0:
            return 0
        return self.kline["Close"].iloc[-1]

    def get_price_change_24h(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span >= ms_in_24h:
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            return (
                self.kline["Close"].iloc[-1] - self.kline["Open"].iloc[prev_24h_index]
            )
        return self.kline["Close"].iloc[-1] - self.kline["Open"].iloc[0]

    def get_price_change_24h_percent(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span >= ms_in_24h:
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            open_price = self.kline["Open"].iloc[-prev_24h_index]
            close_price = self.kline["Close"].iloc[-1]
            if open_price == 0:
                return 0
            return ((close_price - open_price) / open_price) * 100

        close_price = self.kline["Close"].iloc[-1]
        open_price = self.kline["Open"].iloc[0]
        if open_price == 0:
            return 0
        return ((close_price - open_price) / open_price) * 100

    def get_price_change_7d_percent(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_7d = 7 * 24 * 60 * 60 * 1000
        if total_span > ms_in_7d:
            target_time = self.kline.index[-1] - 7 * 24 * 60 * 60 * 1000
            prev_7d_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            open_price = self.kline["Open"].iloc[prev_7d_index]
            close_price = self.kline["Close"].iloc[-1]
            return (close_price - open_price) / open_price
        return self.kline["Close"].iloc[-1] - self.kline["Open"].iloc[0]

    def get_volume_24h(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span > ms_in_24h:
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            return self.kline["Volume"].iloc[prev_24h_index:].sum()
        return self.kline["Volume"].sum()

    def get_open_time_24h(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span > ms_in_24h:
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            return self.kline.index[prev_24h_index]
        return self.kline.index[0]

    def get_close_time_24h(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span > ms_in_24h:
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            return self.kline["CloseTime"].iloc[prev_24h_index]
        return self.kline["CloseTime"].iloc[0]

    def get_open_24h(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span > ms_in_24h:
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            return self.kline["Open"].iloc[prev_24h_index]
        return self.kline["Open"].iloc[0]

    def get_high_24h(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span > ms_in_24h:
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            return self.kline["High"].iloc[prev_24h_index:].max()
        return self.kline["High"].max()

    def get_low_24h(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span > ms_in_24h:
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            return self.kline["Low"].iloc[prev_24h_index:].min()
        return self.kline["Low"].min()

    def get_trade_num_24h(self):
        if len(self.kline) == 0:
            return 0
        # Calculate the total time span of our data
        total_span = self.kline.index[-1] - self.kline.index[0]

        ms_in_24h = 24 * 60 * 60 * 1000
        if total_span > ms_in_24h:
            target_time = self.kline.index[-1] - 24 * 60 * 60 * 1000
            prev_24h_index = self.kline.index.get_indexer(
                [target_time],
                method="pad",
            )[0].item()

            return self.kline["NumberOfTrades"].iloc[prev_24h_index:].sum()
        return self.kline["NumberOfTrades"].sum()

    def update_kline(self, price: float, trade_amount: float):
        current_candle_index = get_current_1m_open_time()
        if len(self.kline.index) != 0 and current_candle_index == self.kline.index[-1]:
            self.kline.iat[-1, 2] = max(price, self.kline.iat[-1, 2])  # High
            self.kline.iat[-1, 3] = min(price, self.kline.iat[-1, 3])  # Low
            self.kline.iat[-1, 4] = price  # Close
            self.kline.iat[-1, 5] += trade_amount  # Volume
            self.kline.iat[-1, 6] += 1  # NumberOfTrades
        else:
            self.kline.loc[current_candle_index] = [
                current_candle_index + 59999,  # CloseTime
                price,  # Open
                price,  # High
                price,  # Low
                price,  # Close
                trade_amount,  # Volume
                1,  # Volume, NumberOfTrades
            ]
