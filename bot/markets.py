QUOTES = {"BTC": [0], "POL": [1, 2]}
TOKENS = {
    "BTC": [0],
    "XMR": [0],
    "POL": [1, 2, 3, 4],
    "BSC": [1, 2, 3, 4],
    "ARB": [1, 2, 3, 4],
}
PAIRS = {
    "POL": {
        2: {  # USDC
            "POL": {
                1: {
                    "bid": 0.9999,
                    "ask": 1.0000,
                    "price_digits": 4,
                    "volume_digits": 2,
                },
            },
        },
        3: {  # WBTC
            "POL": {
                1: {
                    "bid": 79500,
                    "ask": 79500,
                    "price_digits": 2,
                    "volume_digits": 6,
                },
                2: {
                    "bid": 79500,
                    "ask": 79500,
                    "price_digits": 2,
                    "volume_digits": 6,
                },
            },
            "BTC": {
                0: {
                    "bid": 0.9999,
                    "ask": 1.0001,
                    "price_digits": 4,
                    "volume_digits": 2,
                },
            },
        },
        4: {  # Link
            "POL": {
                1: {
                    "bid": 9.7,
                    "ask": 9.7,
                    "price_digits": 4,
                    "volume_digits": 3,
                },
                2: {
                    "bid": 9.7,
                    "ask": 9.7,
                    "price_digits": 4,
                    "volume_digits": 3,
                },
            },
            "BTC": {
                0: {
                    "bid": 0.00016,
                    "ask": 0.00016,
                    "price_digits": 8,
                    "volume_digits": 0,
                },
            },
        },
    },
    "BTC": {
        0: {  # BTC
            "POL": {
                1: {
                    "bid": 79500,
                    "ask": 79500,
                    "price_digits": 2,
                    "volume_digits": 6,
                },
                2: {
                    "bid": 79500,
                    "ask": 79500,
                    "price_digits": 2,
                    "volume_digits": 6,
                },
            },
        },
    },
    "XMR": {
        0: {  # XMR
            "POL": {
                1: {
                    "bid": 170,
                    "ask": 171,
                    "price_digits": 4,
                    "volume_digits": 5,
                },
                2: {
                    "bid": 170,
                    "ask": 171,
                    "price_digits": 4,
                    "volume_digits": 5,
                },
            },
            "BTC": {
                0: {
                    "bid": 0.0029,
                    "ask": 0.0029,
                    "price_digits": 6,
                    "volume_digits": 0,
                },
            },
        },
    },
    "BSC": {
        1: {  # USDT
            "POL": {
                1: {
                    "bid": 0.9999,
                    "ask": 1.0000,
                    "price_digits": 4,
                    "volume_digits": 2,
                },
                2: {
                    "bid": 0.9999,
                    "ask": 1.0000,
                    "price_digits": 4,
                    "volume_digits": 2,
                },
            },
            "BTC": {
                0: {
                    "bid": 0.000017,
                    "ask": 0.000017,
                    "price_digits": 8,
                    "volume_digits": 0,
                },
            },
        },
        2: {  # USDC
            "POL": {
                1: {
                    "bid": 0.9999,
                    "ask": 1.0000,
                    "price_digits": 4,
                    "volume_digits": 2,
                },
                2: {
                    "bid": 0.9999,
                    "ask": 1.0000,
                    "price_digits": 4,
                    "volume_digits": 2,
                },
            },
            "BTC": {
                0: {
                    "bid": 0.000017,
                    "ask": 0.000017,
                    "price_digits": 8,
                    "volume_digits": 0,
                },
            },
        },
        3: {  # WBTC
            "POL": {
                1: {
                    "bid": 79500,
                    "ask": 79500,
                    "price_digits": 2,
                    "volume_digits": 6,
                },
                2: {
                    "bid": 79500,
                    "ask": 79500,
                    "price_digits": 2,
                    "volume_digits": 6,
                },
            },
            "BTC": {
                0: {
                    "bid": 0.9999,
                    "ask": 1.0001,
                    "price_digits": 4,
                    "volume_digits": 2,
                },
            },
        },
        4: {  # Link
            "POL": {
                1: {
                    "bid": 9.7,
                    "ask": 9.7,
                    "price_digits": 4,
                    "volume_digits": 3,
                },
                2: {
                    "bid": 9.7,
                    "ask": 9.7,
                    "price_digits": 4,
                    "volume_digits": 3,
                },
            },
            "BTC": {
                0: {
                    "bid": 0.00016,
                    "ask": 0.00016,
                    "price_digits": 8,
                    "volume_digits": 0,
                },
            },
        },
    },
    "ARB": {
        1: {  # USDT
            "POL": {
                1: {
                    "bid": 0.9999,
                    "ask": 1.0000,
                    "price_digits": 4,
                    "volume_digits": 2,
                },
                2: {
                    "bid": 0.9999,
                    "ask": 1.0000,
                    "price_digits": 4,
                    "volume_digits": 2,
                },
            },
            "BTC": {
                0: {
                    "bid": 0.000017,
                    "ask": 0.000017,
                    "price_digits": 8,
                    "volume_digits": 0,
                },
            },
        },
        2: {  # USDC
            "POL": {
                1: {
                    "bid": 0.9999,
                    "ask": 1.0000,
                    "price_digits": 4,
                    "volume_digits": 2,
                },
                2: {
                    "bid": 0.9999,
                    "ask": 1.0000,
                    "price_digits": 4,
                    "volume_digits": 2,
                },
            },
            "BTC": {
                0: {
                    "bid": 0.000017,
                    "ask": 0.000017,
                    "price_digits": 8,
                    "volume_digits": 0,
                },
            },
        },
        3: {  # WBTC
            "POL": {
                1: {
                    "bid": 79500,
                    "ask": 79500,
                    "price_digits": 2,
                    "volume_digits": 6,
                },
                2: {
                    "bid": 79500,
                    "ask": 79500,
                    "price_digits": 2,
                    "volume_digits": 6,
                },
            },
            "BTC": {
                0: {
                    "bid": 0.9999,
                    "ask": 1.0001,
                    "price_digits": 4,
                    "volume_digits": 2,
                },
            },
        },
        4: {  # Link
            "POL": {
                1: {
                    "bid": 9.7,
                    "ask": 9.7,
                    "price_digits": 4,
                    "volume_digits": 2,
                },
                2: {
                    "bid": 9.7,
                    "ask": 9.7,
                    "price_digits": 4,
                    "volume_digits": 3,
                },
            },
            "BTC": {
                0: {
                    "bid": 0.00016,
                    "ask": 0.00016,
                    "price_digits": 8,
                    "volume_digits": 0,
                },
            },
        },
    },
}
