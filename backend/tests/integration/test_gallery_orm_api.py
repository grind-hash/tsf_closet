import sys
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gateway.databases.base import Base
from gateway.databases.models import Conversation, History, Session, User
from gateway.routes.gallery_router import router


async def _seed_gallery_data(test_session_factory: async_sessionmaker) -> None:
    now = datetime.now()
    async with test_session_factory() as db_session:
        db_session.add(User(id="gallery-user"))
        db_session.add_all(
            [
                Session(
                    id="gallery-session-1",
                    user_id="gallery-user",
                    character_id="char-1",
                    current_image_path="current.png",
                    transformation_count=2,
                    is_active=True,
                    created_at=now - timedelta(minutes=3),
                    updated_at=now - timedelta(minutes=1),
                ),
                Session(
                    id="gallery-session-2",
                    user_id="gallery-user",
                    character_id="char-2",
                    current_image_path="current2.png",
                    transformation_count=1,
                    is_active=True,
                    created_at=now - timedelta(minutes=5),
                    updated_at=now - timedelta(minutes=4),
                ),
            ]
        )
        db_session.add_all(
            [
                History(
                    id="gallery-history-1",
                    session_id="gallery-session-1",
                    instruction="first",
                    image_path="images/1.png",
                    feeling_text="f1",
                    before_description="b1",
                    after_description="a1",
                    created_at=now - timedelta(minutes=2),
                ),
                History(
                    id="gallery-history-2",
                    session_id="gallery-session-1",
                    instruction="second",
                    image_path="images/2.png",
                    feeling_text="f2",
                    before_description="b2",
                    after_description="a2",
                    created_at=now - timedelta(minutes=1),
                ),
                History(
                    id="gallery-history-3",
                    session_id="gallery-session-2",
                    instruction="plain outfit",
                    image_path="images/3.png",
                    feeling_text="calm",
                    before_description="before",
                    after_description="after",
                    created_at=now - timedelta(minutes=4),
                ),
                Conversation(
                    id="gallery-conv-1",
                    session_id="gallery-session-1",
                    role="user",
                    content="赤いドレスに着替えて",
                    created_at=now - timedelta(minutes=2),
                ),
                Conversation(
                    id="gallery-conv-2",
                    session_id="gallery-session-2",
                    role="assistant",
                    content="普通の会話です",
                    created_at=now - timedelta(minutes=4),
                ),
            ]
        )
        await db_session.commit()


def test_gallery_endpoints_return_expected_shapes(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "gallery_api_test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)

    try:
        import asyncio

        asyncio.run(_setup_database(engine))
        test_session_factory = async_sessionmaker(engine, expire_on_commit=False)
        asyncio.run(_seed_gallery_data(test_session_factory))

        module = sys.modules["gateway.routes.gallery_router"]
        monkeypatch.setattr(module, "async_session_factory", test_session_factory)

        class _StubCharacter:
            def __init__(self, name: str):
                self.name = name

        class _StubCharacterManager:
            def get_by_id(self, character_id: str):
                if character_id == "char-1":
                    return _StubCharacter("Character One")
                if character_id == "char-2":
                    return _StubCharacter("Character Two")
                return None

        monkeypatch.setattr(module, "CharacterManager", lambda: _StubCharacterManager())

        app = FastAPI()
        app.include_router(router, prefix="/api")

        with TestClient(app) as client:
            sessions_response = client.get("/api/gallery/sessions")
            search_response = client.get(
                "/api/gallery/sessions", params={"q": "赤いドレス"}
            )
            empty_search_response = client.get(
                "/api/gallery/sessions", params={"q": "存在しないキーワードxyz"}
            )
            list_response = client.get("/api/gallery")
            detail_response = client.get("/api/gallery/gallery-history-2")

        assert sessions_response.status_code == 200
        sessions_payload = sessions_response.json()
        assert sessions_payload["total"] == 2
        assert len(sessions_payload["sessions"]) == 2
        assert sessions_payload["sessions"][0]["session_id"] == "gallery-session-1"
        assert sessions_payload["sessions"][0]["character_name"] == "Character One"

        assert search_response.status_code == 200
        search_payload = search_response.json()
        assert search_payload["total"] == 1
        assert len(search_payload["sessions"]) == 1
        assert search_payload["sessions"][0]["session_id"] == "gallery-session-1"
        assert search_payload["sessions"][0]["match_snippet"]
        assert "赤いドレス" in search_payload["sessions"][0]["match_snippet"]

        assert empty_search_response.status_code == 200
        empty_payload = empty_search_response.json()
        assert empty_payload["total"] == 0
        assert empty_payload["sessions"] == []

        assert list_response.status_code == 200
        list_payload = list_response.json()
        assert list_payload["total"] == 3
        assert len(list_payload["items"]) == 3
        assert {item["id"] for item in list_payload["items"]} == {
            "gallery-history-1",
            "gallery-history-2",
            "gallery-history-3",
        }

        assert detail_response.status_code == 200
        detail_payload = detail_response.json()
        assert detail_payload["item"]["id"] == "gallery-history-2"
        assert detail_payload["prev_id"] == "gallery-history-1"
        assert detail_payload["next_id"] is None
    finally:
        import asyncio

        asyncio.run(engine.dispose())


async def _setup_database(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
