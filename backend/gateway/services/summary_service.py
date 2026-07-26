"""
Summary generation service

Generates play session summaries and titles using LLM.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import select, delete

from ..databases.base import async_session_factory
from ..databases.models import PlaySummary as PlaySummaryORM
from .session import session_store
from .summary_prompts import (
    build_branch_situation_user_prompt,
    build_summary_user_prompt,
    get_branch_situation_system_prompt,
    get_summary_system_prompt,
)

logger = logging.getLogger(__name__)


class SummaryService:
    """Service for generating and managing play summaries."""

    async def get_summary(self, session_id: str) -> dict | None:
        """Get existing summary for a session."""
        async with async_session_factory() as db_session:
            stmt = select(PlaySummaryORM).where(PlaySummaryORM.session_id == session_id)
            row = (await db_session.execute(stmt)).scalars().first()
            if row is None:
                return None

            timeline = []
            if row.timeline_json:
                try:
                    timeline = json.loads(row.timeline_json)
                except (json.JSONDecodeError, TypeError):
                    timeline = []

            return {
                "session_id": session_id,
                "title": row.title,
                "summary": row.summary,
                "timeline": timeline,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }

    async def generate_summary(
        self,
        session_id: str,
        language: str = "ja",
    ) -> dict:
        """Generate a new summary for a session using LLM.

        Fetches the session timeline, calls LLM, parses result,
        and persists to the play_summaries table.
        """
        # Lazy import to avoid circular dependency
        from .llm_service import llm_service

        # Get timeline data
        timeline_data = await session_store.get_session_timeline(session_id, limit=30)
        if not timeline_data:
            raise ValueError(f"No timeline data found for session {session_id}")

        # Build prompts
        system_prompt = get_summary_system_prompt(language)
        user_prompt = build_summary_user_prompt(timeline_data, language)

        logger.info(
            "Generating summary for session %s (%d actions)",
            session_id,
            len(timeline_data),
        )

        # Call LLM
        result = await llm_service.generate_text(system_prompt, user_prompt)
        raw_content = result.content.strip()

        # Parse JSON from LLM response
        title, summary, timeline = self._parse_summary_response(raw_content)

        # Persist to database
        now = datetime.now()
        async with async_session_factory() as db_session:
            # Delete existing summary if any (upsert)
            await db_session.execute(
                delete(PlaySummaryORM).where(PlaySummaryORM.session_id == session_id)
            )
            orm_obj = PlaySummaryORM(
                session_id=session_id,
                title=title,
                summary=summary,
                timeline_json=json.dumps(timeline, ensure_ascii=False),
                created_at=now,
                updated_at=now,
            )
            db_session.add(orm_obj)
            await db_session.commit()

        logger.info(
            "Summary generated for session %s: title=%s",
            session_id,
            title,
        )

        return {
            "session_id": session_id,
            "title": title,
            "summary": summary,
            "timeline": timeline,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

    def _parse_summary_response(self, raw: str) -> tuple[str, str, list[dict]]:
        """Parse LLM response to extract title, summary, and timeline.

        Handles cases where LLM wraps JSON in markdown code blocks.
        """
        content = raw.strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first line (```json or ```) and last line (```)
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            content = "\n".join(lines).strip()

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Failed to parse summary JSON: %s", content[:200])
            return ("Untitled", content[:200], [])

        title = str(data.get("title", "Untitled"))
        summary = str(data.get("summary", ""))
        timeline_raw = data.get("timeline", [])

        # Validate and normalize timeline entries
        timeline = []
        for entry in timeline_raw[:20]:
            if isinstance(entry, dict) and "label" in entry:
                timeline.append(
                    {
                        "label": str(entry["label"]),
                        "type": str(entry.get("type", "dress_up")),
                    }
                )

        return title, summary, timeline

    async def generate_branch_situation_summary(
        self,
        timeline: list[tuple[str, str]],
        appearance_description: str | None = None,
        language: str = "ja",
        fallback_instruction: str | None = None,
    ) -> str:
        """Generate a situation summary for branching a new session.

        Does not persist to play_summaries. On LLM failure, returns a short
        fallback string so session creation can continue.
        """
        from .llm_service import llm_service

        system_prompt = get_branch_situation_system_prompt(language)
        user_prompt = build_branch_situation_user_prompt(
            timeline,
            appearance_description=appearance_description,
            language=language,
        )

        try:
            result = await llm_service.generate_text(system_prompt, user_prompt)
            text = (result.content or "").strip()
            # Strip accidental code fences / quotes
            if text.startswith("```"):
                lines = text.split("\n")
                if lines[-1].strip() == "```":
                    lines = lines[1:-1]
                else:
                    lines = lines[1:]
                text = "\n".join(lines).strip()
            if len(text) > 400:
                text = text[:400].rstrip() + "…"
            if text:
                return text
        except Exception as exc:
            logger.warning("Branch situation summary generation failed: %s", exc)

        base = (fallback_instruction or "").strip()
        if base and base not in ("初期状態", "(初期状態)"):
            short = base if len(base) <= 120 else base[:120].rstrip() + "…"
            if language == "en":
                return f"Continuing from: {short}"
            return f"この状態から再開: {short}"
        if language == "en":
            return "Continuing from the selected image state."
        return "選択した画像の状態から再開する。"


summary_service = SummaryService()
