"""Request mode (依頼モード) for the normal game.

The character asks for the look they want to have: a visible wish and 2-3
hidden preferences. After each dress-up or reality turn the LLM judges the
new look only as a fit category and the ids of the satisfied preferences; the
satisfaction number, which preferences are revealed, and fulfilment are
decided here.

Generation and evaluation take plain character data, so a later salon mode
can reuse them for generated customers.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, field_validator

from ..consts.session_request import (
    REQUEST_EVALUATION_HINT_MAX,
    REQUEST_FIT_SCORES,
    REQUEST_FITS,
    REQUEST_FULFILL_THRESHOLD,
    REQUEST_PREFERENCE_HINT_MAX,
    REQUEST_PREFERENCE_TEXT_MAX,
    REQUEST_PREFERENCES_MAX,
    REQUEST_PREFERENCES_MIN,
    REQUEST_PREFERENCES_SCORE,
    REQUEST_WISH_MAX,
)
from ..models import PersistedSession
from .characters import character_manager
from .cost_tracker import begin_cost_tracking, record_cost
from .custom_sessions import load_custom_session_metadata
from .llm_json import generate_validated
from .llm_service import llm_service
from .session import session_store
from .session_request_prompts import (
    build_request_evaluation_prompt,
    build_request_feeling_context,
    build_request_generation_prompt,
)

logger = logging.getLogger(__name__)


class SessionRequestError(Exception):
    """依頼の作成を受け付けられないときの例外。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _clip(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit].strip()


class _GeneratedPreference(BaseModel):
    text: str
    hint: str = ""

    @field_validator("text", mode="before")
    @classmethod
    def clip_text(cls, value: Any) -> str:
        return _clip(value, REQUEST_PREFERENCE_TEXT_MAX)

    @field_validator("hint", mode="before")
    @classmethod
    def clip_hint(cls, value: Any) -> str:
        return _clip(value, REQUEST_PREFERENCE_HINT_MAX)


class GeneratedRequest(BaseModel):
    wish: str
    preferences: list[_GeneratedPreference]

    @field_validator("wish", mode="before")
    @classmethod
    def clip_wish(cls, value: Any) -> str:
        wish = _clip(value, REQUEST_WISH_MAX)
        if not wish:
            raise ValueError("wish が空です")
        return wish

    @field_validator("preferences", mode="before")
    @classmethod
    def keep_valid_preferences(cls, value: Any) -> Any:
        if not isinstance(value, list):
            raise ValueError("preferences は配列です")
        kept = [
            item
            for item in value
            if isinstance(item, dict) and _clip(item.get("text"), 1)
        ][:REQUEST_PREFERENCES_MAX]
        if len(kept) < REQUEST_PREFERENCES_MIN:
            raise ValueError(f"preferences は {REQUEST_PREFERENCES_MIN} 件以上必要です")
        return kept


class RequestEvaluationOutput(BaseModel):
    fit: str = "none"
    met_preference_ids: list[str] = []
    hint: str = ""

    @field_validator("fit", mode="before")
    @classmethod
    def coerce_fit(cls, value: Any) -> str:
        fit = str(value or "").strip().lower()
        return fit if fit in REQUEST_FITS else "none"

    @field_validator("met_preference_ids", mode="before")
    @classmethod
    def coerce_ids(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item or "").strip()]

    @field_validator("hint", mode="before")
    @classmethod
    def clip_hint(cls, value: Any) -> str:
        return _clip(value, REQUEST_EVALUATION_HINT_MAX)


def compute_satisfaction(fit: str, met_count: int, total: int) -> int:
    """願いへの近さと満たした好みの割合から満足度(0〜100)を決める。"""
    fit_score = REQUEST_FIT_SCORES.get(fit, 0)
    preference_score = (
        round(REQUEST_PREFERENCES_SCORE * met_count / total) if total > 0 else 0
    )
    return max(0, min(100, fit_score + preference_score))


def evaluation_record(
    output: RequestEvaluationOutput, preferences: list[dict[str, Any]]
) -> dict[str, Any]:
    """LLM の判定を、履歴へ保存する評価にする。未知の ID は捨てる。"""
    met_ids = set(output.met_preference_ids)
    met = [item["id"] for item in preferences if item.get("id") in met_ids]
    all_met = len(met) == len(preferences)
    return {
        "satisfaction": compute_satisfaction(output.fit, len(met), len(preferences)),
        "fit": output.fit,
        "met_preference_ids": met,
        "hint": "" if all_met else output.hint,
    }


def is_fulfilled(evaluation: dict[str, Any] | None) -> bool:
    return bool(evaluation) and (
        int(evaluation.get("satisfaction") or 0) >= REQUEST_FULFILL_THRESHOLD
    )


def public_request_view(
    request: dict[str, Any],
    evaluations: list[dict[str, Any]],
    *,
    can_regenerate: bool,
) -> dict[str, Any]:
    """フロントへ配信する依頼。伏せた好みの本文は一度満たされるまで送らない。"""
    revealed: set[str] = set()
    for evaluation in evaluations:
        revealed.update(str(item) for item in evaluation.get("met_preference_ids", []))
    latest = evaluations[-1] if evaluations else None
    current_met = set(latest.get("met_preference_ids", [])) if latest else set()
    return {
        "wish": request["wish"],
        "status": request.get("status") or "active",
        "satisfaction": int(latest.get("satisfaction") or 0) if latest else 0,
        "threshold": REQUEST_FULFILL_THRESHOLD,
        "fit": latest.get("fit") if latest else None,
        "hint": str(latest.get("hint") or "") if latest else "",
        "preferences": [
            {
                "id": item["id"],
                "hint": str(item.get("hint") or ""),
                "text": str(item.get("text") or "") if item["id"] in revealed else None,
                "met": item["id"] in current_met,
            }
            for item in request.get("preferences", [])
            if item.get("id")
        ],
        "evaluated_turns": len(evaluations),
        "can_regenerate": can_regenerate,
    }


def feeling_context(
    request: dict[str, Any], evaluation: dict[str, Any] | None, language: str
) -> str:
    """心境プロンプトに添える依頼ブロック。評価が無ければ願いだけを伝える。"""
    preferences = request.get("preferences", [])
    met_ids = set(evaluation.get("met_preference_ids", [])) if evaluation else set()
    return build_request_feeling_context(
        wish=request["wish"],
        met_texts=[item["text"] for item in preferences if item["id"] in met_ids],
        unmet_texts=[item["text"] for item in preferences if item["id"] not in met_ids],
        fit=evaluation.get("fit") if evaluation else None,
        language=language,
    )


async def _generate_text(
    system_prompt: str, user_prompt: str, *, novelai_model: str | None
) -> str:
    # 補助判定も本文生成と同じプロバイダ・テキストモデルに従わせる
    result = await llm_service.generate_feeling(
        system_prompt,
        user_prompt,
        novelai_model_override=novelai_model,
        max_tokens=1024,
    )
    record_cost(result.cost_usd)
    return result.content


async def _character_profile(session: PersistedSession) -> dict[str, Any]:
    if session.character_id:
        character = character_manager.get_by_id(session.character_id)
        if character is not None:
            return {
                "name": character.name,
                "pronoun": character.pronoun,
                "gender": character.gender,
                "personality": character.personality,
                "description": character.description,
            }
    metadata = load_custom_session_metadata(session.id) or {}
    return {
        "name": metadata.get("name") or "",
        "pronoun": metadata.get("pronoun") or "",
        "gender": metadata.get("gender") or "",
        "personality": metadata.get("personality") or "",
        "description": metadata.get("description") or "",
    }


class SessionRequestService:
    async def get_request_view(self, session_id: str) -> dict[str, Any] | None:
        request = await session_store.get_session_request(session_id)
        if request is None:
            return None
        session = await session_store.get_session_by_id(session_id)
        evaluations = await session_store.get_request_evaluations(session_id)
        return public_request_view(
            request,
            evaluations,
            can_regenerate=bool(session) and session.transformation_count == 0,
        )

    async def create_request(
        self, session_id: str, *, language: str
    ) -> tuple[dict[str, Any], float]:
        """依頼を生成して保存し、(公開ビュー, API 料金 USD) を返す。

        作り直しは最初の着せ替えの前だけ許す。
        """
        session = await session_store.get_session_by_id(session_id)
        if session is None:
            raise SessionRequestError("session_not_found", "セッションが見つかりません")
        if session.self_mode:
            raise SessionRequestError(
                "self_mode", "自分自身モードでは依頼を受けられません"
            )
        existing = await session_store.get_session_request(session_id)
        if existing is not None and session.transformation_count > 0:
            raise SessionRequestError(
                "request_locked", "最初の着せ替えの後は依頼を作り直せません"
            )
        profile = await _character_profile(session)
        latest = await session_store.get_latest_history(session_id)
        appearance = (
            (latest.after_description or latest.before_description or "")
            if latest
            else ""
        )
        user_settings = await session_store.get_user_settings()
        novelai_model = user_settings.get("novelai_text_model")
        tracker = begin_cost_tracking()
        system_prompt, user_prompt = build_request_generation_prompt(
            profile, appearance, language
        )

        async def generate(system: str, user: str) -> str:
            return await _generate_text(system, user, novelai_model=novelai_model)

        generated = await generate_validated(
            GeneratedRequest,
            generate=generate,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        saved = await session_store.save_session_request(
            session_id,
            wish=generated.wish,
            preferences=[
                {"id": f"p{index}", "text": item.text, "hint": item.hint}
                for index, item in enumerate(generated.preferences, start=1)
            ],
            language=language,
        )
        return public_request_view(saved, [], can_regenerate=True), tracker.total_usd

    async def evaluate_turn(
        self,
        request: dict[str, Any],
        *,
        current_look: str,
        instruction: str,
        language: str,
        novelai_model: str | None,
    ) -> dict[str, Any] | None:
        """この手番の姿を評価する。失敗しても手番は止めず None を返す。"""
        system_prompt, user_prompt = build_request_evaluation_prompt(
            wish=request["wish"],
            preferences=request.get("preferences", []),
            current_look=current_look,
            instruction=instruction,
            language=language,
        )

        async def generate(system: str, user: str) -> str:
            return await _generate_text(system, user, novelai_model=novelai_model)

        try:
            output = await generate_validated(
                RequestEvaluationOutput,
                generate=generate,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as error:
            logger.warning(
                "Request evaluation failed: %s: %s", type(error).__name__, error
            )
            return None
        return evaluation_record(output, request.get("preferences", []))


session_request_service = SessionRequestService()
