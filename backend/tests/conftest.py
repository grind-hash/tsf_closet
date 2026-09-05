"""テスト共通フィクスチャ。

DB を使うテストは ``isolated_db`` で一時ファイル上の SQLite に差し替え、
開発者の実 DB (data/database.sqlite) に触れないようにする。
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from gateway.databases import base as db_base


def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
    # 本番の engine (gateway.databases.base) と同じく外部キー制約を有効にする
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _patch_everywhere(
    monkeypatch: pytest.MonkeyPatch, attr: str, original: object, replacement: object
) -> int:
    """import 済みの gateway.* モジュールで ``original`` を指す属性を置き換える。

    session factory は ``from ..databases.base import async_session_factory`` の形で
    各モジュールへコピーされているため、base だけ差し替えても他のモジュールには
    届かない。テスト開始時点で読み込まれているモジュールをすべて走査する。
    """
    count = 0
    for name, module in list(sys.modules.items()):
        if module is None or not name.startswith("gateway"):
            continue
        if getattr(module, attr, None) is original:
            monkeypatch.setattr(module, attr, replacement)
            count += 1
    return count


@dataclass(frozen=True)
class IsolatedDatabase:
    """``isolated_db`` が返す一時 DB のハンドル。"""

    path: Path
    engine: AsyncEngine
    async_factory: async_sessionmaker
    sync_engine: Engine
    sync_factory: sessionmaker


@pytest.fixture
def isolated_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[IsolatedDatabase]:
    """全テーブルを作成した一時 SQLite を用意し、gateway 全体の session factory を向ける。

    async engine は NullPool にして接続を保持しないため、同期フィクスチャのまま
    後始末できる。
    """
    db_path = tmp_path / "test.sqlite"

    sync_engine = create_engine(f"sqlite:///{db_path}", future=True)
    event.listen(sync_engine, "connect", _enable_foreign_keys)
    db_base.Base.metadata.create_all(sync_engine)
    sync_factory = sessionmaker(bind=sync_engine, expire_on_commit=False)

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}", future=True, poolclass=NullPool
    )
    event.listen(engine.sync_engine, "connect", _enable_foreign_keys)
    async_factory = async_sessionmaker(engine, expire_on_commit=False)

    _patch_everywhere(
        monkeypatch,
        "async_session_factory",
        db_base.async_session_factory,
        async_factory,
    )
    _patch_everywhere(
        monkeypatch, "sync_session_factory", db_base.sync_session_factory, sync_factory
    )

    yield IsolatedDatabase(
        path=db_path,
        engine=engine,
        async_factory=async_factory,
        sync_engine=sync_engine,
        sync_factory=sync_factory,
    )
    sync_engine.dispose()
