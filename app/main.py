from contextlib import asynccontextmanager
from threading import Thread
import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from app import manager
from app.api.main import api_router
from app.api.routes.system import process_loop, transmit_tx
from app.verify import close_pool


class StreamRequest(BaseModel):
    id: int
    method: str
    params: list[str]


class StreamResponse(BaseModel):
    id: int
    result: str | None


class JSONMessageManager:
    @classmethod
    def handle(self, message, websocket: WebSocket, context: dict):
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
    Thread(target=asyncio.run, args=(process_loop(),)).start()
    Thread(target=asyncio.run, args=(transmit_tx(),)).start()
    yield
    t = Thread(target=close_pool)
    t.start()


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

    try:
        await receive_messages()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
