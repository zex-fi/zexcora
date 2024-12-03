import time

from fastapi import APIRouter, Form, HTTPException, Query

from .tables import Chart

charts_collection = Chart("db.sqlite")

router = APIRouter(prefix="/1.1/charts", tags=["charts"])


@router.get("/")
def get_charts(
    client_id: str = Query(..., alias="client"),
    user_id: str = Query(..., alias="user"),
    chart_id: str | None = Query(None, alias="chart"),
):
    if user_id <= 0:
        raise HTTPException(404, "invalid user id")
    if chart_id is None:
        return get_all_user_charts(client_id, user_id)
    else:
        return get_chart_content(client_id, user_id, chart_id)


@router.delete("/")
def delete_charts(
    client_id: str = Query(..., alias="client"),
    user_id: str = Query(..., alias="user"),
    chart_id: str | None = Query(None, alias="chart"),
):
    if user_id <= 0:
        raise HTTPException(404, "invalid user id")
    if chart_id is None:
        raise HTTPException(404, "Wrong chart id")
    else:
        return remove_chart(client_id, user_id, chart_id)


@router.post("/")
def set_charts(
    client_id: str = Query(..., alias="client"),
    user_id: str = Query(..., alias="user"),
    chart_id: str | None = Query(None, alias="chart"),
    chart_name: str = Form(..., alias="name"),
    content: str = Form(..., alias="content"),
    symbol: str = Form(..., alias="symbol"),
    resolution: str = Form(..., alias="resolution"),
):
    if user_id <= 0:
        raise HTTPException(404, "invalid user id")
    if chart_id is None:
        return save_chart(client_id, user_id, chart_name, symbol, resolution, content)
    else:
        return rewrite_chart(
            client_id, user_id, chart_id, chart_name, symbol, resolution, content
        )


def get_all_user_charts(client_id, user_id):
    _filter = {"owner_source": client_id, "owner_id": user_id}
    projection = ["id", "name", "timestamp", "symbol", "resolution"]
    result = charts_collection.find(_filter, projection)
    for document in result:
        document["id"] = str(document["id"])

    return {"status": "ok", "data": result}


def get_chart_content(client_id, user_id, chart_id):
    _filter = {"id": int(chart_id), "owner_source": client_id, "owner_id": user_id}
    projection = ["id", "name", "timestamp", "content"]
    found_chart: dict = charts_collection.find_one(_filter, projection)
    if not found_chart:
        raise HTTPException(404, "Chart not found")

    found_chart["id"] = str(found_chart["id"])

    return {"status": "ok", "data": found_chart}


def remove_chart(client_id, user_id, chart_id):
    _filter = {"id": int(chart_id), "owner_source": client_id, "owner_id": user_id}
    charts_collection.delete_one(_filter)
    return {"status": "ok"}


def save_chart(client_id, user_id, chart_name, symbol, resolution, content):
    now = int(time.time())
    inserted_id = charts_collection.insert_one(
        {
            "owner_source": client_id,
            "owner_id": user_id,
            "name": chart_name,
            "content": content,
            "timestamp": now,
            "symbol": symbol,
            "resolution": resolution,
        }
    )
    chart_id = str(inserted_id)
    return {"status": "ok", "id": chart_id}


def rewrite_chart(
    client_id, user_id, chart_id, chart_name, symbol, resolution, content
):
    now = int(time.time())
    chart_new_content = {
        "name": chart_name,
        "content": content,
        "timestamp": now,
        "symbol": symbol,
        "resolution": resolution,
    }
    _filter = {"id": int(chart_id), "owner_source": client_id, "owner_id": user_id}
    result = charts_collection.update_one(_filter, chart_new_content)
    # if not result.matched_count:
    #     raise HTTPException('Chart not found')
    return {"status": "ok"}
