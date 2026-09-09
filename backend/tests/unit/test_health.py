from fastapi.testclient import TestClient

from app.main import app


def test_liveness_does_not_require_dependencies() -> None:
    response = TestClient(app).get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
