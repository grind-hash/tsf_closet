"""性別適合（gender congruence）判定モジュール。

元の性別と現在の服装・認識状態から、TSF 的な性別違和感を感じるべきかを判定する。
- ルールベース: 低遅延。設定 OFF 時の既定経路
- 専用 LLM: 会話経緯・身体認識を含む高度判定。設定 ON 時のみ

feeling_mode:
- legacy: 従来のTSF抵抗心境（性別適合判定なし）
- gender_aware: 性別適合を考慮（ルール。LLM は設定トグル時）

誤って保存された別名:
- new / experimental → gender_aware に正規化
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

FeelingMode = Literal["legacy", "gender_aware"]
VALID_FEELING_MODES: frozenset[str] = frozenset({"legacy", "gender_aware"})
# 誤って保存された別名の互換
_FEELING_MODE_ALIASES: dict[str, FeelingMode] = {
    "new": "gender_aware",
    "experimental": "gender_aware",
}


def normalize_feeling_mode(mode: str | None) -> FeelingMode:
    """feeling_mode を正規化する。不明値は legacy。"""
    raw = (mode or "legacy").strip().lower()
    if raw in _FEELING_MODE_ALIASES:
        return _FEELING_MODE_ALIASES[raw]
    if raw in VALID_FEELING_MODES:
        return raw  # type: ignore[return-value]
    return "legacy"


def is_gender_aware_feeling_mode(mode: str | None) -> bool:
    """性別適合心境を使うモードか。"""
    return normalize_feeling_mode(mode) == "gender_aware"


def should_use_congruence_llm(
    mode: str | None,
    llm_enabled: bool = False,
) -> bool:
    """性別適合 LLM 判定を使うか。

    - gender_aware: 設定トグル ON のときのみ
    - legacy: 使わない
    """
    if not is_gender_aware_feeling_mode(mode):
        return False
    return bool(llm_enabled)


FitKind = Literal["congruent", "incongruent", "ambiguous"]
BodyState = Literal["original", "altered", "unknown"]
SocialRecognition = Literal["original", "opposite", "unknown"]
SourceKind = Literal["rule", "llm", "fallback"]

# 明示的な女性向けマーカー（他語と共起しても優先。例: レディーススーツ）
EXPLICIT_FEMININE_MARKERS: list[str] = [
    "レディース",
    "レディス",
    "女性用",
    "女性向け",
    "女物",
    "女装",
    "女体化",
    "女性化",
    "女子制服",
    "女の子の服",
    "スカートスーツ",
    "ladies",
    "women's",
    "womens",
    "female-only",
]

# 明示的な男性向けマーカー
EXPLICIT_MASCULINE_MARKERS: list[str] = [
    "メンズ",
    "男性用",
    "男性向け",
    "男物",
    "男装",
    "mens",
    "men's",
    "male-only",
]

# 女性寄り（元が男性なら不適合、元が女性なら適合寄り）
FEMININE_KEYWORDS: list[str] = [
    *EXPLICIT_FEMININE_MARKERS,
    "スカート",
    "ワンピース",
    "ドレス",
    "メイド",
    "メイド服",
    "ビキニ",
    "水着",
    "セーラー服",
    "セーラー",
    "ゴスロリ",
    "ロリータ",
    "ヒール",
    "パンプス",
    "ブラ",
    "ブラジャー",
    "パンティ",
    "パンツィ",
    "下着",
    "女の子",
    "少女",
    "リボン",
    "フリル",
    "ミニスカ",
    "タイツ",
    "ストッキング",
    "ニーソ",
    "ブラウス",
    "キャミソール",
    "ネグリジェ",
    "チア",
    "チアリーダー",
    "ブルマ",
    "レオタード",
    "skirt",
    "dress",
    "maid",
    "bikini",
    "lolita",
    "heels",
    "crossdress",
]

# 男性寄り
# 注意: 裸の「スーツ」「suit」はレディーススーツにも部分一致するため弱語扱いにする
MASCULINE_KEYWORDS: list[str] = [
    *EXPLICIT_MASCULINE_MARKERS,
    "メンズスーツ",
    "ワイシャツ",
    "シャツ",
    "ネクタイ",
    "学ラン",
    "学生服",
    "スラックス",
    "ズボン",
    "パンツ",  # 日本語ではズボン意味も強いが女性下着と衝突 → 単独では弱い
    "ジャケット",
    "ブレザー",
    "コート",
    "革靴",
    "ローファー",
    "男の子",
    "タキシード",
    "ビジネススーツ",
    "作業着",
    "つなぎ",
    "スーツ姿",
    "mens suit",
    "necktie",
    "slacks",
    "tuxedo",
    # 弱い（共起語）
    "スーツ",
    "suit",
]

# ユニセックス（どちらでも違和感が薄い）
UNISEX_KEYWORDS: list[str] = [
    "パジャマ",
    "ジャージ",
    "パーカー",
    "tシャツ",
    "ティーシャツ",
    "t-shirt",
    "tee",
    "スウェット",
    "ルームウェア",
    "部屋着",
    "トレーナー",
    "スニーカー",
    "靴下",
    "hoodie",
    "pajamas",
    "jersey",
    "sweatshirt",
]

# 単独では性別を断定しにくい男性語
_WEAK_MASCULINE = {
    "パンツ",
    "シャツ",
    "ジャケット",
    "ブレザー",
    "コート",
    "スーツ",
    "suit",
    "スーツ姿",
}


@dataclass(frozen=True)
class GenderCongruenceResult:
    """性別適合判定結果。"""

    fit: FitKind
    should_feel_gender_discomfort: bool
    body_state: BodyState = "unknown"
    social_recognition: SocialRecognition = "unknown"
    reason: str = ""
    source: SourceKind = "rule"


CONGRUENCE_SYSTEM_PROMPT = """あなたはTSF着せ替えゲームの状況判定者です。
キャラクターの「元の性別」と、今回の指示・現在の外見・これまでの経緯から、
**今この瞬間に性別違和・女装/男装羞恥を感じるべきか**を判定してください。

判定の観点:
1. 今回の服装そのものが、元の性別の衣服として自然か（最優先）
2. 身体や自己認識は既に変質しているか（女体化・男体化など）
3. 周囲の認識はどうか
4. 服装だけが元性別に戻っても、身体変化が残っていれば違和感は残り得る

【服装ラベルの厳守 — 絶対に守ること】
- 「メンズ」「男性用」「mens」と付いた服 → 男性向け
- 「レディース」「レディス」「女性用」「ladies」「women's」と付いた服 → 女性向け
- 元が男性で「レディーススーツ」「レディース○○」は必ず女装 (fit=incongruent, discomfort=true)
- 元が男性で「メンズスーツ」「メンズ○○」は自然 (fit=congruent, discomfort=false)
- 「スーツ」単体は、元が男性なら男性用とみなしてよい。ただしレディース/女性用と併記されていれば女性向け
- 「〜と見なせる」「だいたい同じ」で性別ラベルを打ち消してはいけない
- ビジネス用途やフォーマルだからといって、レディース服を男性自然服に読み替えてはいけない

例（元の性別=男性）:
- 「メンズスーツ」→ congruent, discomfort=false
- 「パジャマ」→ congruent, discomfort=false（性別中立）
- 「レディーススーツ」→ incongruent, discomfort=true
- 「スカート」→ incongruent, discomfort=true
- 「メイド服」→ incongruent, discomfort=true

例（元の性別=女性）:
- 「ドレス」→ congruent, discomfort=false
- 「レディーススーツ」→ congruent, discomfort=false
- 「メンズスーツ」→ incongruent, discomfort=true

出力は次の1行 JSON のみ（説明文禁止）:
{"fit":"congruent|incongruent|ambiguous","discomfort":true|false,"body":"original|altered|unknown","social":"original|opposite|unknown","reason":"短い理由"}

定義:
- fit=congruent: 元性別と服装が自然で、状況的にも性別羞恥が不要
- fit=incongruent: 異性装・性転換後の服装など、性別違和感の対象
- fit=ambiguous: 判断不能
- discomfort=true のときのみ、心境に「おかしい/元に戻りたい」系を出してよい
"""


def _normalize_text(text: str) -> str:
    return (text or "").casefold()


def _count_keyword_hits(text: str, keywords: list[str]) -> list[str]:
    hits: list[str] = []
    for kw in keywords:
        if kw.casefold() in text:
            hits.append(kw)
    return hits


def _has_explicit_markers(text: str, markers: list[str]) -> list[str]:
    return _count_keyword_hits(text, markers)


def evaluate_gender_congruence_rule(
    instruction: str,
    original_gender: str = "man",
    appearance_desc: str = "",
) -> GenderCongruenceResult:
    """ルールベースで性別適合を判定する。

    Args:
        instruction: ユーザー指示（着せ替え・行動）
        original_gender: 元の性別 ("man" | "woman")
        appearance_desc: 現在の外見説明（任意）

    Returns:
        GenderCongruenceResult
    """
    gender = (original_gender or "man").lower()
    if gender not in ("man", "woman"):
        gender = "man"

    combined = _normalize_text(f"{instruction}\n{appearance_desc}")

    explicit_fem = _has_explicit_markers(combined, EXPLICIT_FEMININE_MARKERS)
    explicit_masc = _has_explicit_markers(combined, EXPLICIT_MASCULINE_MARKERS)
    feminine_hits = _count_keyword_hits(combined, FEMININE_KEYWORDS)
    masculine_hits = _count_keyword_hits(combined, MASCULINE_KEYWORDS)
    unisex_hits = _count_keyword_hits(combined, UNISEX_KEYWORDS)

    # 弱い男性語は、他に明確な手掛かりがあるときだけ採用
    strong_masc = [h for h in masculine_hits if h not in _WEAK_MASCULINE]
    weak_masc = [h for h in masculine_hits if h in _WEAK_MASCULINE]

    # 明示マーカーは最優先（レディーススーツ vs メンズスーツ）
    if gender == "man" and explicit_fem:
        return GenderCongruenceResult(
            fit="incongruent",
            should_feel_gender_discomfort=True,
            body_state="unknown",
            social_recognition="unknown",
            reason=f"女性向け明示: {', '.join(explicit_fem[:5])}",
            source="rule",
        )
    if gender == "woman" and explicit_masc:
        return GenderCongruenceResult(
            fit="incongruent",
            should_feel_gender_discomfort=True,
            body_state="unknown",
            social_recognition="unknown",
            reason=f"男性向け明示: {', '.join(explicit_masc[:5])}",
            source="rule",
        )
    if gender == "man" and explicit_masc and not explicit_fem:
        return GenderCongruenceResult(
            fit="congruent",
            should_feel_gender_discomfort=False,
            body_state="original",
            social_recognition="original",
            reason=f"男性向け明示: {', '.join(explicit_masc[:5])}",
            source="rule",
        )
    if gender == "woman" and explicit_fem and not explicit_masc:
        return GenderCongruenceResult(
            fit="congruent",
            should_feel_gender_discomfort=False,
            body_state="original",
            social_recognition="original",
            reason=f"女性向け明示: {', '.join(explicit_fem[:5])}",
            source="rule",
        )

    if gender == "man":
        incongruent_hits = feminine_hits
        # 裸のスーツ等は男性なら適合寄り（レディース明示は上で処理済み）
        congruent_hits = strong_masc + unisex_hits + weak_masc
    else:
        incongruent_hits = strong_masc
        if explicit_masc:
            incongruent_hits = masculine_hits
        congruent_hits = feminine_hits + unisex_hits
        # 弱い男性語単独は woman では ambiguous に寄せる
        if not incongruent_hits and weak_masc and not feminine_hits and not unisex_hits:
            return GenderCongruenceResult(
                fit="ambiguous",
                should_feel_gender_discomfort=True,
                body_state="unknown",
                social_recognition="unknown",
                reason=f"弱い男性語のみ: {', '.join(weak_masc[:5])}",
                source="rule",
            )

    if incongruent_hits:
        return GenderCongruenceResult(
            fit="incongruent",
            should_feel_gender_discomfort=True,
            body_state="unknown",
            social_recognition="unknown",
            reason=f"性別不適合キーワード: {', '.join(incongruent_hits[:5])}",
            source="rule",
        )

    if congruent_hits:
        return GenderCongruenceResult(
            fit="congruent",
            should_feel_gender_discomfort=False,
            body_state="original",
            social_recognition="original",
            reason=f"性別適合/ユニセックス: {', '.join(congruent_hits[:5])}",
            source="rule",
        )

    return GenderCongruenceResult(
        fit="ambiguous",
        should_feel_gender_discomfort=True,
        body_state="unknown",
        social_recognition="unknown",
        reason="明確な性別手掛かりなし（安全側で違和感あり）",
        source="rule",
    )


def rule_has_hard_gender_marker(
    instruction: str,
    original_gender: str = "man",
    appearance_desc: str = "",
) -> bool:
    """明示的な性別マーカーがあり、ルールを LLM で上書きすべきでない場合 True。"""
    gender = (original_gender or "man").lower()
    combined = _normalize_text(f"{instruction}\n{appearance_desc}")
    if gender == "man":
        return bool(_has_explicit_markers(combined, EXPLICIT_FEMININE_MARKERS))
    if gender == "woman":
        return bool(_has_explicit_markers(combined, EXPLICIT_MASCULINE_MARKERS))
    return False


def parse_congruence_llm_response(raw: str) -> GenderCongruenceResult | None:
    """LLM 応答を GenderCongruenceResult にパースする。失敗時は None。"""
    if not raw or not raw.strip():
        return None

    text = raw.strip()
    if text.startswith("```"):
        lines = [ln for ln in text.split("\n") if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()

    # JSON オブジェクトを抽出
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if not match:
        return None

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None

    fit_raw = str(data.get("fit", "ambiguous")).lower()
    fit: FitKind
    if fit_raw in ("congruent", "incongruent", "ambiguous"):
        fit = fit_raw  # type: ignore[assignment]
    else:
        fit = "ambiguous"

    if "discomfort" in data:
        discomfort = bool(data["discomfort"])
    else:
        # fit から推定
        discomfort = fit != "congruent"

    body_raw = str(data.get("body", "unknown")).lower()
    body: BodyState
    if body_raw in ("original", "altered", "unknown"):
        body = body_raw  # type: ignore[assignment]
    else:
        body = "unknown"

    social_raw = str(data.get("social", "unknown")).lower()
    social: SocialRecognition
    if social_raw in ("original", "opposite", "unknown"):
        social = social_raw  # type: ignore[assignment]
    else:
        social = "unknown"

    reason = str(data.get("reason", ""))[:200]

    return GenderCongruenceResult(
        fit=fit,
        should_feel_gender_discomfort=discomfort,
        body_state=body,
        social_recognition=social,
        reason=reason or "llm",
        source="llm",
    )


def _build_timeline_section(
    session_timeline: list[tuple[str, str]] | None,
    limit: int = 12,
    max_chars: int = 1200,
) -> str:
    if not session_timeline:
        return "(履歴なし)"

    labels = {
        "dress_up": "着替",
        "reality_alter": "改変",
        "action": "行動",
        "conversation": "会話",
    }
    lines: list[str] = []
    for entry in session_timeline[-limit:]:
        if not isinstance(entry, tuple) or len(entry) < 2:
            continue
        itype, text = entry[0], entry[1]
        label = labels.get(itype, itype)
        clipped = (text or "")[:120].replace("\n", " ")
        lines.append(f"- [{label}] {clipped}")

    joined = "\n".join(lines)
    if len(joined) > max_chars:
        return joined[-max_chars:]
    return joined or "(履歴なし)"


def build_congruence_user_prompt(
    instruction: str,
    original_gender: str,
    appearance_desc: str = "",
    session_timeline: list[tuple[str, str]] | None = None,
    attributes: list[str] | None = None,
    instruction_type: str = "dress_up",
) -> str:
    """LLM 判定用ユーザープロンプトを構築する。"""
    gender_label = "男性" if (original_gender or "man") == "man" else "女性"
    timeline_section = _build_timeline_section(session_timeline)
    attr_section = "(なし)"
    if attributes:
        attr_section = "\n".join(f"- {a}" for a in attributes[:20])

    return (
        f"元の性別: {gender_label}\n"
        f"指示タイプ: {instruction_type}\n"
        f"今回の指示: {instruction}\n\n"
        f"現在の外見/服装:\n{appearance_desc or '(不明)'}\n\n"
        f"セッション属性:\n{attr_section}\n\n"
        f"これまでの経緯:\n{timeline_section}\n"
    )


async def evaluate_gender_congruence(
    instruction: str,
    original_gender: str = "man",
    appearance_desc: str = "",
    session_timeline: list[tuple[str, str]] | None = None,
    attributes: list[str] | None = None,
    instruction_type: str = "dress_up",
    use_llm: bool = False,
    novelai_model_override: str | None = None,
) -> GenderCongruenceResult:
    """性別適合を評価する。

    use_llm=False のときはルールのみ。
    use_llm=True のときは専用 LLM を試し、失敗時はルールにフォールバック。
    """
    rule_result = evaluate_gender_congruence_rule(
        instruction=instruction,
        original_gender=original_gender,
        appearance_desc=appearance_desc,
    )

    if not use_llm:
        return rule_result

    # レディース/メンズ等の明示マーカーがあるときはルールを優先（LLMの誤読を防ぐ）
    hard_marker = rule_has_hard_gender_marker(
        instruction, original_gender, appearance_desc
    )
    if hard_marker and rule_result.fit in ("congruent", "incongruent"):
        logger.info(
            "Gender congruence: hard marker — prefer rule fit=%s reason=%s",
            rule_result.fit,
            rule_result.reason,
        )
        return rule_result

    try:
        from .llm_service import llm_service
        from ..settings.config import settings

        user_prompt = build_congruence_user_prompt(
            instruction=instruction,
            original_gender=original_gender,
            appearance_desc=appearance_desc,
            session_timeline=session_timeline,
            attributes=attributes,
            instruction_type=instruction_type,
        )

        effective_provider = None
        if settings.image_provider == "novelai":
            effective_provider = "novelai"
        else:
            effective_provider = settings.feeling_provider

        result = await llm_service.generate_feeling(
            system_prompt=CONGRUENCE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            provider_override=effective_provider,
            novelai_model_override=novelai_model_override,
            max_tokens=256,
        )
        parsed = parse_congruence_llm_response(result.content)
        if parsed is not None:
            # ルールが不適合確定なのに LLM が適合と言ったらルールを採用
            if (
                rule_result.fit == "incongruent"
                and rule_result.should_feel_gender_discomfort
                and not parsed.should_feel_gender_discomfort
            ):
                logger.warning(
                    "Gender congruence LLM under-detected discomfort "
                    "(rule incongruent, llm congruent). Prefer rule. llm_reason=%s",
                    parsed.reason,
                )
                return GenderCongruenceResult(
                    fit=rule_result.fit,
                    should_feel_gender_discomfort=True,
                    body_state=parsed.body_state,
                    social_recognition=parsed.social_recognition,
                    reason=f"rule_override: {rule_result.reason} (llm said: {parsed.reason})",
                    source="fallback",
                )

            logger.info(
                "Gender congruence LLM: fit=%s discomfort=%s reason=%s",
                parsed.fit,
                parsed.should_feel_gender_discomfort,
                parsed.reason,
            )
            return parsed

        logger.warning(
            "Gender congruence LLM parse failed, fallback to rule. raw=%s",
            (result.content or "")[:200],
        )
    except Exception as e:
        logger.warning("Gender congruence LLM failed, fallback to rule: %s", e)

    # フォールバック: ルール結果に source を上書きした同等物
    return GenderCongruenceResult(
        fit=rule_result.fit,
        should_feel_gender_discomfort=rule_result.should_feel_gender_discomfort,
        body_state=rule_result.body_state,
        social_recognition=rule_result.social_recognition,
        reason=f"llm_fallback: {rule_result.reason}",
        source="fallback",
    )


def discomfort_free_result() -> GenderCongruenceResult:
    """違和感なしの固定結果（テスト・明示スキップ用）。"""
    return GenderCongruenceResult(
        fit="congruent",
        should_feel_gender_discomfort=False,
        body_state="original",
        social_recognition="original",
        reason="forced_congruent",
        source="rule",
    )
