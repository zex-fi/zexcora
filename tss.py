import os
import struct
import hashlib
import json
from pyfrost.network.node import Node
from pyfrost.network.abstract import Validators, DataManager, NodesInfo

VALIDATED_IPS = {
    '127.0.0.1': ['/pyfrost/v1/dkg/round1', '/pyfrost/v1/dkg/round2', '/pyfrost/v1/dkg/round3', '/pyfrost/v1/sign', '/pyfrost/v1/generate-nonces']
}

class ZexDataManager(DataManager):
    def __init__(self, node_id):
        super().__init__()
        self.__dkg_keys = {}
        self.__nonces = {}
        self.node_id = node_id

    def set_nonce(self, nonce_public, nonce_private):
        self.__nonces[nonce_public] = nonce_private

    def get_nonce(self, nonce_public):
        return self.__nonces[nonce_public]

    def remove_nonce(self, nonce_public):
        del self.__nonces[nonce_public]

    def set_key(self, key, value):
        self.__dkg_keys[key] = value
        with open(f'data/shares_{self.node_id}.json', 'w') as f:
            f.write(json.dumps(self.__dkg_keys))

    def get_key(self, key):
        if key not in self.__dkg_keys:
            with open(f'data/shares_{self.node_id}.json') as f:
                self.__dkg_keys = json.loads(f.read())
        return self.__dkg_keys.get(key, {})

    def remove_key(self, key):
        del self.__dkg_keys[key]


class ZexValidators(Validators):
    def __init__(self):
        super().__init__()

    @staticmethod
    def caller_validator(sender_ip, method):
        if method in VALIDATED_IPS.get(str(sender_ip), []):
            return True
        return False

    @staticmethod
    def data_validator(input_data):
        method, params = input_data['method'], input_data['params']
        if method == 'withdraw':
            msg = struct.pack('I', params['id'])
            hash_hex = hashlib.sha3_256(msg).hexdigest()
            result = { 'hash': hash_hex }
        else:
            raise Exception('invalid method')
        return result


class ZexNodesInfo(NodesInfo):
    prefix = '/pyfrost'

    def __init__(self):
        with open('data/nodes.json') as f:
            self.nodes = json.loads(f.read())
        for n in self.nodes:
            self.nodes[n]['public_key'] = int(self.nodes[n]['public_key'], 16)

    def lookup_node(self, node_id=None):
        return self.nodes.get(node_id, {})

    def get_all_nodes(self, n=None):
        if n is None:
            n = len(self.nodes)
        return list(self.nodes.keys())[:n]


def pyfrost_blueprint():
    private = int(os.environ.get("PYFROST_PRIVATE"), 16)
    node_id = int(os.environ.get("PYFROST_NODE_ID"))
    data_manager = ZexDataManager(node_id)
    nodes_info = ZexNodesInfo()
    node = Node(data_manager, str(node_id), private, nodes_info,
                ZexValidators.caller_validator, ZexValidators.data_validator)
    return node.blueprint