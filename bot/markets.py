QUOTES = {"BTC": [0], "HOL": [1, 2, 3]}
BASES = {
    "XMR": [0],
    "BST": [1, 2, 3, 4, 5, 6],
    "SEP": [1, 2, 3, 4],
}

BEST_BIDS = {
    "XMR": {
        0: {  # XMR
            "HOL": {
                1: (140.1, 100),  # (price, volume)
                2: (141.0, 90),  # (price, volume)
                3: (0.002537, 1),  # (price, volume)
            },
            "BTC": {
                0: (0.002538, 1),  # (price, volume)
            },
        },
    },
    "BST": {
        1: {  # ALICE
            "HOL": {
                1: (9.5, 100),  # (price, volume)
                2: (10.1, 90),  # (price, volume)
                3: (0.0001, 1),  # (price, volume)
            },
            "BTC": {
                0: (0.0001, 1),  # (price, volume)
            },
        },
        2: {  # PION
            "HOL": {
                1: (20, 100),  # (price, volume)
                2: (20.1, 90),  # (price, volume)
                3: (0.0002, 1),  # (price, volume)
            },
            "BTC": {
                0: (0.0002, 1),  # (price, volume)
            },
        },
        3: {  # USDT
            "HOL": {
                1: (1.01, 250),  # (price, volume)
                2: (0.99, 100),  # (price, volume)
                3: (0.000017, 1),  # (price, volume)
            },
            "BTC": {
                0: (0.000017, 1),  # (price, volume)
            },
        },
        4: {  # USDC
            "HOL": {
                1: (1.01, 250),  # (price, volume)
                2: (0.99, 100),  # (price, volume)
                3: (0.000017, 1),  # (price, volume)
            },
            "BTC": {
                0: (0.000017, 1),  # (price, volume)
            },
        },
        5: {  # WBTC
            "HOL": {
                1: (58000, 100),  # (price, volume)
                2: (58100, 90),  # (price, volume)
                3: (0.99, 1),  # (price, volume)
            },
            "BTC": {
                0: (1.01, 1),  # (price, volume)
            },
        },
        6: {  # LINK
            "HOL": {
                1: (9.7, 2),  # (price, volume)
                2: (9.8, 3),  # (price, volume)
                3: (0.00016, 1),  # (price, volume)
            },
            "BTC": {
                0: (0.00016, 1),  # (price, volume)
            },
        },
    },
    "SEP": {
        1: {  # USDT
            "HOL": {
                1: (1.01, 250),  # (price, volume)
                2: (0.99, 100),  # (price, volume)
                3: (0.000017, 1),  # (price, volume)
            },
            "BTC": {
                0: (0.000017, 1),  # (price, volume)
            },
        },
        2: {  # USDC
            "HOL": {
                1: (1.01, 250),  # (price, volume)
                2: (0.99, 100),  # (price, volume)
                3: (0.000017, 1),  # (price, volume)
            },
            "BTC": {
                0: (0.000017, 1),  # (price, volume)
            },
        },
        3: {  # WBTC
            "HOL": {
                1: (58000, 100),  # (price, volume)
                2: (58100, 90),  # (price, volume)
                3: (0.99, 1),  # (price, volume)
            },
            "BTC": {
                0: (1.01, 1),  # (price, volume)
            },
        },
        4: {  # LINK
            "HOL": {
                1: (9.7, 2),  # (price, volume)
                2: (9.8, 3),  # (price, volume)
                3: (0.00016, 1),  # (price, volume)
            },
            "BTC": {
                0: (0.00016, 1),  # (price, volume)
            },
        },
    },
}

BEST_ASKS = {
    "XMR": {
        0: {  # XMR
            "HOL": {
                1: (140.1, 100),  # (price, volume)
                2: (141.0, 90),  # (price, volume)
                3: (0.002537, 1),  # (price, volume)
            },
            "BTC": {
                0: (0.002540, 1),  # (price, volume)
            },
        },
    },
    "BST": {
        1: {  # ALICE
            "HOL": {
                1: (10.5, 100),  # (price, volume)
                2: (10.1, 90),  # (price, volume)
                3: (0.0001, 1),  # (price, volume)
            },
            "BTC": {
                0: (0.0001, 1),  # (price, volume)
            },
        },
        2: {  # PION
            "HOL": {
                1: (20, 100),  # (price, volume)
                2: (20.1, 90),  # (price, volume)
                3: (0.0002, 1),  # (price, volume)
            },
            "BTC": {
                0: (0.0001, 1),  # (price, volume)
            },
        },
        3: {  # USDT
            "HOL": {
                1: (1.01, 250),  # (price, volume)
                2: (0.99, 100),  # (price, volume)
                3: (0.000017, 1),  # (price, volume)
            },
            "BTC": {
                0: (0.000017, 1),  # (price, volume)
            },
        },
        4: {  # USDC
            "HOL": {
                1: (1.01, 250),  # (price, volume)
                2: (0.99, 100),  # (price, volume)
                3: (0.000017, 1),  # (price, volume)
            },
            "BTC": {
                0: (0.000017, 1),  # (price, volume)
            },
        },
        5: {  # WBTC
            "HOL": {
                1: (58000, 100),  # (price, volume)
                2: (58100, 90),  # (price, volume)
                3: (0.99, 1),  # (price, volume)
            },
            "BTC": {
                0: (1.01, 1),  # (price, volume)
            },
        },
        6: {  # LINK
            "HOL": {
                1: (9.7, 2),  # (price, volume)
                2: (9.8, 3),  # (price, volume)
                3: (0.00016, 1),  # (price, volume)
            },
            "BTC": {
                0: (0.00016, 1),  # (price, volume)
            },
        },
    },
    "SEP": {
        1: {  # USDT
            "HOL": {
                1: (1.01, 250),  # (price, volume)
                2: (0.99, 100),  # (price, volume)
                3: (0.000017, 1),  # (price, volume)
            },
            "BTC": {
                0: (0.00016, 1),  # (price, volume)
            },
        },
        2: {  # USDC
            "HOL": {
                1: (1.01, 250),  # (price, volume)
                2: (0.99, 100),  # (price, volume)
                3: (0.000017, 1),  # (price, volume)
            },
            "BTC": {
                0: (0.000017, 1),  # (price, volume)
            },
        },
        3: {  # WBTC
            "HOL": {
                1: (58000, 100),  # (price, volume)
                2: (58100, 90),  # (price, volume)
                3: (0.99, 1),  # (price, volume)
            },
            "BTC": {
                0: (1.01, 1),  # (price, volume)
            },
        },
        4: {  # LINK
            "HOL": {
                1: (9.7, 2),  # (price, volume)
                2: (9.8, 3),  # (price, volume)
                3: (0.00016, 1),  # (price, volume)
            },
            "BTC": {
                0: (0.00016, 1),  # (price, volume)
            },
        },
    },
}
