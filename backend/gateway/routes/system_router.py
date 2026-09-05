"""ヘルスチェック（/health）。プロバイダー設定と外部サービスの接続状況を返す。"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter

from ..services.providers import (
    Provider,
    resolve_image_description_provider,
    resolve_image_provider,
    resolve_text_provider,
)
from ..settings.app_settings import settings

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, Any]:
    """拡張ヘルスチェックエンドポイント

    サーバーが稼働中かを確認し、外部サービスの接続状況も返却。

    Returns:
        Dict[str, Any]: ヘルスステータスと各サービスの状態
    """
    from ..services.litellm_client import litellm_client

    result: dict[str, Any] = {
        "status": "ok",
        "services": {},
        # プロバイダー情報
        "image_provider": settings.image_provider,
        "image_description_provider": settings.image_description_provider,
        "feeling_provider": settings.feeling_provider,
    }

    # ComfyUI 接続確認 (IMAGE_PROVIDER=selfhost時のみ)
    if resolve_image_provider() == Provider.SELFHOST:
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
        resolve_image_description_provider() == Provider.SELFHOST
        or resolve_text_provider() == Provider.SELFHOST
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
    if resolve_image_provider() == Provider.NOVELAI:
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
