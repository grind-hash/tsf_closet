import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from gateway.databases.base import Base
from gateway.services.achievement_service import AchievementService
from gateway.services.settings_service import SettingsService


def test_achievement_service_updates_and_reads_counts(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "achievement_service_test.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine)
    test_sync_session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    module = sys.modules["gateway.services.achievement_service"]
    monkeypatch.setattr(module, "sync_session_factory", test_sync_session_factory)

    service = AchievementService()
    service.update_achievement_counts(["CROSS_DRESS", "REALITY_ALTER"])

    crossdress_count, gender_change_count, reality_alter_count = (
        service.get_achievement_counts()
    )
    assert crossdress_count == 1
    assert gender_change_count == 0
    assert reality_alter_count == 1
    engine.dispose()


@pytest.mark.asyncio
async def test_settings_service_uses_orm_for_user_settings(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "settings_service_test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        test_session_factory = async_sessionmaker(engine, expire_on_commit=False)
        module = sys.modules["gateway.services.settings_service"]
        monkeypatch.setattr(module, "async_session_factory", test_session_factory)

        service = SettingsService()

        settings = await service.get_user_settings("orm-test-user")
        assert settings["nsfw_mode"] is False
        assert settings["difficulty"] == "normal"
        assert settings["language"] == "ja"
        assert settings["bloom_calc_method"] == "legacy"

        updated = await service.update_user_settings(
            user_id="orm-test-user",
            nsfw_mode=True,
            difficulty="hard",
            language="EN",
        )
        assert updated["nsfw_mode"] is True
        assert updated["difficulty"] == "hard"
        assert updated["language"] == "en"
        assert updated["bloom_calc_method"] == "legacy"

        stored = await service.get_user_settings("orm-test-user")
        assert stored["nsfw_mode"] is True
        assert stored["difficulty"] == "hard"
        assert stored["language"] == "en"
        assert stored["bloom_calc_method"] == "legacy"

        method_updated = await service.update_user_settings(
            user_id="orm-test-user",
            bloom_calc_method="new",
        )
        assert method_updated["bloom_calc_method"] == "new"
    finally:
        await engine.dispose()
