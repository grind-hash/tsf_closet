"""
Memory generation job service

Manages the in-memory job state for the batch memory-generation flow:
1. Sequentially (re)generate PlaySummary (title/summary/timeline) for the
   selected recent sessions.
2. Feed the resulting summaries into an LLM to extract the user's
   preferences/kinks as free-form memory text, then persist it.

Jobs are tracked in an in-memory dict only (process-local, matches the
existing in-memory SessionStore pattern). Jobs do not survive a restart.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import desc, select

from .litellm_client import LiteLLMClientError
from .llm_service import LLMServiceError, llm_service
from .memory_prompts import (
    build_memory_generation_user_prompt,
    build_memory_merge_user_prompt,
    chunk_summaries,
    get_memory_generation_system_prompt,
    get_memory_merge_system_prompt,
)
from .settings_service import settings_service
from .summary_service import summary_service
from ..databases.base import async_session_factory
from ..databases.models import Session as SessionORM

logger = logging.getLogger(__name__)

RETRY_WAIT_SECONDS = 5.0


@dataclass
class MemoryJobState:
    """メモリ生成ジョブの状態"""

    job_id: str
    total: int
    regenerate_existing: bool
    language: str
    status: str = "running"  # running/completed/completed_with_errors/failed/cancelled
    # summarizing(要約・称号生成中) / analyzing(メモリチャンク分析中) /
    # merging(チャンク結果統合中) / done(完了)
    phase: str = "summarizing"
    processed: int = 0
    current_session_id: str | None = None
    memory_chunk_total: int = 0
    memory_chunk_processed: int = 0
    errors: list[str] = field(default_factory=list)
    cancel_requested: bool = False
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "phase": self.phase,
            "total": self.total,
            "processed": self.processed,
            "current_session_id": self.current_session_id,
            "memory_chunk_total": self.memory_chunk_total,
            "memory_chunk_processed": self.memory_chunk_processed,
            "errors": self.errors,
            "regenerate_existing": self.regenerate_existing,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


class MemoryJobService:
    """メモリ生成バッチジョブを管理するサービス"""

    def __init__(self) -> None:
        self._jobs: dict[str, MemoryJobState] = {}

    async def get_recent_session_ids(self, session_limit: int | None) -> list[str]:
        """更新日時の新しい順にセッションIDを取得する。

        Args:
            session_limit: 取得件数の上限。Noneの場合は全件。

        Returns:
            セッションIDのリスト（新しい順）
        """
        async with async_session_factory() as db_session:
            stmt = select(SessionORM.id).order_by(desc(SessionORM.updated_at))
            if session_limit is not None:
                stmt = stmt.limit(session_limit)
            rows = (await db_session.execute(stmt)).scalars().all()
            return [str(row) for row in rows]

    def start_generation_job(
        self,
        session_limit: int | None,
        regenerate_existing: bool,
        analysis_prompt: str | None = None,
        language: str = "ja",
    ) -> str:
        """メモリ生成バッチジョブを開始し、job_idを即座に返す。

        実処理はバックグラウンドタスクとして非同期に実行される。
        """
        job_id = str(uuid.uuid4())
        job = MemoryJobState(
            job_id=job_id,
            total=0,
            regenerate_existing=regenerate_existing,
            language=language,
        )
        self._jobs[job_id] = job
        asyncio.create_task(
            self._run_job(
                job_id,
                session_limit,
                regenerate_existing,
                analysis_prompt,
                language,
            )
        )
        return job_id

    def get_job_status(self, job_id: str) -> dict | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        return job.to_dict()

    def request_cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        job.cancel_requested = True
        return True

    async def _run_job(
        self,
        job_id: str,
        session_limit: int | None,
        regenerate_existing: bool,
        analysis_prompt: str | None,
        language: str,
    ) -> None:
        job = self._jobs[job_id]
        try:
            user_settings = await settings_service.get_user_settings()
            effective_novelai_text_model: str | None = user_settings.get(
                "novelai_text_model"
            )
            session_ids = await self.get_recent_session_ids(session_limit)
            job.total = len(session_ids)

            for session_id in session_ids:
                if job.cancel_requested:
                    job.status = "cancelled"
                    break

                job.current_session_id = session_id
                try:
                    await self._maybe_generate_summary(
                        session_id,
                        regenerate_existing,
                        language,
                        effective_novelai_text_model,
                    )
                except Exception as exc:  # noqa: BLE001 - 1セッション失敗でもバッチ継続
                    logger.warning(
                        "Summary generation failed for session %s: %s",
                        session_id,
                        exc,
                    )
                    job.errors.append(f"{session_id}: {exc}")
                job.processed += 1

            if job.status != "cancelled":
                summaries = await self._collect_summaries(session_ids)
                if summaries:
                    try:
                        await self._generate_and_save_memory_text(
                            job,
                            summaries,
                            analysis_prompt,
                            language,
                            effective_novelai_text_model,
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.error("Memory text generation failed: %s", exc)
                        job.errors.append(f"memory_text: {exc}")
                        job.status = "failed"
                if job.status == "running":
                    job.phase = "done"
                    job.status = "completed_with_errors" if job.errors else "completed"
        except Exception as exc:  # noqa: BLE001 - ジョブ全体の予期しない失敗
            logger.exception("Memory generation job %s failed", job_id)
            job.status = "failed"
            job.errors.append(str(exc))
        finally:
            job.current_session_id = None
            job.finished_at = datetime.utcnow()

    async def _maybe_generate_summary(
        self,
        session_id: str,
        regenerate_existing: bool,
        language: str,
        novelai_model_override: str | None,
    ) -> None:
        if not regenerate_existing:
            existing = await summary_service.get_summary(session_id)
            if existing is not None:
                return
        await self._generate_summary_with_retry(
            session_id,
            language,
            novelai_model_override,
        )

    async def _generate_summary_with_retry(
        self,
        session_id: str,
        language: str,
        novelai_model_override: str | None,
    ) -> None:
        try:
            await summary_service.generate_summary(
                session_id,
                language,
                novelai_model_override=novelai_model_override,
            )
        except (LLMServiceError, LiteLLMClientError) as exc:
            if "429" not in str(exc):
                raise
            logger.warning(
                "429 detected for session %s, retrying once after %ss",
                session_id,
                RETRY_WAIT_SECONDS,
            )
            await asyncio.sleep(RETRY_WAIT_SECONDS)
            await summary_service.generate_summary(
                session_id,
                language,
                novelai_model_override=novelai_model_override,
            )

    async def _collect_summaries(self, session_ids: list[str]) -> list[dict]:
        summaries: list[dict] = []
        for session_id in session_ids:
            summary = await summary_service.get_summary(session_id)
            if summary is not None:
                summaries.append(summary)
        return summaries

    async def _generate_and_save_memory_text(
        self,
        job: MemoryJobState,
        summaries: list[dict],
        analysis_prompt: str | None,
        language: str,
        novelai_model_override: str | None,
    ) -> None:
        """要約リストからメモリテキストを生成して保存する。

        セッション数が多い場合、全要約を一度に1回のLLMリクエストに含めると
        ユーザープロンプトが肥大化し、NovelAI等のAPIで400エラーになるため、
        chunk_summaries で複数チャンクに分割して順次分析（多重度1）し、
        チャンクが複数あれば最後に1回だけ統合（マージ）リクエストを行う。
        進捗可視化のため、job.phase / memory_chunk_total / memory_chunk_processed を
        逆登しながら更新する。
        """
        chunks = chunk_summaries(summaries)
        job.memory_chunk_total = len(chunks)
        job.memory_chunk_processed = 0
        job.phase = "analyzing"
        logger.info(
            "Memory generation: %d summaries split into %d chunk(s)",
            len(summaries),
            len(chunks),
        )

        partial_texts: list[str] = []
        for chunk in chunks:
            if job.cancel_requested:
                job.status = "cancelled"
                return
            system_prompt = self._build_memory_analysis_system_prompt(
                get_memory_generation_system_prompt(language),
                analysis_prompt,
                language,
            )
            user_prompt = build_memory_generation_user_prompt(chunk, language)
            partial_texts.append(
                await self._generate_text_with_retry(
                    system_prompt,
                    user_prompt,
                    novelai_model_override,
                )
            )
            job.memory_chunk_processed += 1

        if len(partial_texts) == 1:
            memory_text = partial_texts[0]
        else:
            job.phase = "merging"
            merge_system_prompt = self._build_memory_analysis_system_prompt(
                get_memory_merge_system_prompt(language),
                analysis_prompt,
                language,
            )
            merge_user_prompt = build_memory_merge_user_prompt(partial_texts, language)
            memory_text = await self._generate_text_with_retry(
                merge_system_prompt,
                merge_user_prompt,
                novelai_model_override,
            )

        await settings_service.save_memory_text(memory_text)
        logger.info(
            "Memory text generated from %d summaries across %d chunk(s)",
            len(summaries),
            len(chunks),
        )

    def _build_memory_analysis_system_prompt(
        self,
        base_prompt: str,
        analysis_prompt: str | None,
        language: str,
    ) -> str:
        """自由入力の分析指示を既定のメモリ分析プロンプトへ追加する。"""
        if not analysis_prompt or not analysis_prompt.strip():
            return base_prompt

        cleaned_prompt = analysis_prompt.strip()
        if language == "en":
            return (
                f"{base_prompt}\n\n"
                "Additional user instruction for this analysis:\n"
                f"{cleaned_prompt}"
            )
        return f"{base_prompt}\n\n追加の分析指示:\n{cleaned_prompt}"

    async def _generate_text_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        novelai_model_override: str | None,
    ) -> str:
        """429検出時に1回だけリトライするLLMテキスト生成の共通ヘルパー。"""
        try:
            result = await llm_service.generate_text(
                system_prompt,
                user_prompt,
                novelai_model_override=novelai_model_override,
            )
            return result.content.strip()
        except (LLMServiceError, LiteLLMClientError) as exc:
            if "429" not in str(exc):
                raise
            logger.warning(
                "429 detected during memory text generation, retrying once after %ss",
                RETRY_WAIT_SECONDS,
            )
            await asyncio.sleep(RETRY_WAIT_SECONDS)
            result = await llm_service.generate_text(
                system_prompt,
                user_prompt,
                novelai_model_override=novelai_model_override,
            )
            return result.content.strip()


memory_job_service = MemoryJobService()
