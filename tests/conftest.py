from collections.abc import Generator
from decimal import Decimal

from secp256k1 import PrivateKey
import pytest

from ..app.config import settings
from ..app.zex import Zex
from ..app.zex_types import Token


@pytest.fixture(scope="function")
def zex_instance() -> Generator[Zex]:
    # Mock callbacks
    async def kline_callback(symbol, df):
        pass

    async def depth_callback(symbol, data):
        pass

    async def order_callback(*args, **kwargs):
        pass

    async def deposit_callback(public, chain, token, amount):
        pass

    async def withdraw_callback(public, chain, token, amount):
        pass

    settings.zex.fill_dummy = False
    settings.zex.verified_tokens = {
        "zUSDT": {
            "HOL": Token(
                contract_address="0x325CCd77e71Ac296892ed5C63bA428700ec0f868",
                balance_withdraw_limit=Decimal("1"),
                decimal=6,
            ),
            "SEP": Token(
                contract_address="0x325CCd77e71Ac296892ed5C63bA428700ec0f868",
                balance_withdraw_limit=Decimal("1"),
                decimal=6,
            ),
            "BST": Token(
                contract_address="0x325CCd77e71Ac296892ed5C63bA428700ec0f868",
                balance_withdraw_limit=Decimal("1"),
                decimal=6,
            ),
        },
        "zEIGEN": {
            "HOL": Token(
                contract_address="0x219f1708400bE5b8cC47A56ed2f18536F5Da7EF4",
                balance_withdraw_limit=Decimal("0.01"),
                decimal=18,
            ),
            "SEP": Token(
                contract_address="0x219f1708400bE5b8cC47A56ed2f18536F5Da7EF4",
                balance_withdraw_limit=Decimal("0.01"),
                decimal=18,
            ),
            "BST": Token(
                contract_address="0x219f1708400bE5b8cC47A56ed2f18536F5Da7EF4",
                balance_withdraw_limit=Decimal("0.01"),
                decimal=18,
            ),
        },
        "zWBTC": {
            "HOL": Token(
                contract_address="0x9d84f6e4D734c33C2B6e7a5211780499A71aEf6A",
                balance_withdraw_limit=Decimal("0.00001"),
                decimal=8,
            ),
            "SEP": Token(
                contract_address="0x9d84f6e4D734c33C2B6e7a5211780499A71aEf6A",
                balance_withdraw_limit=Decimal("0.00001"),
                decimal=8,
            ),
            "BST": Token(
                contract_address="0x9d84f6e4D734c33C2B6e7a5211780499A71aEf6A",
                balance_withdraw_limit=Decimal("0.00001"),
                decimal=8,
            ),
        },
    }
    zex = Zex(
        kline_callback,
        depth_callback,
        order_callback,
        deposit_callback,
        withdraw_callback,
        state_dest="test_state.bin",
        light_node=False,
        benchmark_mode=False,
    )
    yield zex
    Zex.reset(Zex)


@pytest.fixture(scope="module")
def client_private1():
    return PrivateKey(
        bytes.fromhex(
            "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        ),
        raw=True,
    )


@pytest.fixture(scope="module")
def client_private2():
    return PrivateKey(
        bytes.fromhex(
            "2234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        ),
        raw=True,
    )
