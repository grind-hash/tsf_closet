"""Tests for history_lookback_count settings (spec 004 T025, US4)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from gateway.routes.settings_router import SettingsModel, SettingsUpdateRequest


def test_settings_model_default_history_lookback_count_is_10():
    model = SettingsModel()
    assert model.history_lookback_count == 10


def test_settings_model_accepts_boundary_values():
    assert SettingsModel(history_lookback_count=5).history_lookback_count == 5
    assert SettingsModel(history_lookback_count=20).history_lookback_count == 20


@pytest.mark.parametrize("invalid", [0, 4, 21, 100, -1])
def test_settings_model_rejects_out_of_range(invalid):
    with pytest.raises(ValidationError):
        SettingsModel(history_lookback_count=invalid)


def test_settings_update_request_accepts_none_and_valid():
    assert SettingsUpdateRequest().history_lookback_count is None
    assert SettingsUpdateRequest(history_lookback_count=15).history_lookback_count == 15


@pytest.mark.parametrize("invalid", [4, 21])
def test_settings_update_request_rejects_out_of_range(invalid):
    with pytest.raises(ValidationError):
        SettingsUpdateRequest(history_lookback_count=invalid)
