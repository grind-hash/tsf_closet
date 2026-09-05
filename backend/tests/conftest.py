"""テスト共通フィクスチャ。

実 DB (data/database.sqlite) に触れないよう、DB を使うテストはここのフィクスチャで
一時ファイル上の SQLite に差し替える。
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from gateway.databases.base import Base

_achievement_service_module = importlib.import_module(
    "gateway.services.achievement_service"
)


@pytest.fixture
def isolated_achievement_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[sessionmaker]:
    """achievement_service の同期セッションを一時 SQLite に向ける。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'achievements.db'}", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(_achievement_service_module, "sync_session_factory", factory)
    yield factory
    engine.dispose()
