from contextlib import asynccontextmanager
from threading import Thread
import asyncio
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import uvicorn

from . import stop_event
from .api.main import api_router
from .api.routes.system import process_loop, transmit_tx
from .config import settings


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
        colorize=debug_mode,
        serialize=False,
    )

    # File handlers
    logger.add(
        "logs/debug.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="10 MB",
        retention="1 week",
        serialize=not debug_mode,
    )

    logger.add(
        "logs/error.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="ERROR",
        rotation="10 MB",
        retention="1 month",
        serialize=not debug_mode,
    )


# Run the broadcaster in the background
@asynccontextmanager
async def lifespan(_: FastAPI):
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


def main():
    uvicorn.run(
        app,
        host=settings.zex.host,
        port=settings.zex.port,
        access_log=False,
    )


if __name__ == "__main__":
    main()
