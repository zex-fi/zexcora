# Zex

In order to test the backend follow these steps:
1. run server: `fastapi dev server.py`
2. use a websocket client like [https://hoppscotch.io/realtime/websocket](https://hoppscotch.io/realtime/websocket)
   1. connect to `ws://127.0.0.1:8000/ws`
   2. send the following as json body to subscribe to events:
      1. ```json
    {
        "method": "SUBSCRIBE",
        "params":
            [
                "eth:0-pol:0@kline_1m",
                "eth:0-pol:0@depth"
            ],
        "id": 1
    }
      ```
3. run the `test.py` script to deposit `usdt` and `wbtc` and send buy and sell transaction to the server. transaction are sent to the `/api/tx` endpoint as list of hex strings
4. the data for each of the subscribed channels listed inside `params` will be send as a json string according to binance websocket API
5. to stop receiving data from a channel modify the method to `SUBSCRIBE`