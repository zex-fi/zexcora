import pytest
from app.zex import Zex


@pytest.fixture(scope="package")
def zex_instance():
    zex = Zex(lambda x, y: None, lambda x, y: None, "")
    return zex


def create_deposit_tx(chain, contract_address, decimal, amount):
    return ""

def test_process(zex_instance):
    assert False


def test_deposit():
    assert False


def test_withdraw():
    assert False


def test_validate_nonce():
    assert False
