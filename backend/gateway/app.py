"""FastAPI アプリケーションの組み立て。

ライフサイクル（DB 初期化と終了）、CORS、各ルーターの登録、SPA 静的配信を行う。
エンドポイントの実装は routes/ に置き、ここには追加しない。"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .databases import close_database, init_database
from .routes import (
    achievements_router,
    adventure_router,
    aivisspeech_router,
    avatar_router,
    character_router,
    favorites_router,
    gallery_router,
    game_router,
    history_router,
    memory_router,
    novelai_router,
    openai_images_router,
    prompt_expander_router,
    settings_router,
    system_router,
)
from .settings.app_settings import configure_logging, settings

# ログ設定を適用
configure_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """アプリケーションのライフサイクル管理

    起動時にデータベースを初期化し、終了時にクローズする。
    """
    # 起動時: データベース初期化
    logger.info("Starting application...")
    await init_database(settings.database_path)
    logger.info("Database initialized")

    yield

    # 終了時: クリーンアップ
    logger.info("Shutting down application...")
    await close_database()
    logger.info("Database connection closed")


app = FastAPI(
    title="ComfyUI x OpenAI Gateway",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS設定 (開発時にポート3000からのリクエストを許可)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静的ファイル配信 (ポータブル配布時に使用)
STATIC_DIR = Path(__file__).parent.parent / "static"


def setup_static_files(application: FastAPI) -> None:
    """静的ファイル配信を設定する（staticディレクトリが存在する場合のみ）

    ポータブル配布パッケージ用。ビルド済みReact SPAを配信する。
    React Routerのクライアントサイドルーティングに対応するため、
    未知のルートでは index.html を返す (SPA fallback)。

    Note: このルートは他のすべてのルートより後に登録する必要がある。
    """
    index_html = STATIC_DIR / "index.html"
    if not index_html.exists():
        return

    # 静的アセット配信 (js, css, images)
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        application.mount(
            "/assets", StaticFiles(directory=str(assets_dir)), name="assets"
        )

    @application.get("/", include_in_schema=False)
    async def serve_index() -> FileResponse:
        """ルートアクセス時にindex.htmlを返す"""
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    @application.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        """SPA fallback - 静的ファイルまたはindex.htmlを返す

        React Routerのクライアントサイドルーティングに対応。
        存在する静的ファイルは直接配信、それ以外はindex.htmlを返す。
        """
        # favicon.ico などのルートレベルファイル
        file_path = STATIC_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)

        # SPA fallback
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")


# ゲームAPIルーターを登録 (prefix="/api"でフロントエンドルートと競合回避)
app.include_router(game_router, prefix="/api")

# 独立アドベンチャーモード
app.include_router(adventure_router, prefix="/api")

# ギャラリーAPIルーターを登録 (007-chat-interactive-ux)
app.include_router(gallery_router, prefix="/api")

# お気に入り衣装スナップショット (spec 009)
app.include_router(favorites_router, prefix="/api")

# 実績APIルーターを登録 (007-chat-interactive-ux)
app.include_router(achievements_router, prefix="/api")

# 設定APIルーターを登録 (007-chat-interactive-ux)
app.include_router(settings_router, prefix="/api")

# マルチキャラ永続化ルーター (spec 005)
app.include_router(character_router, prefix="/api")

# メモリ機能ルーター（要約・称号バッチ生成 + 好み嗜好メモリ）
app.include_router(memory_router, prefix="/api")

# AivisSpeech 連携ルーター
app.include_router(aivisspeech_router, prefix="/api")

# Prompt Expander（実験的機能: 自然言語→NovelAI プロンプト拡張と画像生成）
app.include_router(prompt_expander_router, prefix="/api")

# 3D アバター(VRM)の登録・配信(Adventure 対面会話モードで使用)
app.include_router(avatar_router, prefix="/api")

app.include_router(history_router, prefix="/api")

# 互換・補助 API（従来どおり /api 配下ではないパス）。prefix 無しでそのまま公開する
app.include_router(system_router)
app.include_router(novelai_router)
app.include_router(openai_images_router)


# 静的ファイル配信を最後に登録（catch-all）
# APIルートおよびその他のエンドポイントより後に配置することで、
# API呼び出しが優先され、未マッチのパスのみSPAにフォールバックする
setup_static_files(app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("gateway.app:app", host="0.0.0.0", port=8000, reload=True)
