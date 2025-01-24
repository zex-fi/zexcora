from typing import Literal

from fastapi import APIRouter

from app.zex import Zex

router = APIRouter()
zex = Zex.initialize_zex()


@router.get("/orders")
def pair_orders(pair: str, side: Literal["buy"] | Literal["sell"]):
    if pair not in zex.state_manager.markets:
        return []
    market = zex.state_manager.markets[pair]
    orders = market.buy_orders if side.lower() == "buy" else market.sell_orders

    return [
        {
            "price": price,
            "tx": tx.hex(),
        }
        for price, tx in orders
    ]
