"""
Memory API endpoints

Provides the batch memory-generation job control (start/status/cancel)
and the memory text CRUD (get/save) used by the settings panel.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from ..schemas.memory import (
    MemoryCancelResponse,
    MemoryGenerateRequest,
    MemoryGenerateResponse,
    MemoryJobStatusResponse,
    MemoryTextResponse,
    MemoryTextSaveRequest,
)
from ..services.memory_job_service import memory_job_service
from ..services.settings_service import settings_service

router = APIRouter(prefix="/memory", tags=["memory"])


@router.post("/generate", response_model=MemoryGenerateResponse)
async def generate_memory(request: MemoryGenerateRequest) -> MemoryGenerateResponse:
    """メモリ生成バッチジョブを開始する。"""
    job_id = memory_job_service.start_generation_job(
        session_limit=request.session_limit,
        regenerate_existing=request.regenerate_existing,
        language=request.language,
    )
    return MemoryGenerateResponse(job_id=job_id)


@router.get("/generate/status/{job_id}", response_model=MemoryJobStatusResponse)
async def get_generate_status(job_id: str) -> MemoryJobStatusResponse:
    """メモリ生成バッチジョブの進捗を取得する。"""
    status = memory_job_service.get_job_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return MemoryJobStatusResponse(**status)


@router.get("/generate/export/{job_id}", response_class=Response)
async def download_generate_analysis(job_id: str) -> Response:
    """LLMへ送信したチャンク別プロンプトと結果をMarkdownで返す。"""
    if memory_job_service.get_job_status(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")

    export = memory_job_service.get_job_analysis_export(job_id)
    if export is None:
        raise HTTPException(status_code=409, detail="Analysis data is not ready")

    content, filename = export
    return Response(
        content=content,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/generate/cancel/{job_id}", response_model=MemoryCancelResponse)
async def cancel_generate(job_id: str) -> MemoryCancelResponse:
    """メモリ生成バッチジョブのキャンセルを要求する。"""
    success = memory_job_service.request_cancel(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found")
    return MemoryCancelResponse(success=success)


@router.get("/text", response_model=MemoryTextResponse)
async def get_memory_text() -> MemoryTextResponse:
    """保存済みのメモリテキストを取得する。"""
    memory_text = await settings_service.get_memory_text()
    return MemoryTextResponse(memory_text=memory_text)


@router.put("/text", response_model=MemoryTextResponse)
async def save_memory_text(request: MemoryTextSaveRequest) -> MemoryTextResponse:
    """メモリテキストを保存する（ユーザーによる手動編集を含む）。"""
    saved = await settings_service.save_memory_text(request.memory_text)
    return MemoryTextResponse(memory_text=saved)
