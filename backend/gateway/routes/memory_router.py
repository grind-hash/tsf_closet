"""
Memory API endpoints

Provides the batch memory-generation job control (start/status/cancel)
and the memory text CRUD (get/save) used by the settings panel.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..consts.language import DEFAULT_LANGUAGE, LanguageCode
from ..services.memory_job_service import memory_job_service
from ..services.settings_service import settings_service

router = APIRouter(prefix="/memory", tags=["memory"])


class MemoryGenerateRequest(BaseModel):
    session_limit: int | None = Field(
        default=None, description="対象とする直近セッション数（Noneは全件）"
    )
    regenerate_existing: bool = Field(
        default=False, description="生成済みの要約・称号も再生成するか"
    )
    language: LanguageCode = DEFAULT_LANGUAGE


class MemoryGenerateResponse(BaseModel):
    job_id: str


class MemoryJobStatusResponse(BaseModel):
    job_id: str
    status: str
    phase: str
    total: int
    processed: int
    current_session_id: str | None
    memory_chunk_total: int
    memory_chunk_processed: int
    errors: list[str]
    regenerate_existing: bool
    started_at: str
    finished_at: str | None


class MemoryCancelResponse(BaseModel):
    success: bool


class MemoryTextResponse(BaseModel):
    memory_text: str | None


class MemoryTextSaveRequest(BaseModel):
    memory_text: str


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
