from fastapi import APIRouter

from app.api.routes import markets, orders, system, users

api_router = APIRouter()
api_router.include_router(system.router, tags=["system"])
api_router.include_router(markets.router, tags=["markets"])
api_router.include_router(users.router, tags=["users"])
api_router.include_router(orders.router, tags=["orders"])
