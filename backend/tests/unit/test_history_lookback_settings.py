"""履歴遡及件数のユーザー設定（users テーブル保存）のテスト。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from gateway.schemas.settings import UserSettingsResponse, UserSettingsUpdateRequest
from gateway.services.history_context import clamp_history_lookback_count
from gateway.services.settings_service import settings_service


def test_user_settings_response_default_history_lookback_count_is_10():
    response = UserSettingsResponse(nsfw_mode=False, difficulty="normal", language="ja")
    assert response.history_lookback_count == 10


def test_user_settings_update_request_accepts_none_and_boundaries():
    assert UserSettingsUpdateRequest().history_lookback_count is None
    assert (
        UserSettingsUpdateRequest(history_lookback_count=5).history_lookback_count == 5
    )
    assert (
        UserSettingsUpdateRequest(history_lookback_count=20).history_lookback_count
        == 20
    )


@pytest.mark.parametrize("invalid", [0, 4, 21, 100, -1])
def test_user_settings_update_request_rejects_out_of_range(invalid):
    with pytest.raises(ValidationError):
        UserSettingsUpdateRequest(history_lookback_count=invalid)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 10), ("abc", 10), (3, 5), (5, 5), (15, 15), (20, 20), (99, 20)],
)
def test_clamp_history_lookback_count(value, expected):
    assert clamp_history_lookback_count(value) == expected


async def test_history_lookback_count_defaults_to_10_without_user(isolated_db):
    settings = await settings_service.get_user_settings()
    assert settings["history_lookback_count"] == 10


async def test_history_lookback_count_persists_in_users_table(isolated_db):
    updated = await settings_service.update_user_settings(history_lookback_count=15)
    assert updated["history_lookback_count"] == 15

    # 別の DB セッションで読み直しても値が残っている（プロセス内メモリに依存しない）
    reloaded = await settings_service.get_user_settings()
    assert reloaded["history_lookback_count"] == 15

    # 他の設定だけを更新しても件数は据え置き
    await settings_service.update_user_settings(difficulty="hard")
    reloaded = await settings_service.get_user_settings()
    assert reloaded["history_lookback_count"] == 15
    assert reloaded["difficulty"] == "hard"
