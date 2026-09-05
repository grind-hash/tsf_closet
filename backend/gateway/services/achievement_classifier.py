"""
Achievement Classifier - LLMを使用した変身指示の分類

ユーザーの変身指示テキストを分析し、以下のカテゴリに分類:
- CROSS_DRESS: 異性装（元の性別と異なる服装）
- GENDER_CHANGE: 性別変更/女体化（身体的変化）
- REALITY_ALTER: 現実改変（認識・記憶・歴史の改変）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from ..settings.config import settings
from .llm_service import LLMServiceError, llm_service

logger = logging.getLogger(__name__)


# =============================================================================
# 分類カテゴリ定義
# =============================================================================

VALID_CATEGORIES = {"CROSS_DRESS", "GENDER_CHANGE", "REALITY_ALTER"}

# 分類プロンプト
CLASSIFICATION_SYSTEM_PROMPT = """あなたは優秀な分類者です。キャラクターの元の性別とユーザーのクエリを元に、どのカテゴリに分類されるかを判断してください。

【分類カテゴリ】
- CROSS_DRESS: 異性装（元の性別とは異なる性別の服装を着用）
- GENDER_CHANGE: 性別変更/女体化（身体的な性別の変化）
- REALITY_ALTER: 現実改変（周囲の認識や記憶、歴史の改変）
- NONE: 上記に該当しない

該当するカテゴリをカンマ区切りで返してください。複数該当する場合はすべて返してください。
何も該当しない場合はNONEとだけ返してください。

例:
- 入力「女性用の服に着替える」→ 出力「CROSS_DRESS」
- 入力「女体化する」→ 出力「GENDER_CHANGE」
- 入力「女体化して周囲に女性として認識される」→ 出力「GENDER_CHANGE, REALITY_ALTER」
- 入力「普通の服に着替える」→ 出力「NONE」"""


@dataclass
class ClassificationResult:
    """分類結果"""

    categories: list[str]  # 該当カテゴリのリスト
    raw_response: str  # LLMの生の応答（デバッグ用）
    provider: str  # 使用したプロバイダー
    classified_at: datetime  # 分類実行日時


# =============================================================================
# 分類関数
# =============================================================================


def parse_classification(response: str) -> list[str]:
    """
    LLM応答をパースしてカテゴリリストを抽出

    Args:
        response: LLMからの応答文字列

    Returns:
        有効なカテゴリのリスト（該当なしの場合は空リスト）

    Examples:
        >>> parse_classification("GENDER_CHANGE, REALITY_ALTER")
        ["GENDER_CHANGE", "REALITY_ALTER"]
        >>> parse_classification("NONE")
        []
        >>> parse_classification("gender_change")
        ["GENDER_CHANGE"]
    """
    if not response:
        return []

    # カンマ区切りでパースし、各カテゴリを正規化
    categories = [c.strip().upper() for c in response.split(",")]

    # 有効なカテゴリのみをフィルタリング
    valid_cats = [c for c in categories if c in VALID_CATEGORIES]

    return valid_cats


async def classify_for_achievement(
    query: str,
    gender: str = "man",
    provider: str | None = None,
) -> ClassificationResult:
    """
    変身指示テキストを実績カテゴリに分類

    Args:
        query: ユーザーの変身指示テキスト
        gender: キャラクターの元の性別 ("man" or "woman")
        provider: LLMプロバイダー（省略時は設定値）

    Returns:
        ClassificationResult - 分類結果

    Raises:
        LLMServiceError: LLM呼び出しに失敗した場合
    """
    # ユーザープロンプトを構築
    user_prompt = f"キャラクターの元の性別: {gender}\nユーザーの変身指示: {query}"

    logger.debug(f"Classification request: gender={gender}, query={query}")

    try:
        # プロバイダー選択ロジック
        # NovelAIモード時はNovelAIのテキストモデルを使用
        effective_provider = provider
        if effective_provider is None:
            if settings.image_provider == "novelai":
                effective_provider = "novelai"
            else:
                effective_provider = settings.feeling_provider

        # LLMによる分類を実行
        result = await llm_service.generate_feeling(
            system_prompt=CLASSIFICATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            provider_override=effective_provider,
        )

        # 応答をパース
        categories = parse_classification(result.content)

        logger.info(
            f"Classification result: categories={categories}, "
            f"raw={result.content.strip()}, provider={result.provider}"
        )

        return ClassificationResult(
            categories=categories,
            raw_response=result.content.strip(),
            provider=result.provider,
            classified_at=datetime.now(),
        )

    except LLMServiceError as e:
        logger.error(f"Classification LLM error: {e}")
        raise
    except Exception as e:
        logger.error(f"Classification unexpected error: {e}")
        raise LLMServiceError(f"Classification failed: {e}") from e
