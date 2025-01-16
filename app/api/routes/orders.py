from typing import Literal

from fastapi import APIRouter

from app import zex

router = APIRouter()


@router.get("/orders")
def pair_orders(pair: str, side: Literal["buy"] | Literal["sell"]):
    if pair not in zex.markets:
        return []
    market = zex.markets[pair]
    orders = market.buy_orders if side.lower() == "buy" else market.sell_orders

    return [
        {
            "price": price,
            "tx": tx.hex(),
        }
        for price, tx in orders
    ]
