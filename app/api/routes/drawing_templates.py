from fastapi import APIRouter, Form, HTTPException, Query

from .tables import Drawing

drawing_collection = Drawing("db.sqlite")

router = APIRouter(prefix="/drawing_templates", tags=["drawing_templates"])


@router.get("/")
def get_templates(
    client_id: str = Query(..., alias="client"),
    user_id: str = Query(..., alias="user"),
    name: str | None = Query(None, alias="name"),
    tool: str | None = Query("", alias="tool"),
):
    if name is None:
        return get_all_templates_list(client_id, user_id, tool)
    else:
        return get_template(client_id, user_id, tool, name)


@router.delete("/")
def delete_templates(
    client_id: str = Query(..., alias="client"),
    user_id: str = Query(..., alias="user"),
    name: str | None = Query(None, alias="name"),
    tool: str | None = Query("", alias="tool"),
):
    if name is None:
        raise HTTPException("Wrong template id")
    else:
        return remove_template(client_id, user_id, tool, name)


@router.post("/")
def set_templates(
    client_id: str = Query(..., alias="client"),
    user_id: str = Query(..., alias="user"),
    name: str = Query(..., alias="name"),
    tool: str | None = Query("", alias="tool"),
    content: str = Form(..., alias="content"),
):
    return create_or_update_template(client_id, user_id, name, tool, content)


def get_all_templates_list(client_id, user_id, tool):
    _filter = {"owner_source": client_id, "owner_id": user_id, "tool": tool}
    result = [item["name"] for item in drawing_collection.find(_filter, ["name"])]
    return {"status": "ok", "data": result}


def get_template(client_id, user_id, tool, name):
    _filter = {
        "owner_source": client_id,
        "owner_id": user_id,
        "tool": tool,
        "name": name,
    }
    found = drawing_collection.find_one(_filter)
    if not found:
        raise HTTPException("StudyTemplate not found")
    return {"status": "ok", "data": {"name": name, "content": found["content"]}}


def remove_template(client_id, user_id, tool, name):
    _filter = {
        "owner_source": client_id,
        "owner_id": user_id,
        "tool": tool,
        "name": name,
    }
    result = drawing_collection.delete_one(_filter)
    # if not result.deleted_count:
    #     raise HTTPException('DrawingTemplate not found')
    return {"status": "ok"}


def create_or_update_template(client_id, user_id, name, tool, content):
    _filter = {
        "owner_source": client_id,
        "owner_id": user_id,
        "name": name,
        "tool": tool,
    }
    drawing_collection.update_one(_filter, {"content": content}, upsert=True)
    return {"status": "ok"}
