from io import BytesIO
from threading import Event
import os

import httpx

from app.callbacks import depth_event, kline_event
from app.connection_manager import ConnectionManager

from .zex import Zex

ZEX_HOST = os.getenv("ZEX_HOST", "0.0.0.0")
ZEX_PORT = int(os.getenv("ZEX_PORT", 8000))

LIGHT_NODE = os.getenv("LIGHT_NODE")
ZEX_STATE_SOURCE = os.getenv("ZEX_STATE_SOURCE")
ZEX_STATE_DEST = os.getenv("ZEX_STATE_DEST")
ZEX_BTC_PUBLIC_KEY = os.getenv("ZEX_BTC_PUBLIC_KEY")
ZEX_MONERO_PUBLIC_ADDRESS = os.getenv("ZEX_MONERO_PUBLIC_ADDRESS")
ZEX_ETHERSCAN_API_KEY = os.getenv("ZEX_ETHERSCAN_API_KEY")

assert ZEX_STATE_DEST is not None, "ZEX_STATE_DEST must be specified"
assert ZEX_BTC_PUBLIC_KEY, "ZEX_BTC_PUBLIC_KEY env variable is not set"
assert ZEX_MONERO_PUBLIC_ADDRESS, "ZEX_MONERO_PUBLIC_ADDRESS env variable is not set"
assert ZEX_ETHERSCAN_API_KEY, "ZEX_ETHERSCAN_API_KEY env variable is not set"

manager = ConnectionManager()

# Global stop event
stop_event = Event()


if ZEX_STATE_SOURCE:
    response = httpx.get(ZEX_STATE_SOURCE)
    response.raise_for_status()
    data = BytesIO(response.content)
    zex = Zex.load_state(
        data=data,
        kline_callback=kline_event(manager),
        depth_callback=depth_event(manager),
        state_dest=ZEX_STATE_DEST,
        light_node=False if LIGHT_NODE is None else True,
    )
else:
    zex = Zex(
        kline_callback=kline_event(manager),
        depth_callback=depth_event(manager),
        state_dest=ZEX_STATE_DEST,
        light_node=False if LIGHT_NODE is None else True,
    )
