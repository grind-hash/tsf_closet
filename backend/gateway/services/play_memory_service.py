"""セッション単位のプレイメモ生成とプロンプト注入を管理する。"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from .session import session_store

logger = logging.getLogger(__name__)


class PlayMemoryService:
    """プレイメモのローリング更新と再生成を行う。"""

    def __init__(self) -> None:
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._generation_lock = asyncio.Lock()

    async def build_context(
        self,
        session_id: str,
        *,
        enabled: bool,
        preference_text: str | None = None,
        language: str = "ja",
    ) -> str:
        """有効なメモを優先順位付きの参照文脈へ変換する。"""
        if not enabled:
            return ""
        memory = await session_store.get_play_memory(session_id)
        if memory is None:
            return ""

        sections: list[str] = []
        if memory.user_enabled and memory.user_text and memory.user_text.strip():
            label = "User play memo" if language == "en" else "ユーザーメモ"
            sections.append(f"[{label}]\n{memory.user_text.strip()}")
        if memory.system_enabled and memory.system_text and memory.system_text.strip():
            label = "Automatic play memo" if language == "en" else "自動メモ"
            sections.append(f"[{label}]\n{memory.system_text.strip()}")
        if preference_text and preference_text.strip():
            label = "Preference memory" if language == "en" else "好みメモリ"
            sections.append(f"[{label}]\n{preference_text.strip()}")
        if not sections:
            return ""

        rule = (
            "Use the following as background context. The user's current explicit "
            "instruction always has priority over these notes."
            if language == "en"
            else "以下は背景文脈として参照してください。今回のユーザーの明示指示を常に最優先してください。"
        )
        return f"\n\n{rule}\n\n" + "\n\n".join(sections)

    async def update_rolling(
        self,
        session_id: str,
        *,
        interaction_type: str,
        user_input: str,
        result_text: str,
        language: str = "ja",
    ) -> bool:
        """正常完了した1回のやり取りを自動メモへ反映する。"""
        async with self._locks[session_id]:
            memory = await session_store.get_play_memory(session_id)
            if memory is None or not memory.system_enabled:
                return True
            try:
                generated = await self._generate(
                    previous=memory.system_text or "",
                    interactions=[(interaction_type, user_input, result_text)],
                    language=language,
                )
                await session_store.save_play_memory_system_text(session_id, generated)
                return True
            except Exception:
                logger.exception(
                    "プレイメモのローリング更新に失敗しました: %s", session_id
                )
                return False

    async def regenerate(self, session_id: str, language: str = "ja") -> object:
        """現存する全履歴と会話から自動メモを再生成する。"""
        async with self._locks[session_id]:
            memory = await session_store.get_play_memory(session_id)
            if memory is None:
                raise ValueError("session not found")
            timeline = await session_store.get_session_timeline(session_id, limit=10000)
            if not timeline:
                raise ValueError("no history available")

            previous = ""
            for start in range(0, len(timeline), 30):
                chunk = timeline[start : start + 30]
                interactions = [(kind, text, "") for kind, text in chunk]
                previous = await self._generate(
                    previous=previous,
                    interactions=interactions,
                    language=language,
                )
            saved = await session_store.save_play_memory_system_text(
                session_id, previous
            )
            if saved is None:
                raise ValueError("session not found")
            return saved

    async def _generate(
        self,
        *,
        previous: str,
        interactions: list[tuple[str, str, str]],
        language: str,
    ) -> str:
        """LLMで構造化された自動メモを生成する。"""
        from .llm_service import llm_service

        if language == "en":
            system_prompt = (
                "Update a concise play-session memory. Output plain text with exactly "
                "these headings: History, Current situation, Important continuity. "
                "Preserve established facts, incorporate the new completed interactions, "
                "and never invent details. Keep the result under 2000 characters."
            )
        else:
            system_prompt = (
                "プレイセッションのメモを簡潔に更新してください。出力はプレーンテキストで、"
                "「これまでの経緯」「現在の状況」「継続すべき重要事項」の3見出しを必ず使ってください。"
                "確定済みの事実を維持し、今回完了したやり取りを反映し、存在しない内容を補わないでください。"
                "全体を2000文字以内にしてください。"
            )
        lines = [f"Previous memory:\n{previous or '(none)'}", "Completed interactions:"]
        for kind, user_input, result_text in interactions:
            lines.append(
                f"- type={kind}\n  user={user_input}\n  result={result_text or '(not provided)'}"
            )
        async with self._generation_lock:
            result = await llm_service.generate_text(system_prompt, "\n".join(lines))
        text = result.content.strip()
        if not text:
            raise ValueError("empty play memory response")
        return text[:2000]


play_memory_service = PlayMemoryService()
