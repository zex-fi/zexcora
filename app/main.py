from contextlib import asynccontextmanager
from threading import Thread
import asyncio

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel
import uvicorn

from app import ZEX_HOST, ZEX_PORT, manager, stop_event
from app.api.main import api_router
from app.api.routes.system import process_loop, transmit_tx


class StreamRequest(BaseModel):
    id: int
    method: str
    params: list[str]


class StreamResponse(BaseModel):
    id: int
    result: str | None


class JSONMessageManager:
    @classmethod
    def handle(cls, message, websocket: WebSocket, context: dict):
        request = StreamRequest.model_validate_json(message)
        match request.method.upper():
            case "SUBSCRIBE":
                for channel in request.params:
                    parts = channel.split("@")
                    parts[0] = parts[0].upper()
                    manager.subscribe(websocket, "@".join(parts))
                return StreamResponse(id=request.id, result=None)
            case "UNSUBSCRIBE":
                for channel in request.params:
                    parts = channel.split("@")
                    parts[0] = parts[0].upper()
                    manager.unsubscribe(websocket, "@".join(parts))
                return StreamResponse(id=request.id, result=None)


# Run the broadcaster in the background
@asynccontextmanager
async def lifespan(_: FastAPI):
    t1 = Thread(
        target=asyncio.run,
        args=(process_loop(),),
    )
    t2 = Thread(
        target=asyncio.run,
        args=(transmit_tx(),),
    )

    t1.start()
    t2.start()
    yield

    # Signal the threads to stop
    stop_event.set()


app = FastAPI(
    lifespan=lifespan,
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    async def receive_messages():
        async for message in websocket.iter_text():
            response = JSONMessageManager.handle(message, websocket, context={})
            await websocket.send_text(response.model_dump_json())
        manager.remove(websocket)

    try:
        await receive_messages()
    except Exception as e:
        logger.exception(e)


if __name__ == "__main__":
    uvicorn.run(app, host=ZEX_HOST, port=ZEX_PORT, log_level="warning")
