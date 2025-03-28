from contextlib import asynccontextmanager
from threading import Thread
import asyncio

from eth_utils.address import to_checksum_address
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel
import uvicorn

from . import stop_event
from .api.main import api_router
from .api.routes.system import process_loop, transmit_tx
from .config import settings
from .connection_manager import ConnectionManager
from .utils.logger import FileConfig, setup_logging

manager = ConnectionManager()


class StreamRequest(BaseModel):
    id: int
    method: str
    params: list[str]


class StreamResponse(BaseModel):
    id: int
    result: str | None


class JSONMessageManager:
    @staticmethod
    def normalize_channel(channel: str):
        symbol, task = channel.split("@")
        if ":" in symbol:
            base_token, quote_token = symbol.split("-")
            if ":" in base_token:
                base_chain, base_contract_address = base_token.split(":")
                try:
                    base_contract_address = to_checksum_address(base_contract_address)
                except ValueError as e:
                    logger.exception(e)
                    raise e

                base_token = f"{base_chain}:{base_contract_address}"
            if ":" in quote_token:
                quote_chain, quote_contract_address = quote_token.split(":")
                try:
                    quote_contract_address = to_checksum_address(quote_contract_address)
                except ValueError as e:
                    logger.exception(e)
                    raise e
                quote_token = f"{quote_chain}:{quote_contract_address}"
            symbol = f"{base_token}-{quote_token}"
        return f"{symbol}@{task}"

    @classmethod
    def handle(cls, message, websocket: WebSocket, context: dict):
        request = StreamRequest.model_validate_json(message)
        match request.method.upper():
            case "SUBSCRIBE":
                for channel in request.params:
                    try:
                        normal_channel = cls.normalize_channel(channel)
                    except ValueError:
                        return StreamResponse(
                            result={"error": "contract address is not valid"}
                        )
                    manager.subscribe(websocket, normal_channel)
                return StreamResponse(id=request.id, result=None)
            case "UNSUBSCRIBE":
                for channel in request.params:
                    try:
                        normal_channel = cls.normalize_channel(channel)
                    except ValueError:
                        return StreamResponse(
                            result={"error": "contract address is not valid"}
                        )
                    manager.unsubscribe(websocket, normal_channel)
                return StreamResponse(id=request.id, result=None)


# Run the broadcaster in the background
@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.zex.log_to_file:
        setup_logging(
            debug_mode=settings.zex.verbose,
            file_config=FileConfig(
                location=settings.zex.log_directory,
                rotation_size_in_mb=settings.zex.log_rotation_size_in_mb,
                retention_time_in_week=settings.zex.log_retention_time_in_week
            ),
            sentry_dsn=settings.zex.sentry_dsn,
            sentry_environment="production" if settings.zex.mainnet else "test",
        )
    else:
        setup_logging(debug_mode=settings.zex.verbose)

    t1 = Thread(
        target=asyncio.run,
        args=(transmit_tx(),),
    )
    t2 = Thread(
        target=asyncio.run,
        args=(process_loop(),),
    )

    t1.start()
    t2.start()
    yield

    # Signal the threads to stop
    stop_event.set()
    t1.join(1)
    t2.join(1)


app = FastAPI(
    lifespan=lifespan,
    docs_url="/v1/docs",
    redoc_url="/v1/redoc",
    openapi_url="/v1/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.zex.api_prefix)


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


def main():
    uvicorn.run(
        app,
        host=settings.zex.host,
        port=settings.zex.port,
        access_log=False,
    )


if __name__ == "__main__":
    main()
