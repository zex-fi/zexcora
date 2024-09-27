import hashlib
import json
import os.path as osp

import requests
from eth_abi.packed import encode_packed
from pyfrost.network.abstract import DataManager, Validators
from pyfrost.network.abstract import NodesInfo as BaseNodesInfo

from .config import VALIDATED_IPS


class NodeDataManager(DataManager):
    def __init__(self) -> None:
        super().__init__()
        self.__dkg_keys_path = "dkg.shares"
        try:
            if osp.getsize(self.__dkg_keys_path) == 0:
                self.__dkg_keys = {}
            else:
                with open(self.__dkg_keys_path) as f:
                    self.__dkg_keys = json.load(f)
        except FileNotFoundError:
            self.__dkg_keys = {}

        self.__nonces = {}

    def set_nonce(self, nonce_public: str, nonce_private: str) -> None:
        self.__nonces[nonce_public] = nonce_private

    def get_nonce(self, nonce_public: str):
        return self.__nonces[nonce_public]

    def remove_nonce(self, nonce_public: str) -> None:
        del self.__nonces[nonce_public]

    def set_key(self, key, value) -> None:
        self.__dkg_keys[key] = value
        with open(self.__dkg_keys_path, "w") as f:
            json.dump(self.__dkg_keys, f)

    def get_key(self, key):
        return self.__dkg_keys.get(key, {})

    def remove_key(self, key):
        del self.__dkg_keys[key]
        with open(self.__dkg_keys_path, "w") as f:
            json.dump(self.__dkg_keys, f)


class NodeValidators(Validators):
    def __init__(self) -> None:
        super().__init__()

    @staticmethod
    def caller_validator(sender_ip: str, method: str):
        if method in VALIDATED_IPS.get(str(sender_ip), []):
            return True
        return False

    @staticmethod
    def data_validator(input_data: dict):
        chain = input_data["chain"]
        public = input_data["public"]
        nonce = input_data["nonce"]

        url = f"http://127.0.0.1:8000/api/v1/user/{public}/withdraws/{chain}/{nonce}"
        resp = requests.get(url)
        resp.raise_for_status()
        zex_data = resp.json()

        zex_packed = encode_packed(
            ["bytes3", "uint8", "string", "string", "address", "uint32", "uint32"],
            [
                zex_data["chain"],
                zex_data["tokenID"],
                zex_data["amount"],
                zex_data["user"],
                zex_data["destination"],
                zex_data["t"],
                zex_data["nonce"],
            ],
        )

        hash_hex = hashlib.sha256(zex_packed).digest()

        return {
            "data": input_data,
            "hash": hash_hex,
        }


NODES_INFO = {
    "1": {
        "public_key": 317261279852899074313183185542781032616418573647151905000540258178325142514530,
        "host": "127.0.0.1",
        "port": str(5000 + 0),
    },
    "2": {
        "public_key": 448383939583839765699883543643790268073515315738637988752301536519479955492703,
        "host": "127.0.0.1",
        "port": str(5000 + 1),
    },
    "3": {
        "public_key": 245244277969302639771235170628466784507179141748552837571651825035719962202519,
        "host": "127.0.0.1",
        "port": str(5000 + 2),
    },
}


class NodesInfo(BaseNodesInfo):
    prefix = "/pyfrost"

    def __init__(self):
        self.nodes = NODES_INFO

    def lookup_node(self, node_id: str = None):
        return self.nodes.get(node_id, {})

    def get_all_nodes(self, n: int = None) -> dict:
        if n is None:
            n = len(self.nodes)
        return list(self.nodes.keys())[:n]
