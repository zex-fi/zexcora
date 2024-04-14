import time
import timeit
import sys
import os
import json
import random
import asyncio
from typing import Dict, List
from pyfrost.network.sa import SA
from pyfrost.network.dkg import Dkg
from pyfrost.network.abstract import NodesInfo

dkg_key = {'public_key': 284631958478044684446231412428760194834653907338941878385172772357086753425604, 'public_shares': {'1': 440077668336695301399258258669815416678889591289318833292235040953770456986693, '2': 318548440132152467398752591869037649065642582038642161832289258690224090106397}, 'party': ['1', '2'], 'validations': {'1': [68231359375752989278793500661292392094386351847138172327535903164631648354772, 9851284974638528250189661658749126320539677692634955690238061599004892187733], '2': [61419297032865381029506887082052290225114544809391265396097334230828421841465, 78467982675300668434472433056755262741403418713798434526540567964803013026092]}, 'result': 'SUCCESSFUL'}

class ZexNodesInfo(NodesInfo):
    prefix = '/pyfrost'

    def __init__(self):
        with open('nodes.json') as f:
            self.nodes = json.loads(f.read())

        for n in self.nodes:
            self.nodes[n]['public_key'] = int(self.nodes[n]['public_key'], 16)

    def lookup_node(self, node_id: str = None):
        return self.nodes.get(node_id, {})

    def get_all_nodes(self, n: int = None) -> Dict:
        if n is None:
            n = len(self.nodes)
        return list(self.nodes.keys())[:n]


async def main(threshold: int) -> None:
    nodes_info = ZexNodesInfo()
    all_nodes = nodes_info.get_all_nodes()
    sa = SA(nodes_info, default_timeout=50)
    nonces = {}
    nonces_response = await sa.request_nonces(all_nodes)
    for node_id in all_nodes:
        nonces.setdefault(node_id, [])
        nonces[node_id] += nonces_response[node_id]['data']

    dkg_public_key = dkg_key['public_key']
    print(f'dkg key: {dkg_key}')

    print(f'Get signature with DKG public key {dkg_public_key}')

    dkg_party: List = dkg_key['party']
    nonces_dict = {}

    for node_id in dkg_party:
        nonce = nonces[node_id].pop()
        nonces_dict[node_id] = nonce

    now = timeit.default_timer()
    sa_data = {
        'method': 'withdraw',
        'params': {
            'id': 1234
        }
    }

    signature = await sa.request_signature(dkg_key, nonces_dict, sa_data, dkg_key['party'])
    then = timeit.default_timer()

    print(f'Requesting signature takes {then - now} seconds')
    print(f'Signature data: {signature}')


if __name__ == '__main__':
    threshold = int(sys.argv[1])
    asyncio.run(main(threshold))
