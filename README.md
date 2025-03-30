# Zex

> [!NOTE]
**Project Ownership Transition**:
> This project was originally developed and maintained by **Zellular** under the MIT license until the end of 2024.
> As of **January 1, 2025**, ownership and further development of this project have been transferred to **Zex**.

> [!CAUTION]
> This code serves as a proof of concept (PoC) for the core module of the Zellular exchange. The Zellular exchange is an application designed as an example of interacting with the sequencer. **Do NOT use this code in production environments. It is intended for testnet use only.**

## Dependencies
1. install `MCL` required for fastecdsa ([follow instructions](https://github.com/herumi/mcl?tab=readme-ov-file#how-to-build-with-cmake))
2. install libgmp4-dev
```bash
$ sudo apt install libgmp-dev
```

## install
### Poetry
install using `poetry install` from the project root directory

### pip
`cd` into the roo of the project and install using `pip install .`

In order to test the backend follow these steps:
1. run server: `TEST_MODE=1 python app/main.py`
2. use a websocket client like [https://hoppscotch.io/realtime/websocket](https://hoppscotch.io/realtime/websocket)
   1. connect to `ws://127.0.0.1:8000/api/v1/ws`
   2. send the following as json body to subscribe to events: 
    ```json
    {
        "method": "SUBSCRIBE",
        "params":
            [
                "BTC-USDT@kline_1m",
                "BTC-USDT@depth"
            ],
        "id": 1
    }
      ```
3. the data for each of the subscribed channels listed inside `params` will be sent as a json string according to binance websocket API
4. to stop receiving data from a channel modify the method to `UNSUBSCRIBE`

## Ports
1. Sequencer:                   15781
2. Zex:                         15782
3. Zex State Manager            15783
4. Zex Event Distributor        15784
5. Zex Websocket Service        15785
6. Zex State Source:            15786
