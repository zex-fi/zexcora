QUOTES = {"BTC": [1], "POL": [1, 2]}
TOKENS = {
    "BTC": [1],
    "POL": [1, 2, 3, 4],
    "BSC": [1, 2, 3, 4],
    "ARB": [1, 2, 3, 4],
    "OPT": [1, 2, 3, 4],
}
PAIRS = {
    "BTC": {
        1: {  # BTC
            "POL": {
                1: {"price_digits": 2, "volume_digits": 5, "binance_name": "BTCUSDT"},
            },
        },
    },
    "POL": {
        4: {  # Link
            "POL": {
                1: {"price_digits": 2, "volume_digits": 2, "binance_name": "LINKUSDT"},
            },
        },
    },
    "BSC": {
        4: {  # Link
            "POL": {
                1: {"price_digits": 2, "volume_digits": 2, "binance_name": "LINKUSDT"},
            },
        },
    },
    "OPT": {
        4: {  # Link
            "POL": {
                1: {"price_digits": 4, "volume_digits": 2, "binance_name": "LINKUSDT"},
            },
        },
    },
}
