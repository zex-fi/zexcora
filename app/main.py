from contextlib import asynccontextmanager
from threading import Thread
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import uvicorn

from . import stop_event
from .api.main import api_router
from .api.routes.system import process_loop, transmit_tx
from .config import settings
from .utils.logger import FileConfig, setup_logging


# Run the broadcaster in the background
@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.zex.log_to_file:
        setup_logging(
            debug_mode=settings.zex.verbose,
            file_config=FileConfig(
                location=settings.zex.log_directory,
                rotation_size_in_mb=settings.zex.log_rotation_size_in_mb,
                retention_time_in_week=settings.zex.log_retention_time_in_week,
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


def main():
    uvicorn.run(
        app,
        host=settings.zex.host,
        port=settings.zex.port,
        access_log=False,
    )


if __name__ == "__main__":
    main()
