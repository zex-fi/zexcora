from struct import pack, unpack

from fastapi import APIRouter

from app import zex

router = APIRouter()


@router.get("/orders/{pair}/{name}")
def pair_orders(pair, name):
    pair = pair.split("_")
    pair = (
        pair[0].encode()
        + pack(">I", int(pair[1]))
        + pair[2].encode()
        + pack(">I", int(pair[3]))
    )
    q = zex.markets.get(pair)
    if not q:
        return []
    q = q.buy_orders if name == "buy" else q.sell_orders
    return [
        {
            "amount": unpack(">d", o[16:24])[0],
            "price": unpack(">d", o[24:32])[0],
        }
        for price, index, o in q
    ]
