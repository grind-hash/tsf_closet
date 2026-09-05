"""NovelAI の補助 API プロキシ（/novelai/subscription, /novelai/suggest-tags）。

認証はサーバー側の NOVELAI_API_KEY で行う。従来どおり /api 配下ではなくルート直下に公開する。"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from ..services.anlas_service import parse_novelai_usage
from ..services.http_client import async_client
from ..settings.app_settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["novelai"])


@router.get("/novelai/subscription")
async def get_novelai_subscription() -> dict[str, Any]:
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
            - usage: Optional[dict] V5 利用上限 {percent, is_negative,
              time_until_next_percent}（レスポンスに usage が無い場合は None）

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
        async with async_client(timeout=10.0) as client:
            response = await client.get(
                "https://image.novelai.net/user/subscription",
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

            # tier, active, expiresAt, usageはトップレベルにある
            usage = parse_novelai_usage(data)
            return {
                "tier": data.get("tier", 0),
                "active": data.get("active", False),
                "expires_at": data.get("expiresAt"),
                "usage": {
                    "percent": usage.percent,
                    "is_negative": usage.is_negative,
                    "time_until_next_percent": usage.time_until_next_percent,
                }
                if usage
                else None,
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


@router.get("/novelai/suggest-tags")
async def suggest_tags(
    prompt: str,
    model: str = "nai-diffusion-4-5-full",
    lang: str = "jp",
) -> dict[str, Any]:
    """NovelAIタグ候補検索 (T004-T005)

    NovelAI suggest-tags APIをプロキシして、プロンプト入力補助用のタグ候補を返す。
    認証はサーバーサイドで行う (NOVELAI_API_KEY環境変数)。

    Args:
        prompt: 検索クエリ（日本語またはアルファベット）1-500文字
        model: NovelAIモデル名 (デフォルト: nai-diffusion-4-5-full)
        lang: 言語コード (デフォルト: jp)

    Returns:
        Dict[str, Any]: タグ候補レスポンス
            - tags: list[{tag, count}] タグ候補リスト
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
        async with async_client(timeout=10.0) as client:
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
            elif isinstance(data, dict) and "tags" in data:
                for item in data["tags"]:
                    if isinstance(item, dict):
                        tag_name = (
                            item.get("en_tag")
                            or item.get("jp_tag")
                            or item.get("tag")
                            or item.get("name", "")
                        )
                        count = (
                            item.get("power") or item.get("count") or item.get("score")
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
