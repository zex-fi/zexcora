from config import settings
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
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


app.mount("/state", StaticFiles(directory="state"), name="state")
app.include_router(router=router, prefix=settings.state_manager.api_prefix)


def main():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
