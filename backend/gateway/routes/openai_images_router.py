"""OpenAI互換 Images API（/v1/images/edits, /v1/images/variations）。

ComfyUI をバックエンドに使う。従来どおり /api 配下ではなくルート直下に公開する。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from ..services.comfy import ComfyUIClient
from ..services.openai_image_form import process_image_form
from ..settings.app_settings import Settings, settings

router = APIRouter(tags=["openai-images"])


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


@router.post("/v1/images/edits")
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

    return await process_image_form(form, client=client, cfg=cfg)


@router.post("/v1/images/variations")
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

    return await process_image_form(form, client=client, cfg=cfg, force_mask_none=True)
