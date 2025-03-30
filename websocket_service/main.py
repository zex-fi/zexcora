from contextlib import asynccontextmanager
import asyncio

from config import settings
from eth_utils.address import to_checksum_address
from fastapi import APIRouter, FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.websockets import WebSocketState
from loguru import logger
from pika.adapters.asyncio_connection import AsyncioConnection
from pydantic import BaseModel
import httpx
import pika


class RabbitMQConsumer:
    def __init__(self, host: str, port: int, username: str, password: str):
        """
        Initialize RabbitMQ consumer

        :param host: RabbitMQ host
        :param queues: List of queues to consume from
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password

        # Establish connection
        self.connection = None
        self.channel = None
        self.is_connected = False
        self.queues: dict[
            str, set[WebSocket]
        ] = {}  # Maps queue names to sets of WebSocket clients

    async def connect(self):
        if self.is_connected:
            return

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

    async def reconnect(self):
        await asyncio.sleep(5)
        logger.info("Attempting to reconnect to RabbitMQ...")
        await self.connect()

    def open_channel(self):
        logger.info("Creating a new RabbitMQ channel")
        self.connection.channel(on_open_callback=self.on_channel_open)

    def on_channel_open(self, channel):
        logger.info("RabbitMQ channel opened")
        self.channel = channel
        self.channel.add_on_close_callback(self.on_channel_closed)

        # Re-declare all queues for existing subscriptions
        for queue_name in self.queues.keys():
            self.setup_queue(queue_name)

    def on_channel_closed(self, channel, reason):
        logger.warning(f"RabbitMQ channel closed: {reason}")
        self.channel = None
        if self.is_connected:
            self.open_channel()

    def setup_queue(self, queue_name: str):
        if not self.channel:
            logger.error("Cannot setup queue - channel not available")
            return

        def on_queue_declared(_unused_frame):
            logger.info(f"Queue declared: {queue_name}")
            httpx.post(
                f"{settings.websocket_service.event_distributor}/activate",
                json={"queue": queue_name},
            )
            self.channel.basic_consume(
                queue=queue_name,
                on_message_callback=lambda ch,
                method,
                properties,
                body: self.on_message(ch, method, properties, body, queue_name),
                auto_ack=True,
            )

        queue_args = {
            "x-message-ttl": settings.websocket_service.broker.message_ttl
            * 1000  # TTL in milliseconds (60000 = 60 seconds)
        }

        self.channel.queue_declare(
            queue=queue_name,
            callback=on_queue_declared,
            durable=True,
            auto_delete=False,
            arguments=queue_args,
        )

    def on_message(
        self, _unused_channel, method, _unused_properties, body, queue_name: str
    ):
        message = body.decode()
        logger.debug(f"Received message from {queue_name}: {message}")

        # Forward message to all subscribed WebSocket clients
        if queue_name in self.queues:
            for websocket in self.queues[queue_name].copy():
                if websocket.client_state == WebSocketState.CONNECTED:
                    asyncio.create_task(self.send_to_websocket(websocket, message))

    async def send_to_websocket(self, websocket: WebSocket, message: str):
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Failed to send message to WebSocket: {e}")
            self.remove_websocket_from_all_queues(websocket)

    def add_subscription(self, queue_name: str, websocket: WebSocket):
        if queue_name not in self.queues:
            self.queues[queue_name] = set()
            if self.channel:
                self.setup_queue(queue_name)

        self.queues[queue_name].add(websocket)
        logger.info(f"Added subscription to {queue_name} for WebSocket {id(websocket)}")

    def remove_subscription(self, queue_name: str, websocket: WebSocket):
        if queue_name in self.queues and websocket in self.queues[queue_name]:
            self.queues[queue_name].remove(websocket)
            logger.info(
                f"Removed subscription to {queue_name} for WebSocket {id(websocket)}"
            )

            if not self.queues[queue_name]:
                del self.queues[queue_name]
                self.channel.queue_delete(queue_name)
                httpx.post(
                    f"{settings.websocket_service.event_distributor}/deactivate",
                    json={"queue": queue_name},
                )
                logger.info(
                    f"No more subscribers for {queue_name}, removed from tracking"
                )

    def remove_websocket_from_all_queues(self, websocket: WebSocket):
        queues_to_remove = []
        for queue_name, websockets in self.queues.items():
            if websocket in websockets:
                websockets.remove(websocket)
                logger.info(f"Removed WebSocket {id(websocket)} from {queue_name}")

                if not websockets:
                    queues_to_remove.append(queue_name)

        for queue_name in queues_to_remove:
            del self.queues[queue_name]
            self.channel.queue_delete(queue_name)
            httpx.post(
                f"{settings.websocket_service.event_distributor}/deactivate",
                json={"queue": queue_name},
            )
            logger.info(f"No more subscribers for {queue_name}, removed from tracking")


router = APIRouter()

consumer = RabbitMQConsumer(
    settings.websocket_service.broker.host,
    settings.websocket_service.broker.port,
    settings.websocket_service.broker.username,
    settings.websocket_service.broker.password,
)


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
                            id=request.id,
                            result="error: contract address is not valid",
                        )
                    consumer.add_subscription(normal_channel, websocket)
                return StreamResponse(id=request.id, result=None)
            case "UNSUBSCRIBE":
                for channel in request.params:
                    try:
                        normal_channel = cls.normalize_channel(channel)
                    except ValueError:
                        return StreamResponse(
                            id=request.id,
                            result="error: contract address is not valid",
                        )
                    consumer.remove_subscription(normal_channel, websocket)
                return StreamResponse(id=request.id, result=None)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    async def receive_messages():
        async for message in websocket.iter_text():
            response = JSONMessageManager.handle(message, websocket, context={})
            await websocket.send_text(response.model_dump_json())

    try:
        await receive_messages()
    except Exception as e:
        logger.exception(e)
    finally:
        consumer.remove_websocket_from_all_queues(websocket)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await consumer.connect()

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

app.include_router(router=router, prefix=settings.websocket_service.api_prefix)


def main():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
