from fastapi import APIRouter, Form, HTTPException, Query

from .tables import Study

study_collection = Study("db.sqlite")

router = APIRouter(prefix="/1.1/study_templates", tags=["study_templates"])


@router.get("/")
def get_templates(
    client_id: str = Query(..., alias="client"),
    user_id: str = Query(..., alias="user"),
    template_name: str | None = Query(None, alias="template"),
):
    if user_id == "0":
        raise HTTPException(404, "invalid user id")
    if template_name is None:
        return get_all_templates_list(client_id, user_id)
    else:
        return get_template(client_id, user_id, template_name)


@router.delete("/")
def delete_templates(
    client_id: str = Query(..., alias="client"),
    user_id: str = Query(..., alias="user"),
    template_name: str | None = Query(None, alias="template"),
):
    if user_id == "0":
        raise HTTPException(404, "invalid user id")
    if template_name is None:
        raise HTTPException(404, "Wrong template id")
    else:
        return remove_template(client_id, user_id, template_name)


@router.post("/")
def set_templates(
    client_id: str = Query(..., alias="client"),
    user_id: str = Query(..., alias="user"),
    template_name: str = Form(..., alias="name"),
    content: str = Form(..., alias="content"),
):
    if user_id == "0":
        raise HTTPException(404, "invalid user id")
    return create_or_update_template(client_id, user_id, template_name, content)


def get_all_templates_list(client_id, user_id):
    _filter = {"owner_source": client_id, "owner_id": user_id}
    result = study_collection.find(_filter, ["name"])
    return {"status": "ok", "data": result}


def get_template(client_id, user_id, name):
    _filter = {"owner_source": client_id, "owner_id": user_id, "name": name}
    found = study_collection.find_one(_filter)
    if not found:
        raise HTTPException(404, "StudyTemplate not found")
    return {"status": "ok", "data": {"name": name, "content": found["content"]}}


def remove_template(client_id, user_id, name):
    _filter = {"owner_source": client_id, "owner_id": user_id, "name": name}
    result = study_collection.delete_one(_filter)
    if not result.deleted_count:
        raise HTTPException(404, "StudyTemplate not found")
    return {"status": "ok"}


def create_or_update_template(client_id, user_id, name, content):
    _filter = {"owner_source": client_id, "owner_id": user_id, "name": name}
    study_collection.update_one(_filter, {"content": content}, upsert=True)
    return {"status": "ok"}
