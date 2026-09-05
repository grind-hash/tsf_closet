"""app.py から分離したルーターの配線と、ルート直下の互換 API の基本動作を確認する。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from gateway.app import app
from gateway.routes.openai_images_router import get_comfy_client
from gateway.settings.config import settings

# with を使わず生成し、lifespan（実 DB の初期化）を走らせない
client = TestClient(app)


def _route_paths() -> set[tuple[str, str]]:
    # include_router したルートは遅延展開されるため、OpenAPI スキーマから取る
    return {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }


def test_legacy_root_paths_and_api_prefix_are_preserved() -> None:
    paths = _route_paths()
    expected = {
        ("GET", "/health"),
        ("GET", "/novelai/subscription"),
        ("GET", "/novelai/suggest-tags"),
        ("POST", "/v1/images/edits"),
        ("POST", "/v1/images/variations"),
        ("GET", "/api/history/images/{history_id}"),
        ("GET", "/api/history/surroundings/{history_id}"),
        ("POST", "/api/game/play/stream"),
        ("GET", "/api/adventure/templates"),
    }
    assert expected <= paths
    # 互換 API が誤って /api 配下へ移っていないこと
    assert ("GET", "/api/health") not in paths
    assert ("GET", "/api/novelai/subscription") not in paths


def test_health_reports_providers_without_network(monkeypatch) -> None:
    monkeypatch.setattr(settings, "image_provider", "novelai")
    monkeypatch.setattr(settings, "image_description_provider", "openrouter")
    monkeypatch.setattr(settings, "feeling_provider", "openrouter")
    monkeypatch.setattr(settings, "novelai_api_key", "test-key")

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["image_provider"] == "novelai"
    assert payload["services"]["comfyui"]["status"] == "skipped"
    assert payload["services"]["litellm"]["status"] == "skipped"
    assert payload["services"]["novelai"]["status"] == "ok"


def test_novelai_endpoints_require_api_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "novelai_api_key", "")

    assert client.get("/novelai/subscription").status_code == 401
    assert client.get("/novelai/suggest-tags", params={"prompt": ""}).status_code == 400
    assert (
        client.get(
            "/novelai/suggest-tags", params={"prompt": "silver hair"}
        ).status_code
        == 401
    )


def test_image_edits_requires_image_upload() -> None:
    # ComfyUI クライアントの生成はワークフローテンプレート（git 管理外）を読むため、
    # 依存を差し替えて画像なしのバリデーションだけを確認する
    app.dependency_overrides[get_comfy_client] = lambda: object()
    try:
        response = client.post("/v1/images/edits", data={"prompt": "red dress"})
    finally:
        app.dependency_overrides.pop(get_comfy_client, None)

    assert response.status_code == 400
    assert "Image upload 'image' is required" in response.json()["detail"]


def test_history_image_returns_404_for_unknown_id(isolated_db) -> None:
    assert client.get("/api/history/images/no-such-history").status_code == 404
    assert client.get("/api/history/surroundings/no-such-history").status_code == 404
