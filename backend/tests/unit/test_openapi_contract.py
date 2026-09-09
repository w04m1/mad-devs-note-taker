from app.main import app


def _response_schema(path: str):
    return app.openapi()["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]


def test_tag_list_and_upcoming_openapi_shapes_match_frontend_contract() -> None:
    tags = _response_schema("/api/v1/tags")
    assert tags["type"] == "array"
    assert tags["items"] == {"$ref": "#/components/schemas/TagResponse"}

    upcoming = app.openapi()["components"]["schemas"]["UpcomingResponse"]
    assert set(upcoming["required"]) == {"today", "week", "past", "server_now", "next_transition_at"}
    for group in ("today", "week", "past"):
        assert upcoming["properties"][group] == {"$ref": "#/components/schemas/Page"}
