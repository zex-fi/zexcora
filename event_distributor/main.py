from contextlib import asynccontextmanager
import asyncio
import json

from config import settings
from fastapi import APIRouter, BackgroundTasks, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pika.adapters.asyncio_connection import AsyncioConnection
from pydantic import BaseModel
import pika
import pika.exceptions


class QueueItem(BaseModel):
    queue: str


class MessageBroker:
    def __init__(self, host: str, port: int, username: str, password: str):
        self.host = host
        self.port = port
        self.username = username
        self.password = password

        # Establish connection
        self.connection = None
        self.channel = None
        self.is_connected = False

    async def connect(self):
        parameters = pika.ConnectionParameters(
            host=self.host,  # Replace with your RabbitMQ host
            port=self.port,  # Default RabbitMQ port
            credentials=pika.PlainCredentials(
                self.username,
                self.password,
                erase_on_connect=True,
            ),
            heartbeat=600,
            blocked_connection_timeout=300,
        )

        try:
            self.connection = AsyncioConnection(
                parameters,
                on_open_callback=self.on_connection_open,
                on_open_error_callback=self.on_connection_open_error,
                on_close_callback=self.on_connection_closed,
            )
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            await asyncio.sleep(5)  # Wait before retrying
            await self.connect()

    def on_connection_open(self, _unused_connection):
        logger.info("RabbitMQ connection opened")
        self.is_connected = True
        self.open_channel()

    def on_connection_open_error(self, _unused_connection, err):
        logger.error(f"RabbitMQ connection open failed: {err}")
        self.is_connected = False
        asyncio.create_task(self.reconnect())

    def on_connection_closed(self, _unused_connection, reason):
        logger.warning(f"RabbitMQ connection closed: {reason}")
        self.is_connected = False
        asyncio.create_task(self.reconnect())

    def open_channel(self):
        logger.info("Creating a new RabbitMQ channel")
        self.connection.channel(on_open_callback=self.on_channel_open)

    async def reconnect(self):
        await asyncio.sleep(5)
        logger.info("Attempting to reconnect to RabbitMQ...")
        await self.connect()

    def on_channel_open(self, channel):
        logger.info("RabbitMQ channel opened")
        self.channel = channel
        self.channel.add_on_close_callback(self.on_channel_closed)

    def on_channel_closed(self, channel, reason):
        logger.warning(f"RabbitMQ channel closed: {reason}")
        self.channel = None
        if self.is_connected:
            self.open_channel()

    def send_message(self, stream: str, event: dict):
        """
        Send message to the appropriate message broker
        """
        try:
            # Publish message
            self.channel.basic_publish(
                exchange="",
                routing_key=stream,
                body=json.dumps(event),
                properties=pika.BasicProperties(
                    delivery_mode=pika.DeliveryMode.Transient  # Make message persistent
                ),
            )
        except pika.exceptions.ChannelClosed:
            logger.debug(f"no consumer for queue {stream}")
        except Exception as e:
            print(f"Error sending message: {type(e)}")


router = APIRouter()
app = FastAPI()

active_streams = set()

message_broker = MessageBroker(
    settings.event_distributor.broker.host,
    settings.event_distributor.broker.port,
    settings.event_distributor.broker.username,
    settings.event_distributor.broker.password,
)


async def process_events(events: list[dict]):
    """
    Process events and send to message broker if a listener exists
    """
    for event in events:
        # Check if stream exists (simulated listener check)
        if "stream" in event:
            # Validate stream name and send to message broker
            stream = event["stream"]
            if stream not in active_streams:
                continue
            try:
                message_broker.send_message(stream, event)
                print(f"Event sent to stream: {stream}")
            except Exception as e:
                print(f"Failed to process event for stream {stream}: {e}")


@router.post("/events")
async def handle_events(events: list[dict], background_tasks: BackgroundTasks):
    background_tasks.add_task(process_events, events)
    return {"status": "ok"}


@router.post("/activate")
async def activate_queue(item: QueueItem):
    if item.queue in active_streams:
        return {"success": False, "message": "queue already activated"}

    active_streams.add(item.queue)
    return {"success": True, "message": "queue added"}


@router.post("/deactivate")
async def deactivate_queue(item: QueueItem):
    if item.queue not in active_streams:
        return {"success": False, "message": "queue in not active"}

    active_streams.remove(item.queue)
    return {"success": True, "message": "queue deactivated"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    await message_broker.connect()

    yield


app = FastAPI(
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(router=router, prefix=settings.event_distributor.api_prefix)


def main():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
