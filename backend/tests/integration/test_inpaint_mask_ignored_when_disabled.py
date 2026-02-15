from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from gateway.routes.game_router import router


class StubGameService:
    def __init__(self) -> None:
        self.captured: dict[str, object] = {}

    async def play_with_stream(self, **kwargs):
        self.captured = kwargs
        yield SimpleNamespace(type="done", data={"ok": True})


def test_play_stream_without_mask_sends_no_mask_fields(monkeypatch):
    app = FastAPI()
    app.include_router(router)

    stub_service = StubGameService()
    monkeypatch.setattr("gateway.services.game_service.game_service", stub_service)

    with TestClient(app) as client:
        response = client.post(
            "/game/play/stream",
            json={
                "instruction": "test",
                "session_id": "session-1",
            },
        )

    assert response.status_code == 200
    assert stub_service.captured["mask_image"] is None
    assert stub_service.captured["mask_id"] is None
