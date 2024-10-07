import json
import logging
import os
import sys

from flask import Flask
from pyfrost.network.node import Node
from web3 import Account

from frost_node import (
    NodeDataManager,
    NodesInfo,
    NodeValidators,
)


def run_node(node_number: int) -> None:
    data_manager = NodeDataManager()
    nodes_info = NodesInfo()
    private_file = os.getenv("FROST_NODE_PRIVATE_FILE")
    assert private_file is not None, "FROST_NODE_PRIVATE_FILE env variable is not set"

    private_file_password = os.getenv("FROST_NODE_PRIVATE_PASSWORD")
    assert (
        private_file_password is not None
    ), "FROST_NODE_PRIVATE_PASSWORD env variable is not set"

    with open(private_file) as f:
        data = json.load(f)
        private_hex = Account.decrypt(data, private_file_password)

    node = Node(
        data_manager,
        node_number,
        int.from_bytes(private_hex, byteorder="big"),
        nodes_info,
        NodeValidators.caller_validator,
        NodeValidators.data_validator,
    )
    node_info = nodes_info.lookup_node(str(node_number))
    app = Flask(__name__)
    app.register_blueprint(node.blueprint, url_prefix="/pyfrost")
    app.run(host=node_info["host"], port=int(node_info["port"]), debug=True)


if __name__ == "__main__":
    node_number = int(sys.argv[1])
    file_path = "logs"
    file_name = f"node{node_number}.log"
    log_formatter = logging.Formatter(
        "%(asctime)s - %(message)s",
    )
    root_logger = logging.getLogger()
    if not os.path.exists(file_path):
        os.mkdir(file_path)
    with open(f"{file_path}/{file_name}", "w"):
        pass
    file_handler = logging.FileHandler(f"{file_path}/{file_name}")
    file_handler.setFormatter(log_formatter)
    root_logger.addHandler(file_handler)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    root_logger.addHandler(console_handler)
    root_logger.setLevel(logging.DEBUG)
    sys.set_int_max_str_digits(0)

    try:
        run_node(node_number)
    except KeyboardInterrupt:
        pass
