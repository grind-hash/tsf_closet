"""
OpenAI互換 Images API Gateway for ComfyUI

このモジュールは、ComfyUIをバックエンドとして使用しながら、
OpenAI Images APIと互換性のあるエンドポイントを提供するFastAPIアプリケーションです。

主な機能:
- /v1/images/edits: 画像編集 (マスク付き可能)
- /v1/images/variations: 画像バリエーション生成 (マスク無し)

処理フロー:
1. multipart/form-dataでリクエスト受信
2. 画像・マスク・プロンプトを抽出
3. ComfyUIクライアント経由でワークフロー実行
4. OpenAI互換形式でBase64エンコードした画像を返却
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Optional, Sequence

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import FormData

from .services.comfy import ComfyUIClient, ComfyUIError
from .databases import close_database, init_database
from .routes import (
    achievements_router,
    character_router,
    gallery_router,
    game_router,
    settings_router,
)
from .settings.app_settings import Settings, configure_logging, settings

# ログ設定を適用
configure_logging()

logger = logging.getLogger(__name__)

# OpenAI互換レスポンスで返すモデル名
MODEL_NAME = "qwen-image-edit"

# ComfyUIにアップロード可能な画像タイプ (input/output/temp)
_DEF_PLACEHOLDER_TYPES = {"input", "output", "temp"}


def _is_upload(value: object) -> bool:
    """オブジェクトがアップロードファイルかどうかを判定

    Args:
        value: チェック対象のオブジェクト

    Returns:
        bool: UploadFileインスタンスの場合True
    """
    return hasattr(value, "filename") and hasattr(value, "read")


def _decode_image_payload(value: str) -> bytes:
    """Base64エンコードされた画像データをデコード

    Data URL形式 (data:image/png;base64,xxx) と純粋なBase64文字列の両方に対応。

    Args:
        value: Base64エンコードされた画像文字列

    Returns:
        bytes: デコードされた画像バイナリ

    Raises:
        ValueError: Base64デコードに失敗した場合
    """
    # Data URL形式の場合、カンマ以降のBase64部分を抽出
    if value.startswith("data:"):
        try:
            _, encoded = value.split(",", 1)
        except ValueError as exc:
            raise ValueError("Invalid data URL for image placeholder") from exc
    else:
        encoded = value

    # Base64デコード
    try:
        return base64.b64decode(encoded)
    except binascii.Error as exc:
        raise ValueError(f"Invalid base64 image payload: {exc}") from exc


def _find_upload(
    form: FormData, names: Sequence[str], *, fallback_prefix: str
) -> UploadFile | None:
    """multipart/form-dataから画像ファイルアップロードを探索

    フォームデータから指定された名前のファイルアップロードを検索。
    配列形式のフィールドやプレフィックスマッチングにも対応。

    Args:
        form: FastAPIのFormDataオブジェクト
        names: 検索するフィールド名のリスト (例: ["image", "image[]"])
        fallback_prefix: 名前が見つからない場合のプレフィックスマッチング用

    Returns:
        UploadFile | None: 見つかったファイル、または None
    """
    # 1. 通常のフィールド名で検索
    for name in names:
        value = form.get(name)
        if _is_upload(value):
            return value

    # 2. 配列形式のフィールド (getlistメソッド使用)
    getlist = getattr(form, "getlist", None)
    if callable(getlist):
        for name in names:
            items = getlist(name)
            for item in items:
                if _is_upload(item):
                    return item

    # 3. フォールバック: プレフィックスマッチング
    for key, value in form.multi_items():
        if _is_upload(value) and (key in names or key.startswith(fallback_prefix)):
            return value
    return None


def _collect_nested_form_data(form: FormData) -> Dict[str, Any]:
    """ネストされたフォームデータを辞書形式に変換

    "replacements[key1]" や "image_placeholders[img1][data]" のような
    ブラケット記法を、ネストした辞書構造に変換します。

    例:
        replacements[__SEED__]=12345 → {"replacements": {"__SEED__": "12345"}}

    Args:
        form: FastAPIのFormDataオブジェクト

    Returns:
        Dict[str, Any]: ネストされた辞書構造
    """
    nested: Dict[str, Any] = {}
    for key, value in form.multi_items():
        # ブラケット記法でないフィールドはスキップ
        if "[" not in key:
            continue

        # "replacements[__SEED__]" → ["replacements", "__SEED__"]
        parts = re.findall(r"[^\[\]]+", key)
        if not parts:
            continue

        # ネストした辞書を構築
        current: Dict[str, Any] = nested
        for part in parts[:-1]:
            current = current.setdefault(part, {})  # type: ignore[assignment]
        current[parts[-1]] = value
    return nested


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

# ギャラリーAPIルーターを登録 (007-chat-interactive-ux)
app.include_router(gallery_router, prefix="/api")

# 実績APIルーターを登録 (007-chat-interactive-ux)
app.include_router(achievements_router, prefix="/api")

# 設定APIルーターを登録 (007-chat-interactive-ux)
app.include_router(settings_router, prefix="/api")

# マルチキャラ永続化ルーター (spec 005)
app.include_router(character_router, prefix="/api")


# 履歴画像配信エンドポイント
@app.get("/api/history/images/{history_id}")
async def get_history_image(history_id: str):
    """履歴画像を取得

    Args:
        history_id: 履歴ID

    Returns:
        画像ファイル
    """
    from .services.session import session_store

    history = await session_store.get_history_by_id(history_id)
    if history is None:
        raise HTTPException(status_code=404, detail="History not found")

    image_path = settings.history_images_dir.parent / history.image_path
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image file not found")

    return FileResponse(image_path, media_type="image/png")


# US2: 周囲状況画像配信エンドポイント
@app.get("/api/history/surroundings/{history_id}")
async def get_history_surroundings_image(history_id: str):
    """周囲状況画像を取得 (US2)

    Args:
        history_id: 履歴ID

    Returns:
        周囲状況画像ファイル
    """
    from .services.session import session_store

    history = await session_store.get_history_by_id(history_id)
    if history is None:
        raise HTTPException(status_code=404, detail="History not found")

    if not history.surroundings_image_path:
        raise HTTPException(status_code=404, detail="Surroundings image not found")

    # Resolve relative path (e.g. history_images/surroundings_xxx.png) against data dir
    image_path = settings.history_images_dir.parent / history.surroundings_image_path
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Surroundings image file not found")

    return FileResponse(image_path, media_type="image/png")


def get_settings() -> Settings:
    """FastAPI Dependency: アプリケーション設定を取得"""
    return settings


def get_comfy_client(cfg: Settings = Depends(get_settings)) -> ComfyUIClient:
    """FastAPI Dependency: ComfyUIクライアントインスタンスを生成

    Args:
        cfg: アプリケーション設定 (DI経由)

    Returns:
        ComfyUIClient: ComfyUI通信用クライアント
    """
    return ComfyUIClient(
        base_url=cfg.comfyui_base_url,
        workflow_path=cfg.comfyui_workflow_path,
        client_id=cfg.comfyui_client_id,
        request_timeout=cfg.comfyui_request_timeout,
        poll_interval=cfg.comfyui_poll_interval,
    )


@app.get("/health")
async def health() -> Dict[str, Any]:
    """拡張ヘルスチェックエンドポイント

    サーバーが稼働中かを確認し、外部サービスの接続状況も返却。

    Returns:
        Dict[str, Any]: ヘルスステータスと各サービスの状態
    """
    from .services.litellm_client import litellm_client

    result: Dict[str, Any] = {
        "status": "ok",
        "services": {},
        # プロバイダー情報
        "image_provider": settings.image_provider,
        "image_description_provider": settings.image_description_provider,
        "feeling_provider": settings.feeling_provider,
    }

    # ComfyUI 接続確認 (IMAGE_PROVIDER=selfhost時のみ)
    if settings.image_provider == "selfhost":
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{settings.comfyui_base_url}/system_stats")
                if resp.status_code == 200:
                    result["services"]["comfyui"] = {"status": "ok"}
                else:
                    result["services"]["comfyui"] = {
                        "status": "error",
                        "code": resp.status_code,
                    }
        except Exception as e:
            result["services"]["comfyui"] = {"status": "error", "message": str(e)}
    else:
        result["services"]["comfyui"] = {
            "status": "skipped",
            "reason": f"using {settings.image_provider}",
        }

    # LiteLLM Proxy 接続確認 (selfhost使用時のみ)
    needs_litellm = (
        settings.image_description_provider == "selfhost"
        or settings.feeling_provider == "selfhost"
    )
    if needs_litellm:
        try:
            litellm_status = await litellm_client.health_check()
            result["services"]["litellm"] = litellm_status
        except Exception as e:
            result["services"]["litellm"] = {"status": "error", "message": str(e)}
    else:
        result["services"]["litellm"] = {
            "status": "skipped",
            "reason": "using openrouter",
        }

    # NovelAI チェック（IMAGE_PROVIDER=novelai時）
    if settings.image_provider == "novelai":
        if settings.novelai_api_key:
            result["services"]["novelai"] = {"status": "ok"}
        else:
            result["services"]["novelai"] = {
                "status": "error",
                "message": "NOVELAI_API_KEY is missing",
            }

    # いずれかのサービスがエラーならdegraded (skippedは無視)
    has_error = any(s.get("status") == "error" for s in result["services"].values())
    if has_error:
        result["status"] = "degraded"

    return result


@app.get("/novelai/subscription")
async def get_novelai_subscription() -> Dict[str, Any]:
    """NovelAIサブスクリプション情報を取得

    NovelAI API /user/subscription を呼び出し、
    ユーザーのサブスクリプション情報（tier, active, expires_at）を返却。

    tier値:
    - 0: Free (Paper)
    - 1: Tablet
    - 2: Scroll
    - 3: Opus

    Returns:
        Dict[str, Any]: サブスクリプション情報
            - tier: int (0-3)
            - active: bool
            - expires_at: Optional[str]

    Raises:
        HTTPException:
            - 401: APIキー未設定または認証エラー
            - 503: NovelAI APIへの接続エラー
    """
    if not settings.novelai_api_key:
        raise HTTPException(
            status_code=401,
            detail="NovelAI API key is not configured",
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.novelai.net/user/subscription",
                headers={
                    "Authorization": f"Bearer {settings.novelai_api_key}",
                    "Content-Type": "application/json",
                },
            )

            if response.status_code == 401:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid NovelAI API key",
                )

            response.raise_for_status()
            data = response.json()

            # デバッグ: 生のレスポンスをログ出力
            logger.info(f"NovelAI subscription raw response: {data}")

            # tier, active, expiresAtはトップレベルにある
            return {
                "tier": data.get("tier", 0),
                "active": data.get("active", False),
                "expires_at": data.get("expiresAt"),
            }

    except httpx.TimeoutException as e:
        logger.error(f"NovelAI subscription check timeout: {e}")
        raise HTTPException(
            status_code=503,
            detail="NovelAI API timeout",
        ) from e
    except httpx.HTTPStatusError as e:
        logger.error(f"NovelAI subscription check error: {e.response.status_code}")
        raise HTTPException(
            status_code=503,
            detail=f"NovelAI API error: {e.response.status_code}",
        ) from e
    except Exception as e:
        logger.error(f"NovelAI subscription check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail="Failed to check NovelAI subscription",
        ) from e


@app.get("/novelai/suggest-tags")
async def suggest_tags(
    prompt: str,
    model: str = "nai-diffusion-4-5-full",
    lang: str = "jp",
) -> Dict[str, Any]:
    """NovelAIタグ候補検索 (T004-T005)

    NovelAI suggest-tags APIをプロキシして、プロンプト入力補助用のタグ候補を返す。
    認証はサーバーサイドで行う (NOVELAI_API_KEY環境変数)。

    Args:
        prompt: 検索クエリ（日本語またはアルファベット）1-500文字
        model: NovelAIモデル名 (デフォルト: nai-diffusion-4-5-full)
        lang: 言語コード (デフォルト: jp)

    Returns:
        Dict[str, Any]: タグ候補レスポンス
            - tags: list[TagSuggestion] タグ候補リスト
            - query: str 元のクエリ

    Raises:
        HTTPException:
            - 400: promptが空または無効
            - 401: APIキー未設定
            - 502: NovelAI APIエラー
    """
    # バリデーション
    if not prompt or prompt.strip() == "":
        raise HTTPException(
            status_code=400,
            detail="prompt is required",
        )
    if len(prompt) > 500:
        raise HTTPException(
            status_code=400,
            detail="prompt must be 500 characters or less",
        )

    if not settings.novelai_api_key:
        raise HTTPException(
            status_code=401,
            detail="NovelAI API key not configured",
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://image.novelai.net/ai/generate-image/suggest-tags",
                params={
                    "model": model,
                    "prompt": prompt.strip(),
                    "lang": lang,
                },
                headers={
                    "Authorization": f"Bearer {settings.novelai_api_key}",
                    "Accept": "application/json",
                },
            )

            if response.status_code == 401:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid NovelAI API key",
                )

            if response.status_code != 200:
                logger.error(
                    f"NovelAI suggest-tags error: {response.status_code} - {response.text}"
                )
                raise HTTPException(
                    status_code=502,
                    detail=f"NovelAI API returned error: {response.status_code}",
                )

            data = response.json()
            logger.debug(f"NovelAI suggest-tags raw response: {data}")

            # レスポンス形式を正規化
            # NovelAI APIレスポンス形式:
            # [{ "jp_tag": "日本語名", "en_tag": "english_tag", "power": N }, ...]
            tags = []
            if isinstance(data, list):
                # 配列形式の場合 (NovelAI標準)
                for item in data:
                    if isinstance(item, dict):
                        # NovelAI形式: en_tag を優先、なければ jp_tag
                        tag_name = (
                            item.get("en_tag")
                            or item.get("jp_tag")
                            or item.get("tag")
                            or item.get("name", "")
                        )
                        count = (
                            item.get("power") or item.get("count") or item.get("score")
                        )
                        if tag_name:  # 空のタグは除外
                            tags.append(
                                {
                                    "tag": tag_name,
                                    "count": count,
                                }
                            )
                    elif isinstance(item, str):
                        tags.append({"tag": item, "count": None})
            elif isinstance(data, dict):
                if "tags" in data:
                    for item in data["tags"]:
                        if isinstance(item, dict):
                            tag_name = (
                                item.get("en_tag")
                                or item.get("jp_tag")
                                or item.get("tag")
                                or item.get("name", "")
                            )
                            count = (
                                item.get("power")
                                or item.get("count")
                                or item.get("score")
                            )
                            if tag_name:
                                tags.append(
                                    {
                                        "tag": tag_name,
                                        "count": count,
                                    }
                                )
                        elif isinstance(item, str):
                            tags.append({"tag": item, "count": None})

            return {
                "tags": tags,
                "query": prompt,
            }

    except httpx.TimeoutException as e:
        logger.error(f"NovelAI suggest-tags timeout: {e}")
        raise HTTPException(
            status_code=502,
            detail="NovelAI API timeout",
        ) from e
    except httpx.HTTPStatusError as e:
        logger.error(f"NovelAI suggest-tags HTTP error: {e.response.status_code}")
        raise HTTPException(
            status_code=502,
            detail=f"NovelAI API error: {e.response.status_code}",
        ) from e
    except HTTPException:
        # 既にHTTPExceptionの場合は再スロー
        raise
    except Exception as e:
        logger.error(f"NovelAI suggest-tags failed: {e}")
        raise HTTPException(
            status_code=502,
            detail="Failed to fetch tag suggestions",
        ) from e


async def _process_image_form(
    form: FormData,
    *,
    client: ComfyUIClient,
    cfg: Settings,
    force_mask_none: bool = False,
) -> JSONResponse:
    """画像編集リクエストのメイン処理関数

    multipart/form-dataから画像・マスク・パラメータを抽出し、
    ComfyUIでワークフローを実行してOpenAI互換形式で結果を返却。

    処理フロー:
    1. プロンプト・画像・マスク・生成枚数などの基本パラメータを抽出
    2. ネストされたフォームデータ (replacements, image_placeholders) を解析
    3. extra_body (JSON形式の追加パラメータ) を解析
    4. ComfyUIクライアントで画像編集を実行
    5. Base64エンコードしてOpenAI互換レスポンスを返却

    Args:
        form: multipart/form-dataのパース結果
        client: ComfyUIクライアントインスタンス
        cfg: アプリケーション設定
        force_mask_none: Trueの場合、マスクを強制的に無効化 (variations用)

    Returns:
        JSONResponse: OpenAI互換のレスポンス

    Raises:
        HTTPException: パラメータエラーやComfyUI通信エラー時
    """
    # ========================================
    # 1. 基本パラメータの抽出
    # ========================================

    # プロンプト (テキスト)
    prompt_value = form.get("prompt")
    if prompt_value is not None and not isinstance(prompt_value, str):
        raise HTTPException(status_code=400, detail="prompt must be a text field")
    prompt: Optional[str] = prompt_value

    # ネストされたフォームデータを収集 (replacements[xxx], image_placeholders[xxx] など)
    nested_fields = _collect_nested_form_data(form)

    # 画像ファイル (必須)
    image_upload = _find_upload(form, ("image", "image[]"), fallback_prefix="image")
    if image_upload is None:
        available_keys = sorted({key for key, _ in form.multi_items()})
        key_types = {key: type(value).__name__ for key, value in form.multi_items()}
        raise HTTPException(
            status_code=400,
            detail=(
                "Image upload 'image' is required "
                f"(received keys: {available_keys}, types: {key_types})"
            ),
        )

    # マスク画像 (オプション)
    # variations エンドポイントの場合は force_mask_none=True でマスクを強制無視
    raw_mask_upload = _find_upload(form, ("mask", "mask[]"), fallback_prefix="mask")
    mask_upload: Optional[UploadFile] = None
    if raw_mask_upload is not None:
        if force_mask_none:
            await raw_mask_upload.close()
        else:
            mask_upload = raw_mask_upload
    else:
        mask_value = form.get("mask")
        if isinstance(mask_value, UploadFile):
            if force_mask_none:
                await mask_value.close()
            else:
                mask_upload = mask_value
        elif mask_value not in (None, "", b""):
            raise HTTPException(
                status_code=400, detail="mask must be provided as a file upload"
            )

    # 生成枚数 (n) の取得 (デフォルト: 1)
    n_value = form.get("n")
    if isinstance(n_value, UploadFile):
        raise HTTPException(status_code=400, detail="n must be provided as text")
    if n_value in (None, ""):
        n = 1
    else:
        try:
            n = int(str(n_value).strip())
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400, detail="n must be an integer"
            ) from None
    if n < 1:
        raise HTTPException(status_code=400, detail="n must be >= 1")

    # レスポンス形式 (デフォルト: b64_json)
    response_format_value = form.get("response_format")
    if isinstance(response_format_value, UploadFile):
        raise HTTPException(
            status_code=400, detail="response_format must be provided as text"
        )
    if response_format_value in (None, ""):
        response_format = "b64_json"
    else:
        response_format = str(response_format_value).strip()
    if response_format not in {"b64_json", "b64_bytes"}:
        raise HTTPException(
            status_code=400, detail="Only base64 responses are supported"
        )

    # ========================================
    # 2. extra_body (拡張パラメータ) の解析
    # ========================================
    # extra_body: JSON形式の追加パラメータ
    # - workflow: 使用するワークフロー名 ("default", "instruct_game" など)
    # - replacements: ワークフローテンプレート内のプレースホルダー置換用
    # - negative_prompt: ネガティブプロンプト
    # - image_placeholders: 追加画像のBase64データ

    extra_body_value = form.get("extra_body")
    extra_body: Optional[str]
    if isinstance(extra_body_value, UploadFile):
        try:
            extra_body_bytes = await extra_body_value.read()
        except Exception as exc:  # pragma: no cover - defensive
            raise HTTPException(
                status_code=400, detail=f"Could not read extra_body: {exc}"
            ) from exc
        finally:
            await extra_body_value.close()
        extra_body = extra_body_bytes.decode("utf-8")
    elif isinstance(extra_body_value, str):
        extra_body = extra_body_value
    else:
        extra_body = None

    # パラメータを統合するためのリスト
    extra_payloads: list[Dict[str, Any]] = []

    # ネストフィールド (replacements[xxx], image_placeholders[xxx]) を処理
    if nested_fields:
        nested_payload: Dict[str, Any] = {}

        # replacements の処理
        nested_replacements = nested_fields.get("replacements")
        if isinstance(nested_replacements, dict) and nested_replacements:
            nested_payload["replacements"] = {
                str(key): str(value)
                for key, value in nested_replacements.items()
                if value is not None
            }

        # image_placeholders の処理
        nested_image_placeholders = nested_fields.get("image_placeholders")
        if isinstance(nested_image_placeholders, dict) and nested_image_placeholders:
            placeholder_entries: Dict[str, Any] = {}
            for placeholder, raw_value in nested_image_placeholders.items():
                if isinstance(raw_value, dict):
                    data_value = raw_value.get("data")
                    type_value = raw_value.get("type", "input")
                    if data_value is None:
                        continue
                    placeholder_entries[placeholder] = {
                        "data": str(data_value),
                        "type": str(type_value) if type_value is not None else "input",
                    }
                elif raw_value is not None:
                    placeholder_entries[placeholder] = str(raw_value)
            if placeholder_entries:
                nested_payload["image_placeholders"] = placeholder_entries
        nested_negative_prompt = nested_fields.get("negative_prompt")
        if isinstance(nested_negative_prompt, str):
            nested_payload["negative_prompt"] = nested_negative_prompt
        if nested_payload:
            extra_payloads.append(nested_payload)

    if extra_body:
        try:
            extra_payload = json.loads(extra_body)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid extra_body: {exc}"
            ) from exc
        if not isinstance(extra_payload, dict):
            raise HTTPException(
                status_code=400, detail="Invalid extra_body: must be an object"
            )
        extra_payloads.append(extra_payload)

    # ========================================
    # 3. 画像ファイルの読み込み
    # ========================================

    # メイン画像の読み込み
    try:
        image_bytes = await image_upload.read()
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=400, detail=f"Could not read image: {exc}"
        ) from exc
    finally:
        await image_upload.close()

    # マスク画像の読み込み
    mask_bytes: Optional[bytes] = None
    if mask_upload is not None:
        try:
            mask_bytes = await mask_upload.read()
        except Exception as exc:  # pragma: no cover - defensive
            raise HTTPException(
                status_code=400, detail=f"Could not read mask: {exc}"
            ) from exc
        finally:
            await mask_upload.close()

    # ========================================
    # 4. プレースホルダー置換と追加画像の準備
    # ========================================

    replacements: Dict[str, Any] = {}  # ワークフロー内の __PROMPT__ などを置換
    extra_images: Dict[str, Dict[str, Any]] = {}  # 追加画像 (Base64デコード済み)

    # extra_payloads から replacements と image_placeholders を抽出
    for payload in extra_payloads:
        # replacements の処理
        replacements_payload = payload.get("replacements")
        if replacements_payload is not None:
            if not isinstance(replacements_payload, dict):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid extra_body: replacements must be an object",
                )
            for key, value in replacements_payload.items():
                if value is None:
                    continue
                replacements[str(key)] = str(value)

        # negative_prompt の処理
        negative_prompt = payload.get("negative_prompt")
        if negative_prompt is not None:
            if isinstance(negative_prompt, (str, bytes, bytearray)):
                neg_value = (
                    negative_prompt
                    if isinstance(negative_prompt, str)
                    else negative_prompt.decode("utf-8", "ignore")
                )
                replacements["__NEGATIVE_PROMPT__"] = neg_value
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid extra_body: negative_prompt must be a string",
                )

        # image_placeholders の処理
        image_placeholders_payload = payload.get("image_placeholders")
        if image_placeholders_payload is not None:
            if not isinstance(image_placeholders_payload, dict):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid extra_body: image_placeholders must be an object",
                )
            for placeholder, value in image_placeholders_payload.items():
                if isinstance(value, dict):
                    data_value = value.get("data")
                    file_type = value.get("type", "input")
                else:
                    data_value = value
                    file_type = "input"
                if data_value is None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"image placeholder {placeholder} requires data",
                    )
                image_bytes_payload = _decode_image_payload(str(data_value))
                entry = {"bytes": image_bytes_payload}
                file_type_str = str(file_type) if file_type is not None else "input"
                entry["type"] = (
                    file_type_str
                    if file_type_str in _DEF_PLACEHOLDER_TYPES
                    else "input"
                )
                extra_images[placeholder] = entry

    # ネガティブプロンプトのデフォルト値を設定
    replacements.setdefault("__NEGATIVE_PROMPT__", "")

    # ========================================
    # 5. ワークフローの選択
    # ========================================

    workflow_name: Optional[str] = None
    for payload in extra_payloads:
        wf = payload.get("workflow")
        if wf is not None:
            workflow_name = str(wf)
            break

    # workflow パラメータはフォームフィールドからも取得可能
    if workflow_name is None:
        workflow_value = form.get("workflow")
        if isinstance(workflow_value, str) and workflow_value:
            workflow_name = workflow_value.strip()

    # ワークフローパスを取得
    workflow_path = None
    if workflow_name:
        try:
            workflow_path = cfg.get_workflow_path(workflow_name)
            cfg.ensure_workflow_exists(workflow_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # ========================================
    # 6. ComfyUIで画像編集を実行
    # ========================================

    try:
        result = await client.image_edit(
            image_bytes=image_bytes,
            prompt=prompt,
            mask_bytes=mask_bytes,
            replacements=replacements,
            limit=n,
            extra_images=extra_images or None,
            workflow_path=workflow_path,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except ComfyUIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"ComfyUI request failed: {exc}"
        ) from exc

    # ========================================
    # 7. OpenAI互換形式でレスポンスを生成
    # ========================================

    # 指定された枚数分だけ取得
    images = result.images[:n]

    # 画像をBase64エンコード
    data = []
    for image_bytes in images:
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        key = "b64_bytes" if response_format == "b64_bytes" else "b64_json"
        data.append({key: encoded})

    # OpenAI Images API互換レスポンスを構築
    payload = {
        "created": int(time.time()),
        "data": data,
        "model": MODEL_NAME,
        "object": "image.edit",
    }
    return JSONResponse(payload)


@app.post("/v1/images/edits")
async def image_edits(
    request: Request,
    client: ComfyUIClient = Depends(get_comfy_client),
    cfg: Settings = Depends(get_settings),
) -> JSONResponse:
    """OpenAI互換Images API: 画像編集エンドポイント

    画像とプロンプトを受け取り、ComfyUIで編集した画像を返却。
    マスク画像を指定すれば、マスク部分のみ編集可能。

    リクエストパラメータ (multipart/form-data):
        - image: 編集対象の画像 (必須)
        - prompt: 編集指示のテキスト (オプション)
        - mask: マスク画像 (オプション)
        - n: 生成枚数 (デフォルト: 1)
        - response_format: "b64_json" or "b64_bytes" (デフォルト: "b64_json")
        - extra_body: JSON形式の追加パラメータ

    Returns:
        JSONResponse: OpenAI互換の画像編集レスポンス
    """
    try:
        form = await request.form(max_part_size=cfg.multipart_max_part_size)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=400, detail=f"Invalid multipart payload: {exc}"
        ) from exc

    return await _process_image_form(form, client=client, cfg=cfg)


@app.post("/v1/images/variations")
async def image_variations(
    request: Request,
    client: ComfyUIClient = Depends(get_comfy_client),
    cfg: Settings = Depends(get_settings),
) -> JSONResponse:
    """OpenAI互換Images API: 画像バリエーションエンドポイント

    画像のバリエーションを生成。
    内部的には image_edits と同じワークフローを使用するが、
    マスクを強制的に無効化する点が異なる。

    リクエストパラメータ (multipart/form-data):
        - image: 元になる画像 (必須)
        - prompt: バリエーション指示 (オプション)
        - n: 生成枚数 (デフォルト: 1)
        - response_format: "b64_json" or "b64_bytes" (デフォルト: "b64_json")
        - extra_body: JSON形式の追加パラメータ

    注: maskパラメータが指定されても無視されます。

    Returns:
        JSONResponse: OpenAI互換の画像生成レスポンス
    """
    try:
        form = await request.form(max_part_size=cfg.multipart_max_part_size)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=400, detail=f"Invalid multipart payload: {exc}"
        ) from exc

    return await _process_image_form(form, client=client, cfg=cfg, force_mask_none=True)


# 静的ファイル配信を最後に登録（catch-all）
# APIルートおよびその他のエンドポイントより後に配置することで、
# API呼び出しが優先され、未マッチのパスのみSPAにフォールバックする
setup_static_files(app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("gateway.app:app", host="0.0.0.0", port=8000, reload=True)
