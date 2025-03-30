from config import settings
from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel
import redis

router = APIRouter()
app = FastAPI()

route_prefix = "/v1"


# Redis Cluster configuration
redis_nodes = []

# Redis cluster connection
redis_client = redis.Redis(
    host="redis",
    port=6379,
    db=0,
)


class Kline(BaseModel):
    CloseTime: int
    Open: float
    High: float
    Low: float
    Close: float
    Volume: float
    NumberOfTrades: int


type Price = str
type Quantity = str


class Depth(BaseModel):
    Ask: list[tuple[Price, Quantity]]
    Bid: list[tuple[Price, Quantity]]


class OrderBookAndKlineUpdate(BaseModel):
    kline: Kline | None = None
    depth: Depth | None = None


@router.post("/updates")
async def update_order_book_and_kline(updates: dict[str, OrderBookAndKlineUpdate]):
    print(updates)
    return {"status": "ok"}


@router.post("/events")
async def handle_events(events: list):
    print(events)
    return {"status": "ok"}


@router.post("/depth/")
async def update_order_book(update):
    symbol = update.symbol
    bids = update.bids
    asks = update.asks

    # Update the order book with the new bids and asks
    for price, quantity in bids:
        if quantity == 0:
            # Remove the price level if quantity is zero
            redis_client.hdel(symbol, f"bid:{price}")
        else:
            redis_client.hset(symbol, f"bid:{price}", quantity)

    for price, quantity in asks:
        if quantity == 0:
            # Remove the price level if quantity is zero
            redis_client.hdel(symbol, f"ask:{price}")
        else:
            redis_client.hset(symbol, f"ask:{price}", quantity)

    return {"status": "success", "message": "Order book updated"}


@router.get("/depth/{symbol}")
async def get_order_book(symbol: str):
    # Fetch the entire order book from Redis
    order_book = redis_client.hgetall(symbol)

    if not order_book:
        raise HTTPException(status_code=404, detail="Order book not found")

    # Parse the order book into bids and asks
    bids = []
    asks = []
    for key, value in order_book.items():
        key_str = key.decode()
        price = float(key_str.split(":")[1])
        quantity = float(value.decode())
        if key_str.startswith("bid:"):
            bids.append([price, quantity])
        elif key_str.startswith("ask:"):
            asks.append([price, quantity])

    # Sort bids (descending) and asks (ascending)
    bids.sort(reverse=True, key=lambda x: x[0])
    asks.sort(key=lambda x: x[0])

    return {"symbol": symbol, "bids": bids, "asks": asks}


app.include_router(router=router, prefix=settings.state_manager.api_prefix)


def main():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
