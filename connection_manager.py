from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: set[WebSocket] = set()
        self.subscriptions: dict[str, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

    def subscribe(self, websocket: WebSocket, channel: str):
        if channel not in self.subscriptions:
            self.subscriptions[channel] = set()
        self.subscriptions[channel].add(websocket)
        return f"Subscribed to {channel}"

    def unsubscribe(self, websocket: WebSocket, channel: str):
        if channel in self.subscriptions and websocket in self.subscriptions[channel]:
            self.subscriptions[channel].remove(websocket)
            if not self.subscriptions[channel]:  # Remove channel if empty
                del self.subscriptions[channel]
            return f"Unsubscribed from {channel}"
        return f"Not subscribed to {channel}"
