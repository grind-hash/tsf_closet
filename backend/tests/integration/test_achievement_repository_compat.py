from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.routes.achievements_router import router


def test_achievements_api_works_with_repository_structure():
    app = FastAPI()
    app.include_router(router, prefix="/api")

    with TestClient(app) as client:
        response = client.get("/api/achievements")

    assert response.status_code == 200
    payload = response.json()
    assert "achievements" in payload
    assert "unlocked_count" in payload
