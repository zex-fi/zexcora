from fastapi import APIRouter

from app import zex
from app.api.routes import markets, orders, system, users

api_router = APIRouter()
if zex.light_node:
    api_router.include_router(users.light_router)
else:
    api_router.include_router(system.router, tags=["system"])
    api_router.include_router(markets.router, tags=["markets"])
    api_router.include_router(users.router, tags=["users"])
    api_router.include_router(orders.router, tags=["orders"])
