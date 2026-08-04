"""TSF Bloomer の 6 軸素質算出。

セッションのやり取り本文とタグ集計から経験シグナルを抽出し、6軸ステータスを
決定論的に算出する。LLMは使用しない。

算出は3層構造:
  第1層 compute_core_axes        … モード非依存のコア値
  第2層 apply_*_mode_modifier    … 通常モード(SessionStats) / セルフモード(SelfProfile)
  第3層 normalize_axes           … 公平化正規化と個体差の付与
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from ..consts.bloomer_consts import (
    ATTRIBUTE_COUNT_CAP,
    AXIS_KEYS,
    AXIS_MAX,
    AXIS_MIN,
    AXIS_TOTAL_TARGET,
    CONVERSATION_COUNT_CAP,
    CORE_AXIS_FLOOR,
    CORE_AXIS_WEIGHTS,
    COSTUME_CATEGORY_COUNT,
    DEPRAVED_COSTUME_CATEGORIES,
    EXPOSURE_WEIGHTS,
    HISTORY_COUNT_CAP,
    INSTRUCTION_TYPE_COUNT,
    MAX_CONVERSATION_SCAN,
    MAX_HISTORY_SCAN,
    MAX_TEXT_LENGTH_PER_ROW,
    MODIFIER_WEIGHT,
    REACTION_STYLE_BIAS,
    SELF_PROFILE_ATTITUDE_BONUS,
    SELF_PROFILE_INTEREST_BONUS,
    SELF_PROFILE_INTEREST_CAP,
    TRANSFORMATION_COUNT_CAP,
)
from .bloomer_lexicon_loader import BloomerLexicon, get_bloomer_lexicon

# 本文スキャン対象のシグナルカテゴリ (attitude_* は SelfProfile 専用のため除外)
SCANNED_CATEGORIES: tuple[str, ...] = (
    "intimacy",
    "climax",
    "received",
    "initiative",
    "receptivity",
    "resistance",
    "dominance",
    "submission",
    "partner",
    "tsf_identity",
)

# 通常モードで SessionStats による補正を受ける軸
NORMAL_MODE_MODIFIER_AXES: frozenset[str] = frozenset(
    ("allure", "depravity", "endurance", "composure")
)

# =============================================================================
# 入力データ (DB非依存)
# =============================================================================


@dataclass(frozen=True)
class HistoryRecord:
    instruction: str = ""
    feeling_text: str | None = None
    after_description: str | None = None
    instruction_type: str | None = None
    costume_category: str | None = None
    exposure_level: str | None = None


@dataclass(frozen=True)
class ConversationRecord:
    role: str = "assistant"
    content: str = ""


@dataclass(frozen=True)
class StatsRecord:
    bloom: int = 0
    shame: int = 50
    adaptation: int = 0


@dataclass(frozen=True)
class FighterSource:
    """ステータス算出の入力一式。"""

    session_id: str
    self_mode: bool = False
    transformation_count: int = 0
    source_history_id: str | None = None
    histories: Sequence[HistoryRecord] = field(default_factory=tuple)
    conversations: Sequence[ConversationRecord] = field(default_factory=tuple)
    attribute_texts: Sequence[str] = field(default_factory=tuple)
    stats: StatsRecord | None = None
    self_profile: dict[str, Any] | None = None


# =============================================================================
# 汎用ヘルパ
# =============================================================================


def log_scale(value: float, cap: float) -> float:
    """0..100 に収まる逓減曲線。cap 到達で 100。"""
    if cap <= 0:
        return 0.0
    normalized = math.log1p(max(0.0, value)) / math.log1p(cap)
    return min(100.0, 100.0 * normalized)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _truncate(text: str | None) -> str:
    if not text:
        return ""
    return text[:MAX_TEXT_LENGTH_PER_ROW].lower()


def _count_hits(texts: Iterable[str], keywords: Sequence[str]) -> tuple[int, set[str]]:
    """キーワードにヒットした行数と、ヒットしたキーワードの種類を返す。"""
    if not keywords:
        return 0, set()
    hit_rows = 0
    matched: set[str] = set()
    for text in texts:
        if not text:
            continue
        row_matched = False
        for keyword in keywords:
            if keyword in text:
                matched.add(keyword)
                row_matched = True
        if row_matched:
            hit_rows += 1
    return hit_rows, matched


def _seed_jitter(seed_source: str, axis: str) -> float:
    digest = hashlib.sha256(f"{seed_source}:{axis}".encode("utf-8")).digest()
    raw = int.from_bytes(digest[:4], "big")
    return (raw % 601) / 100.0 - 3.0


# =============================================================================
# 第0層: 経験シグナル抽出
# =============================================================================


def extract_signals(
    source: FighterSource, lexicon: BloomerLexicon | None = None
) -> tuple[dict[str, float], dict[str, int]]:
    """本文とタグ集計から正規化済みシグナルと生カウントを返す。"""
    lex = lexicon or get_bloomer_lexicon()

    histories = list(source.histories)[-MAX_HISTORY_SCAN:]
    conversations = list(source.conversations)[-MAX_CONVERSATION_SCAN:]

    row_texts: list[str] = []
    for history in histories:
        merged = " ".join(
            part
            for part in (
                history.instruction,
                history.feeling_text,
                history.after_description,
            )
            if part
        )
        row_texts.append(_truncate(merged))
    row_texts.extend(_truncate(item.content) for item in conversations)

    raw: dict[str, int] = {}
    signals: dict[str, float] = {}

    for category in SCANNED_CATEGORIES:
        keywords = lex.keywords_for(category)
        hits, matched = _count_hits(row_texts, keywords)
        raw[category] = hits
        cap = lex.cap_for(category)
        if category == "partner":
            raw["partner_variety"] = len(matched)
            signals["partner_bond"] = log_scale(hits, cap)
            signals["partner_variety"] = log_scale(len(matched), max(1, cap // 3))
        else:
            signals[category] = log_scale(hits, cap)

    history_count = len(histories)
    raw["history_count"] = history_count
    raw["conversation_count"] = len(conversations)
    raw["attribute_count"] = len(source.attribute_texts)
    raw["transformation_count"] = source.transformation_count

    signals["history_progress"] = log_scale(history_count, HISTORY_COUNT_CAP)
    signals["conversation_progress"] = log_scale(
        len(conversations), CONVERSATION_COUNT_CAP
    )
    signals["attribute_progress"] = log_scale(
        len(source.attribute_texts), ATTRIBUTE_COUNT_CAP
    )
    signals["transformation_progress"] = log_scale(
        source.transformation_count, TRANSFORMATION_COUNT_CAP
    )

    # 露出スコア: exposure_level の加重平均
    exposure_total = 0
    exposure_rows = 0
    costume_categories: set[str] = set()
    deprived_rows = 0
    instruction_types: set[str] = set()
    reality_rows = 0
    for history in histories:
        if history.exposure_level in EXPOSURE_WEIGHTS:
            exposure_total += EXPOSURE_WEIGHTS[history.exposure_level]
            exposure_rows += 1
        if history.costume_category:
            costume_categories.add(history.costume_category)
            if history.costume_category in DEPRAVED_COSTUME_CATEGORIES:
                deprived_rows += 1
        if history.instruction_type:
            instruction_types.add(history.instruction_type)
            if history.instruction_type == "reality_alter":
                reality_rows += 1

    signals["exposure_score"] = exposure_total / exposure_rows if exposure_rows else 0.0
    signals["costume_diversity"] = (
        len(costume_categories) / COSTUME_CATEGORY_COUNT * 100.0
    )
    signals["type_diversity"] = len(instruction_types) / INSTRUCTION_TYPE_COUNT * 100.0
    signals["reality_ratio"] = (
        reality_rows / history_count * 100.0 if history_count else 0.0
    )
    signals["deprived_costume_ratio"] = (
        deprived_rows / history_count * 100.0 if history_count else 0.0
    )

    raw["exposure_rows"] = exposure_rows
    raw["costume_variety"] = len(costume_categories)
    raw["reality_count"] = reality_rows

    return signals, raw


# =============================================================================
# 第1層: 6軸コア
# =============================================================================


def compute_core_axes(signals: dict[str, float]) -> dict[str, float]:
    axes: dict[str, float] = {}
    for axis, weights in CORE_AXIS_WEIGHTS.items():
        total = sum(signals.get(key, 0.0) * weight for key, weight in weights.items())
        axes[axis] = _clamp(total + CORE_AXIS_FLOOR, 0.0, 100.0)
    return axes


# =============================================================================
# 第2層: モード別補正
# =============================================================================


def _blend(core: float, modifier: float) -> float:
    return core * (1.0 - MODIFIER_WEIGHT) + modifier * MODIFIER_WEIGHT


def apply_normal_mode_modifier(
    core: dict[str, float], stats: StatsRecord | None
) -> dict[str, float]:
    if stats is None:
        return dict(core)

    bloom = _clamp(float(stats.bloom), 0.0, 100.0)
    shame_inverted = _clamp(100.0 - float(stats.shame), 0.0, 100.0)
    adaptation = _clamp((float(stats.adaptation) + 100.0) / 2.0, 0.0, 100.0)

    modifiers = {
        "allure": bloom,
        "composure": shame_inverted,
        "endurance": adaptation,
        "depravity": bloom * 0.6 + shame_inverted * 0.4,
    }

    result = dict(core)
    for axis in NORMAL_MODE_MODIFIER_AXES:
        result[axis] = _blend(core[axis], modifiers[axis])
    return result


def apply_self_mode_modifier(
    core: dict[str, float],
    self_profile: dict[str, Any] | None,
    lexicon: BloomerLexicon | None = None,
) -> dict[str, float]:
    profile = self_profile or {}
    style = str(profile.get("reaction_style") or "default")
    bias = REACTION_STYLE_BIAS.get(style, REACTION_STYLE_BIAS["default"])

    result = {axis: _blend(core[axis], float(bias[axis])) for axis in AXIS_KEYS}

    interests = profile.get("interests") or []
    if isinstance(interests, list) and interests:
        ratio = min(1.0, len(interests) / SELF_PROFILE_INTEREST_CAP)
        result["technique"] += SELF_PROFILE_INTEREST_BONUS * ratio

    attitude = _truncate(str(profile.get("tsf_attitude") or ""))
    if attitude:
        lex = lexicon or get_bloomer_lexicon()
        positive, _ = _count_hits([attitude], lex.keywords_for("attitude_positive"))
        negative, _ = _count_hits([attitude], lex.keywords_for("attitude_negative"))
        if positive and not negative:
            result["depravity"] += SELF_PROFILE_ATTITUDE_BONUS
            result["composure"] -= SELF_PROFILE_ATTITUDE_BONUS * 0.5
        elif negative and not positive:
            result["composure"] += SELF_PROFILE_ATTITUDE_BONUS
            result["depravity"] -= SELF_PROFILE_ATTITUDE_BONUS * 0.5

    return {axis: _clamp(value, 0.0, 100.0) for axis, value in result.items()}


# =============================================================================
# 第3層: 公平化正規化
# =============================================================================


def normalize_axes(axes: dict[str, float], seed_source: str) -> dict[str, int]:
    """6軸合計を目標帯に揃えつつ、決定論的な個体差を付与する。"""
    jittered = {
        axis: _clamp(axes[axis] + _seed_jitter(seed_source, axis), 1.0, 100.0)
        for axis in AXIS_KEYS
    }

    total = sum(jittered.values())
    if total > 0:
        factor = AXIS_TOTAL_TARGET / total
        jittered = {
            axis: _clamp(value * factor, float(AXIS_MIN), float(AXIS_MAX))
            for axis, value in jittered.items()
        }

    result = {axis: int(round(value)) for axis, value in jittered.items()}
    return _rebalance(result)


def _rebalance(axes: dict[str, int]) -> dict[str, int]:
    """クランプで生じた合計のズレを、余裕のある軸へ配分する。"""
    result = dict(axes)
    for _ in range(AXIS_TOTAL_TARGET):
        diff = AXIS_TOTAL_TARGET - sum(result.values())
        if diff == 0:
            break
        step = 1 if diff > 0 else -1
        candidates = [
            axis for axis in AXIS_KEYS if AXIS_MIN <= result[axis] + step <= AXIS_MAX
        ]
        if not candidates:
            break
        # 合計を増やすときは低い軸から、減らすときは高い軸から埋める
        candidates.sort(key=lambda axis: (result[axis], axis), reverse=step < 0)
        result[candidates[0]] += step
    return result


# =============================================================================
# オーケストレーション
# =============================================================================


def build_base_stats(
    source: FighterSource, lexicon: BloomerLexicon | None = None
) -> dict[str, Any]:
    """6軸素質を算出して返す。"""
    lex = lexicon or get_bloomer_lexicon()
    signals, raw = extract_signals(source, lex)
    core = compute_core_axes(signals)

    if source.self_mode:
        adjusted = apply_self_mode_modifier(core, source.self_profile, lex)
        source_mode = "self"
    else:
        adjusted = apply_normal_mode_modifier(core, source.stats)
        source_mode = "normal"

    seed_source = f"{source.session_id}:{source.source_history_id or ''}"
    axes = normalize_axes(adjusted, seed_source)

    return {
        "axes": axes,
        "source_mode": source_mode,
        "signals": {key: round(value, 2) for key, value in sorted(signals.items())},
        "raw": dict(sorted(raw.items())),
    }
