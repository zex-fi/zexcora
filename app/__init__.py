import os

from app.callbacks import depth_event, kline_event
from app.connection_manager import ConnectionManager

from .zex import Zex

# ZSEQ_HOST = os.environ.get("ZSEQ_HOST")
# ZSEQ_PORT = int(os.environ.get("ZSEQ_PORT"))
# ZSEQ_URL = f"http://{ZSEQ_HOST}:{ZSEQ_PORT}/node/transactions"
BLS_PRIVATE = os.environ.get("BLS_PRIVATE")
assert BLS_PRIVATE, "BLS_PRIVATE env variableis not set"

manager = ConnectionManager()

zex = Zex(kline_callback=kline_event(manager), depth_callback=depth_event(manager))
