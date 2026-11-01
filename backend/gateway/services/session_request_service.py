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
import re
from typing import Any

from pydantic import BaseModel, field_validator

from ..consts.session_request import (
    REQUEST_ANSWER_MAX,
    REQUEST_EVALUATION_HINT_MAX,
    REQUEST_FIT_SCORES,
    REQUEST_FITS,
    REQUEST_FULFILL_THRESHOLD,
    REQUEST_LISTENING_BONUS_MAX,
    REQUEST_LISTENING_BONUS_PER_ANSWER,
    REQUEST_PREFERENCE_HINT_MAX,
    REQUEST_PREFERENCE_TEXT_MAX,
    REQUEST_PREFERENCES_MAX,
    REQUEST_PREFERENCES_MIN,
    REQUEST_PREFERENCES_SCORE,
    REQUEST_QUESTION_LIMIT_DEFAULT,
    REQUEST_QUESTION_LIMIT_MAX,
    REQUEST_QUESTION_MAX,
    REQUEST_TURN_LIMIT_MAX,
    REQUEST_WISH_MAX,
)
from ..models import PersistedSession
from .characters import character_manager
from .clothing_layers import split_worn_under_layers
from .cost_tracker import begin_cost_tracking, record_cost
from .custom_sessions import load_custom_session_metadata
from .llm_json import generate_validated
from .llm_service import llm_service
from .session import session_store
from .session_request_prompts import (
    build_request_evaluation_prompt,
    build_request_feeling_context,
    build_request_generation_prompt,
    build_request_question_prompt,
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
    # 満たした好みと、その根拠として姿の説明から写した語句 [{id, evidence}]
    met_preferences: list[dict[str, str]] = []
    # 汲んだカウンセリングの答え(1 始まりの番号)と、その根拠の語句 [{index, evidence}]
    reflected_answers: list[dict[str, Any]] = []
    hint: str = ""

    @field_validator("fit", mode="before")
    @classmethod
    def coerce_fit(cls, value: Any) -> str:
        fit = str(value or "").strip().lower()
        return fit if fit in REQUEST_FITS else "none"

    @field_validator("met_preferences", mode="before")
    @classmethod
    def coerce_met(cls, value: Any) -> list[dict[str, str]]:
        if not isinstance(value, list):
            return []
        return [
            {
                "id": str(item.get("id") or "").strip(),
                "evidence": str(item.get("evidence") or "").strip(),
            }
            for item in value
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        ]

    @field_validator("reflected_answers", mode="before")
    @classmethod
    def coerce_reflected(cls, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        reflected: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("index"))
            except (TypeError, ValueError):
                continue
            reflected.append(
                {"index": index, "evidence": str(item.get("evidence") or "").strip()}
            )
        return reflected

    @field_validator("hint", mode="before")
    @classmethod
    def clip_hint(cls, value: Any) -> str:
        return _clip(value, REQUEST_EVALUATION_HINT_MAX)


def listening_bonus(reflected_count: int) -> int:
    """カウンセリングの答えを汲んだ数に応じた加点(上限あり)。"""
    return min(
        REQUEST_LISTENING_BONUS_MAX,
        REQUEST_LISTENING_BONUS_PER_ANSWER * max(0, reflected_count),
    )


def compute_satisfaction(
    fit: str, met_count: int, total: int, reflected_count: int = 0
) -> int:
    """願いへの近さ・満たした好みの割合・ヒアリングの反映から満足度(0〜100)を決める。"""
    fit_score = REQUEST_FIT_SCORES.get(fit, 0)
    preference_score = (
        round(REQUEST_PREFERENCES_SCORE * met_count / total) if total > 0 else 0
    )
    total_score = fit_score + preference_score + listening_bonus(reflected_count)
    return max(0, min(100, total_score))


def _normalize_for_match(text: str) -> str:
    return " ".join(str(text or "").lower().split())


# 体の特徴を表す語。服や飾りの好みの根拠には使わせない(短い髪は丈の根拠にならない)
_BODY_WORDS = ("hair", "eye", "eyes", "skin", "face")
# 好み自体が髪・頭・目などに関わるときは、体の特徴のタグも根拠に使ってよい(例: 髪のリボン)
_BODY_PREFERENCE_WORDS = (
    "髪",
    "ヘア",
    "ヘッド",
    "頭",
    "目",
    "瞳",
    "肌",
    "顔",
    "hair",
    "head",
    "eye",
    "skin",
    "face",
)


# 好みが丈や色についてのものなら、根拠にもその種類の語が要る。
# 評価役は丈の好みに無関係な服のタグ(princess dress など)を根拠に挙げることがあるため。
# (好みの文に現れる語, 根拠に必要な語)
_ATTRIBUTE_VOCABULARY: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("丈", "短", "ミニ", "膝", "ロング", "床", "length", "short", "mini", "knee"),
        (
            "short",
            "mini",
            "micro",
            "long",
            "knee",
            "thigh",
            "floor",
            "ankle",
            "maxi",
            "midi",
            "length",
            "cropped",
            "丈",
            "短",
            "長",
            "ミニ",
            "膝",
            "ロング",
        ),
    ),
    (
        ("色", "カラー", "パステル", "淡", "濃", "color", "colour", "pastel", "shade"),
        (
            "white",
            "black",
            "red",
            "blue",
            "pink",
            "green",
            "yellow",
            "purple",
            "orange",
            "brown",
            "grey",
            "gray",
            "silver",
            "gold",
            "beige",
            "navy",
            "cyan",
            "aqua",
            "teal",
            "turquoise",
            "lavender",
            "violet",
            "lilac",
            "cream",
            "ivory",
            "mint",
            "peach",
            "coral",
            "crimson",
            "scarlet",
            "magenta",
            "burgundy",
            "wine",
            "maroon",
            "rose",
            "champagne",
            "nude",
            "khaki",
            "olive",
            "emerald",
            "sapphire",
            "indigo",
            "azure",
            "sky",
            "charcoal",
            "tan",
            "pastel",
            "pale",
            "light",
            "dark",
            "vivid",
            "colorful",
            "multicolored",
            "monochrome",
            "色",
            "カラー",
            "パステル",
            "淡",
            "白",
            "黒",
            "赤",
            "青",
            "ピンク",
            "緑",
            "黄",
            "紫",
            "金",
            "銀",
        ),
    ),
)


def _clean_tag(raw: str) -> str:
    """NovelAI の強調記号({}・[]・1.2::…::)を外して小文字にそろえたタグ。"""
    tag = re.sub(r"^-?\d+(?:\.\d+)?::|::$", "", raw.strip())
    return _normalize_for_match(tag.strip("{}[]() "))


def _look_tags(look_text: str) -> set[str]:
    """タグ列の姿の説明を、強調の記号を外したタグの集合にする。"""
    return {
        tag
        for tag in (_clean_tag(raw) for raw in re.split(r"[,\n]", look_text or ""))
        if tag
    }


def _evidence_supports(
    evidence: str,
    preference: dict[str, Any],
    look_text: str,
    *,
    look_is_tags: bool,
) -> bool:
    parts = [_clean_tag(part) for part in evidence.split(",")]
    parts = [part for part in parts if part]
    if not parts:
        return False
    preference_text = _normalize_for_match(
        f"{preference.get('text') or ''} {preference.get('hint') or ''}"
    )
    allows_body = any(word in preference_text for word in _BODY_PREFERENCE_WORDS)
    joined = " ".join(parts)
    for preference_words, evidence_words in _ATTRIBUTE_VOCABULARY:
        if any(word in preference_text for word in preference_words) and not any(
            word in joined for word in evidence_words
        ):
            return False
    tags = _look_tags(look_text) if look_is_tags else None
    look = _normalize_for_match(look_text)
    for part in parts:
        # タグ列では、タグの一部(例: short black hair の short)を根拠にさせない
        if tags is not None and part not in tags:
            return False
        if tags is None and part not in look:
            return False
        if not allows_body and any(
            re.search(rf"\b{word}\b", part) for word in _BODY_WORDS
        ):
            return False
    return True


def grounded_met_ids(
    output: RequestEvaluationOutput,
    preferences: list[dict[str, Any]],
    look_text: str,
    *,
    look_is_tags: bool = False,
) -> list[str]:
    """根拠が姿の説明で実際に示されている好みだけを、満たしたものとして残す。

    LLM は説明に無い属性(例: タグに無い丈)を、無関係な語(短い髪の short など)を根拠に
    満たしたと判定することがある。根拠が説明に無い・体の特徴で服を裏付けている判定は捨てる。
    未知の ID も捨て、順序は依頼の並びに揃える。
    """
    by_id = {item.get("id"): item for item in preferences}
    grounded = {
        item["id"]
        for item in output.met_preferences
        if item["id"] in by_id
        and _evidence_supports(
            item.get("evidence") or "",
            by_id[item["id"]],
            look_text,
            look_is_tags=look_is_tags,
        )
    }
    return [item["id"] for item in preferences if item.get("id") in grounded]


def _fallback_hint(
    preferences: list[dict[str, Any]], met: list[str], language: str
) -> str:
    """LLM がヒントを書かなかったときに、満たしていない好みの分類から1文を作る。"""
    unmet = next((item for item in preferences if item.get("id") not in met), None)
    category = str((unmet or {}).get("hint") or "").strip()
    if not category:
        return ""
    if language == "ja":
        return f"「{category}」のあたりが、まだ少し気になっているようです"
    return f"Something about the {category} still seems to bother them"


def evaluation_record(
    output: RequestEvaluationOutput,
    preferences: list[dict[str, Any]],
    *,
    look_text: str,
    look_is_tags: bool = False,
    language: str = "ja",
    questions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """LLM の判定を、履歴へ保存する評価にする。根拠が姿の説明に無い判定は捨てる。"""
    met = grounded_met_ids(output, preferences, look_text, look_is_tags=look_is_tags)
    reflected = grounded_reflected_answers(
        output, questions or [], look_text, look_is_tags=look_is_tags
    )
    all_met = len(met) == len(preferences)
    hint = (
        "" if all_met else (output.hint or _fallback_hint(preferences, met, language))
    )
    return {
        "satisfaction": compute_satisfaction(
            output.fit, len(met), len(preferences), len(reflected)
        ),
        "fit": output.fit,
        "met_preference_ids": met,
        "reflected_answers": reflected,
        "listening_bonus": listening_bonus(len(reflected)),
        "hint": hint,
    }


def grounded_reflected_answers(
    output: RequestEvaluationOutput,
    questions: list[dict[str, Any]],
    look_text: str,
    *,
    look_is_tags: bool = False,
) -> list[int]:
    """姿の根拠で裏付けられた、汲んだカウンセリングの答えの番号(1 始まり・昇順)。

    根拠の照合は好みと同じ規則で行う(答えが色や丈の話なら、根拠にもその語が要る)。
    """
    reflected: set[int] = set()
    for item in output.reflected_answers:
        index = item["index"]
        if not 1 <= index <= len(questions):
            continue
        qa = questions[index - 1]
        pseudo_preference = {
            "text": f"{qa.get('question') or ''} {qa.get('answer') or ''}"
        }
        if _evidence_supports(
            item.get("evidence") or "",
            pseudo_preference,
            look_text,
            look_is_tags=look_is_tags,
        ):
            reflected.add(index)
    return sorted(reflected)


def scored_evaluations(evaluations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """評価に失敗した手番(手数には数える)を除いた、満足度を持つ評価。"""
    return [item for item in evaluations if not item.get("failed")]


def turns_remaining(
    request: dict[str, Any], evaluations: list[dict[str, Any]]
) -> int | None:
    """残りの施術の手数。上限なしは None。評価に失敗した手番も使った手数に数える。"""
    limit = request.get("turn_limit")
    if limit is None:
        return None
    return max(0, int(limit) - len(evaluations))


def questions_remaining(request: dict[str, Any]) -> int:
    return max(
        0, int(request.get("question_limit") or 0) - len(request.get("questions", []))
    )


def normalize_turn_limit(value: int | None) -> int | None:
    if value is None:
        return None
    return max(1, min(REQUEST_TURN_LIMIT_MAX, int(value)))


def normalize_question_limit(value: int | None) -> int:
    if value is None:
        return REQUEST_QUESTION_LIMIT_DEFAULT
    return max(0, min(REQUEST_QUESTION_LIMIT_MAX, int(value)))


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
    scored = scored_evaluations(evaluations)
    revealed: set[str] = set()
    for evaluation in scored:
        revealed.update(str(item) for item in evaluation.get("met_preference_ids", []))
    latest = scored[-1] if scored else None
    current_met = set(latest.get("met_preference_ids", [])) if latest else set()
    reflected_answers = set(latest.get("reflected_answers", [])) if latest else set()
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
        "evaluated_turns": len(scored),
        "turn_limit": request.get("turn_limit"),
        "turns_used": len(evaluations),
        "turns_remaining": turns_remaining(request, evaluations),
        "question_limit": int(request.get("question_limit") or 0),
        "questions": [
            {
                "question": str(item.get("question") or ""),
                "answer": str(item.get("answer") or ""),
                "reflected": index in reflected_answers,
            }
            for index, item in enumerate(request.get("questions", []), start=1)
        ],
        "listening_bonus": int(latest.get("listening_bonus") or 0) if latest else 0,
        "questions_remaining": questions_remaining(request),
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
        questions=list(request.get("questions", [])),
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
                "tsf_attitude": character.tsf_attitude,
            }
    metadata = load_custom_session_metadata(session.id) or {}
    return {
        "name": metadata.get("name") or "",
        "pronoun": metadata.get("pronoun") or "",
        "gender": metadata.get("gender") or "",
        "personality": metadata.get("personality") or "",
        "description": metadata.get("description") or "",
        "tsf_attitude": metadata.get("tsf_attitude") or "",
    }


async def _request_profile(session: PersistedSession) -> dict[str, Any]:
    """依頼の生成・質問の答えに使う人物像。TSF への態度は人物パネルの主人公を優先する。"""
    profile = await _character_profile(session)
    panel_profile = await session_store.get_protagonist_profile(session.id) or {}
    if str(panel_profile.get("tsf_attitude") or "").strip():
        profile["tsf_attitude"] = panel_profile["tsf_attitude"]
    return profile


async def session_profile(session_id: str) -> dict[str, Any] | None:
    """セッションの主人公(依頼主)の人物像。サロンの口コミなど、依頼の外でも使う。"""
    session = await session_store.get_session_by_id(session_id)
    if session is None:
        return None
    return await _request_profile(session)


async def generate_customer_text(
    system_prompt: str, user_prompt: str, *, novelai_model: str | None
) -> str:
    """依頼主の言葉を生成する(本文と同じプロバイダー・テキストモデル)。料金は記録する。"""
    return await _generate_text(system_prompt, user_prompt, novelai_model=novelai_model)


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
        self,
        session_id: str,
        *,
        language: str,
        turn_limit: int | None = None,
        question_limit: int | None = None,
    ) -> tuple[dict[str, Any], float]:
        """依頼を生成して保存し、(公開ビュー, API 料金 USD) を返す。

        作り直しは最初の着せ替えの前だけ許す。turn_limit が None なら施術の手数は上限なし。
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
        profile = await _request_profile(session)
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
            turn_limit=normalize_turn_limit(turn_limit),
            question_limit=normalize_question_limit(question_limit),
        )
        return public_request_view(saved, [], can_regenerate=True), tracker.total_usd

    async def ask_question(
        self, session_id: str, question: str, *, language: str
    ) -> tuple[dict[str, Any], float]:
        """カウンセリングの質問に、本人の口調で答えさせて記録する。

        伏せた好みは名指しせず、手掛かりとして答えに滲ませる。(公開ビュー, 料金 USD) を返す。
        """
        session = await session_store.get_session_by_id(session_id)
        if session is None:
            raise SessionRequestError("session_not_found", "セッションが見つかりません")
        request = await session_store.get_session_request(session_id)
        if request is None:
            raise SessionRequestError("request_not_found", "依頼がありません")
        text = _clip(question, REQUEST_QUESTION_MAX)
        if not text:
            raise SessionRequestError("empty_question", "質問を入力してください")
        if questions_remaining(request) <= 0:
            raise SessionRequestError(
                "request_question_limit", "これ以上は質問できません"
            )
        profile = await _request_profile(session)
        user_settings = await session_store.get_user_settings()
        tracker = begin_cost_tracking()
        system_prompt, user_prompt = build_request_question_prompt(
            profile=profile,
            wish=request["wish"],
            preferences=request.get("preferences", []),
            previous=request.get("questions", []),
            question=text,
            language=language,
        )
        raw = await _generate_text(
            system_prompt,
            user_prompt,
            novelai_model=user_settings.get("novelai_text_model"),
        )
        answer = _clip(raw.strip().strip('「」"'), REQUEST_ANSWER_MAX)
        if not answer:
            raise SessionRequestError("answer_failed", "答えを受け取れませんでした")
        saved = await session_store.append_request_question(
            session_id, question=text, answer=answer
        )
        evaluations = await session_store.get_request_evaluations(session_id)
        view = public_request_view(
            saved or request,
            evaluations,
            can_regenerate=session.transformation_count == 0,
        )
        return view, tracker.total_usd

    async def evaluate_turn(
        self,
        request: dict[str, Any],
        *,
        current_look: str,
        instruction: str,
        language: str,
        novelai_model: str | None,
        previous_look: str | None = None,
        look_is_tags: bool = False,
    ) -> dict[str, Any] | None:
        """この手番の姿を評価する。失敗しても手番は止めず None を返す。

        重ね着の記録(WORN_UNDER_LAYERS の行)は見えない下着の在庫なので、評価には渡さない。
        """
        visible_look = split_worn_under_layers(current_look)[0]
        visible_previous = split_worn_under_layers(previous_look or "")[0] or None
        system_prompt, user_prompt = build_request_evaluation_prompt(
            wish=request["wish"],
            preferences=request.get("preferences", []),
            current_look=visible_look,
            instruction=instruction,
            language=language,
            previous_look=visible_previous,
            questions=request.get("questions", []),
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
        return evaluation_record(
            output,
            request.get("preferences", []),
            look_text=f"{visible_previous or ''}\n{visible_look}",
            look_is_tags=look_is_tags,
            language=language,
            questions=request.get("questions", []),
        )


session_request_service = SessionRequestService()
