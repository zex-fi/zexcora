import asyncio
import json
from websockets.sync.client import connect
import requests
from pprint import pprint

ORDER_BOOK = {"lastUpdateId": 0, "bids": {}, "asks": {}}

host = "89.106.206.214"
port = 8000


def get_depth():
    res = requests.get(
        f"http://{host}:{port}/api/fapi/v1/depth?symbol=eth%3A0-pol%3A0&limit=500"
    )
    data = res.json()
    ORDER_BOOK["lastUpdateId"] = data["lastUpdateId"]
    for price, qty in data["bids"]:
        ORDER_BOOK["bids"][price] = qty

    for price, qty in data["asks"]:
        ORDER_BOOK["asks"][price] = qty

    return data["lastUpdateId"]


def main():
    last_update_id = get_depth()
    with connect(f"ws://{host}:{port}/ws") as websocket:
        websocket.send(
            json.dumps(
                {
                    "method": "SUBSCRIBE",
                    "params": ["eth:0-pol:0@depth"],
                    "id": 1,
                }
            )
        )
        for message in websocket:
            data = json.loads(message)
            if "stream" not in data or data["stream"] != "eth:0-pol:0@depth":
                print(data)
                print("skipping...")
                continue
            data = data["data"]
            first_id = data["U"]
            final_id = data["u"]
            pu = data["pu"]
            if final_id < last_update_id:
                print("small final id. skipping...")
                continue
            if pu != last_update_id:
                print(f"pu != last_update_id: {pu} != {last_update_id}")
            last_update_id = final_id
            ORDER_BOOK["lastUpdateId"] = last_update_id
            for price, qty in data["b"]:
                if qty == 0:
                    if price in ORDER_BOOK["bids"]:
                        del ORDER_BOOK["bids"][price]
                else:
                    ORDER_BOOK["bids"][price] = qty
            for price, qty in data["a"]:
                if qty == 0:
                    if price in ORDER_BOOK["asks"]:
                        del ORDER_BOOK["asks"][price]
                else:
                    ORDER_BOOK["asks"][price] = qty


try:
    main()
finally:
    pprint(ORDER_BOOK, indent=2)
