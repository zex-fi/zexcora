import asyncio
import json

import websockets

# WebSocket server details
WS_URI = "ws://127.0.0.1:15782/ws"
NUM_CLIENTS = 1000  # Number of concurrent clients to simulate

# JSON data to send to the server
SUBSCRIPTION_MSG = {
    "method": "SUBSCRIBE",
    "params": [
        "038cb5a29c20c25db647628313a90ac3e53186cc268fff91b0e03a2a2b18baa550@executionReport",
        "zEIGEN-zUSDT@depth",
        "zEIGEN-zUSDT@kline",
        "zWBTC-zUSDT@depth",
        "zWBTC-zUSDT@kline",
    ],
    "id": 1,
}


# Coroutine to simulate a single WebSocket client
async def websocket_client(client_id):
    try:
        async with websockets.connect(WS_URI) as websocket:
            print(f"Client {client_id} connected")

            # Send the subscription message to the server
            await websocket.send(json.dumps(SUBSCRIPTION_MSG))
            print(f"Client {client_id} sent subscription message")

            # Start receiving messages from the server
            while True:
                await websocket.recv()
                # print(f"Client {client_id} received: {message}")
    except Exception as e:
        print(f"Client {client_id} encountered an error: {e}")


# Coroutine to start multiple WebSocket clients
async def run_load_test():
    start_time = asyncio.get_event_loop().time()

    # Create tasks for all clients
    tasks = [asyncio.create_task(websocket_client(i)) for i in range(NUM_CLIENTS)]

    # Wait for all clients to complete (or run indefinitely)
    await asyncio.gather(*tasks)

    end_time = asyncio.get_event_loop().time()
    print(f"Load test completed in {end_time - start_time:.2f} seconds")


# Run the load test
asyncio.run(run_load_test())
