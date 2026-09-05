import pytest

from gateway.services.achievement_service import AchievementService
from gateway.services.settings_service import SettingsService


def test_achievement_service_updates_and_reads_counts(isolated_db):
    # achievement_service.sync_session_factory は isolated_db.sync_factory に差し替え済み
    service = AchievementService()
    service.update_achievement_counts(["CROSS_DRESS", "REALITY_ALTER"])

    crossdress_count, gender_change_count, reality_alter_count = (
        service.get_achievement_counts()
    )
    assert crossdress_count == 1
    assert gender_change_count == 0
    assert reality_alter_count == 1


@pytest.mark.asyncio
async def test_settings_service_uses_orm_for_user_settings(isolated_db):
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
