from fastapi import APIRouter

from app.api.routes import (
    charts,
    drawing_templates,
    markets,
    orders,
    study_templates,
    system,
    users,
)
from app.zex import Zex

api_router = APIRouter()
zex = Zex.initialize_zex()

if zex.light_node:
    api_router.include_router(users.light_router)
else:
    api_router.include_router(system.router, tags=["system"])
    api_router.include_router(markets.router, tags=["markets"])
    api_router.include_router(users.router, tags=["users"])
    api_router.include_router(orders.router, tags=["orders"])
    api_router.include_router(charts.router)
    api_router.include_router(drawing_templates.router)
    api_router.include_router(study_templates.router)
