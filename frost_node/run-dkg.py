import asyncio
import sys

from pyfrost.network.dkg import Dkg

from frost_node.abstracts import NodesInfo

if __name__ == "__main__":
    all_nodes_count = int(sys.argv[1])
    threshold = int(sys.argv[2])

    nodes_info = NodesInfo()
    all_nodes = nodes_info.get_all_nodes(n=all_nodes_count)

    dkg = Dkg(nodes_info)
    result = asyncio.run(dkg.request_dkg(threshold, all_nodes))

    print(result)
