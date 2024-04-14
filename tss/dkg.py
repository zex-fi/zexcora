import timeit
import sys
import json
import asyncio
from typing import Dict
from pyfrost.network.dkg import Dkg
from pyfrost.network.abstract import NodesInfo


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
    dkg = Dkg(nodes_info, default_timeout=50)
    now = timeit.default_timer()
    dkg_key = await dkg.request_dkg(threshold, all_nodes)
    then = timeit.default_timer()

    print(f'Requesting DKG takes: {then - now} seconds.')
    print(f'The DKG result is {dkg_key["result"]}')

    dkg_public_key = dkg_key['public_key']
    print(f'dkg key: {dkg_key}')


if __name__ == '__main__':
    threshold = int(sys.argv[1])
    asyncio.run(main(threshold))
