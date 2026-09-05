"""履歴画像・情景画像の配信（/api/history/images, /api/history/surroundings）。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..settings.app_settings import settings

router = APIRouter(prefix="/history", tags=["history"])


# 履歴画像配信エンドポイント
@router.get("/images/{history_id}")
async def get_history_image(history_id: str):
    """履歴画像を取得

    Args:
        history_id: 履歴ID

    Returns:
        画像ファイル
    """
    from ..services.session import session_store

    history = await session_store.get_history_by_id(history_id)
    if history is None:
        raise HTTPException(status_code=404, detail="History not found")

    image_path = settings.history_images_dir.parent / history.image_path
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image file not found")

    return FileResponse(image_path, media_type="image/png")


# US2: 周囲状況画像配信エンドポイント
@router.get("/surroundings/{history_id}")
async def get_history_surroundings_image(history_id: str):
    """周囲状況画像を取得 (US2)

    Args:
        history_id: 履歴ID

    Returns:
        周囲状況画像ファイル
    """
    from ..services.session import session_store

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
