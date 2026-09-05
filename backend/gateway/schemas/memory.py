"""ユーザーメモ（本文と生成ジョブ）の API モデル。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..consts.language import DEFAULT_LANGUAGE, LanguageCode


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
