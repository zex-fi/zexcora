from contextlib import asynccontextmanager
from threading import Thread
import asyncio
import sys

from eth_utils.address import to_checksum_address
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel
import uvicorn

from app import manager, stop_event
from app.api.main import api_router
from app.api.routes.system import process_loop, transmit_tx
from app.config import settings
from app.verify import TransactionVerifier


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
    verifier = TransactionVerifier(num_processes=4)
    t1 = Thread(
        target=asyncio.run,
        args=(transmit_tx(verifier),),
    )
    t2 = Thread(
        target=asyncio.run,
        args=(process_loop(verifier),),
    )

    t1.start()
    t2.start()
    yield

    # Signal the threads to stop
    stop_event.set()
    verifier.cleanup()
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


def setup_logging(debug_mode: bool = False):
    """Configure logging for the application."""
    # Remove default handler
    logger.remove()

    # Determine minimum console log level based on debug mode
    console_level = "DEBUG" if debug_mode else "INFO"

    # Console handler
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=console_level,
        colorize=True,
        # serialize=True,
    )

    # File handlers
    logger.add(
        "logs/debug.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="10 MB",
        retention="1 week",
        # serialize=True,
    )

    logger.add(
        "logs/error.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="ERROR",
        rotation="10 MB",
        retention="1 month",
        # serialize=True,
    )


if __name__ == "__main__":
    setup_logging(debug_mode=settings.zex.verbose)
    uvicorn.run(
        app,
        host=settings.zex.host,
        port=settings.zex.port,
        # log_level="debug" if settings.zex.verbose else "info",
    )
