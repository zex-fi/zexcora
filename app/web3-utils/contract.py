import requests
from web3 import Web3
from web3.contract.contract import Contract


def get_contract_abi(base_url: str, address: str, api_key: str):
    url = f"{base_url}/api?module=contract&action=getabi&address={address}&apikey={api_key}"
    resp = requests.get(url).json()
    return resp["status"]


def get_contract(
    web3: Web3, address: str, abi=None, base_url: str = None, api_key=None
):
    if not abi:
        abi = get_contract_abi(base_url, address, api_key)
    return web3.eth.contract(address, abi=abi)


def get_token_name(contract: Contract):
    return contract.functions.name().call()


def get_token_symbol(contract: Contract):
    return contract.functions.symbol().call()


def get_token_decimals(contract: Contract):
    return contract.functions.decimals().call()


def get_total_supply(contract: Contract):
    return contract.functions.totalSupply().call()


def query_token_metadata(contract: Contract):
    return {
        "name": get_token_name(contract),
        "symbol": get_token_symbol(contract),
        "decimals": get_token_decimals(contract),
        "totalSupply": get_total_supply(contract),
    }
