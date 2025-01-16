from io import BytesIO
from threading import Event

from bitcoinutils.setup import setup
import httpx

from app.callbacks import (
    depth_event,
    kline_event,
    user_deposit_event,
    user_order_event,
    user_withdraw_event,
)
from app.connection_manager import ConnectionManager

from .config import settings
from .zex import Zex

setup("mainnet" if settings.zex.mainnet else "testnet")

manager = ConnectionManager()

# Global stop event
stop_event = Event()


def initialize_zex():
    if settings.zex.state_source == "":
        return Zex(
            kline_callback=kline_event(manager),
            depth_callback=depth_event(manager),
            order_callback=user_order_event(manager),
            deposit_callback=user_deposit_event(manager),
            withdraw_callback=user_withdraw_event(manager),
            state_dest=settings.zex.state_dest,
            light_node=settings.zex.light_node,
        )
    try:
        response = httpx.get(settings.zex.state_source)
        if response.status_code != 200 or len(response.content) == 0:
            return Zex(
                kline_callback=kline_event(manager),
                depth_callback=depth_event(manager),
                order_callback=user_order_event(manager),
                deposit_callback=user_deposit_event(manager),
                withdraw_callback=user_withdraw_event(manager),
                state_dest=settings.zex.state_dest,
                light_node=settings.zex.light_node,
            )
    except httpx.ConnectError:
        return Zex(
            kline_callback=kline_event(manager),
            depth_callback=depth_event(manager),
            order_callback=user_order_event(manager),
            deposit_callback=user_deposit_event(manager),
            withdraw_callback=user_withdraw_event(manager),
            state_dest=settings.zex.state_dest,
            light_node=settings.zex.light_node,
        )

    data = BytesIO(response.content)
    return Zex.load_state(
        data=data,
        kline_callback=kline_event(manager),
        depth_callback=depth_event(manager),
        order_callback=user_order_event(manager),
        deposit_callback=user_deposit_event(manager),
        withdraw_callback=user_withdraw_event(manager),
        state_dest=settings.zex.state_dest,
        light_node=settings.zex.light_node,
    )


zex = initialize_zex()
