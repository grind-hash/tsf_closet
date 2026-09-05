"""LLM の出力から JSON を取り出して検証するための共通処理。

モデルは JSON をコードフェンスで囲んだり前後に説明文を付けたりするため、
各サービスで似た前処理が繰り返されていた。フェンス除去・オブジェクト抽出・
Pydantic 検証・「検証に失敗したら 1 回だけ修復を依頼する」ループをここに集約する。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

_FENCE = "```"


def strip_code_fence(raw: str | None) -> str:
    """``\\`\\`\\`json ... \\`\\`\\``` のようなコードフェンスと前後の空白を取り除く。

    先頭のフェンス行（言語タグ付きを含む）、末尾のフェンス、途中に紛れた
    フェンスだけの行を除く。フェンスが無ければ空白除去だけを行う。
    """
    text = (raw or "").strip()
    if not text:
        return ""
    lines = text.splitlines()
    if lines and lines[0].startswith(_FENCE):
        lines = lines[1:]
    if lines and lines[-1].rstrip().endswith(_FENCE):
        last = lines[-1].rstrip()[: -len(_FENCE)]
        lines = lines[:-1] + ([last] if last.strip() else [])
    lines = [line for line in lines if line.strip() != _FENCE]
    return "\n".join(lines).strip()


def extract_json_object(raw: str | None) -> str:
    """フェンスを除いたうえで、最初の ``{`` から最後の ``}`` までを返す。

    前後に説明文が混ざった出力向け。波括弧が見つからなければフェンス除去後の
    テキストをそのまま返す。
    """
    text = strip_code_fence(raw)
    start = text.find("{")
    end = text.rfind("}")
    return text[start : end + 1] if start >= 0 and end > start else text


def validate_model_json(
    model: type[ModelT],
    raw: str,
    *,
    context: dict[str, Any] | None = None,
) -> ModelT:
    """LLM 出力の JSON を Pydantic モデルで検証する。制御文字だけが不正な場合は救済する。

    ローカルモデルは JSON 文字列内へ生の改行を混ぜやすく、厳密パースだけでは
    復旧可能な出力まで失うため、``json.loads(strict=False)`` で再試行する。
    それでも読めなければ元の検証エラーを送出し、呼び出し側の修復へ委ねる。
    """
    text = extract_json_object(raw)
    try:
        return model.model_validate_json(text, context=context)
    except ValidationError as strict_error:
        try:
            data = json.loads(text, strict=False)
        except ValueError as lenient_error:
            raise strict_error from lenient_error
        return model.model_validate(data, context=context)


class StructuredOutputError(Exception):
    """修復を 1 回試しても JSON がスキーマに合わなかった。"""

    def __init__(
        self,
        model_name: str,
        first_error: ValidationError,
        second_error: ValidationError,
        *,
        raw: str,
        repaired: str,
    ) -> None:
        super().__init__(f"{model_name} output failed validation twice")
        self.model_name = model_name
        self.first_error = first_error
        self.second_error = second_error
        self.raw = raw
        self.repaired = repaired


def default_repair_prompt(first_error: ValidationError, raw: str) -> str:
    """修復依頼の既定文。元の出力に無い事実を足させず、長さ制限も守らせる。"""
    return (
        "Repair the following output into one valid compact JSON object for "
        "the required schema. Return JSON only and do not add new facts. "
        "Respect every string length limit in the schema; when a value is "
        "too long, shorten it by dropping trailing details. "
        f"Fix these validation errors:\n{first_error}\n\n" + raw
    )


async def generate_validated(
    model: type[ModelT],
    *,
    generate: Callable[[str, str], Awaitable[str]],
    system_prompt: str,
    user_prompt: str,
    context: dict[str, Any] | None = None,
    repair_prompt: Callable[[ValidationError, str], str] = default_repair_prompt,
    repair_system_prompt: str | None = None,
) -> ModelT:
    """LLM に生成させ、検証に失敗したら 1 回だけ修復を依頼して再検証する。

    ``generate(system_prompt, user_prompt)`` はテキストを返すコルーチン。
    2 回目も失敗したら :class:`StructuredOutputError` を送出する。
    """
    raw = await generate(system_prompt, user_prompt)
    try:
        return validate_model_json(model, raw, context=context)
    except ValidationError as first_error:
        logger.warning(
            "%s JSON validation failed; requesting a repair: %s",
            model.__name__,
            first_error,
        )
        repaired = await generate(
            repair_system_prompt or system_prompt, repair_prompt(first_error, raw)
        )
        try:
            return validate_model_json(model, repaired, context=context)
        except ValidationError as second_error:
            raise StructuredOutputError(
                model.__name__,
                first_error,
                second_error,
                raw=raw,
                repaired=repaired,
            ) from second_error
