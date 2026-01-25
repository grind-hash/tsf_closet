"""
ゲームサービス

変身ゲームのコアロジックを実装。
ComfyUI (画像生成) + LiteLLM (画像説明・心境生成) を統合。
"""

from __future__ import annotations

import asyncio
import base64
import logging
import random
from dataclasses import dataclass
from typing import AsyncGenerator, Optional, Tuple

from .characters import character_manager
from .comfy import ComfyUIClient
from .config import settings
from .image_generation import image_service, ImageGenerationService
from .llm_service import llm_service, LLMServiceError
from .litellm_client import litellm_client, LiteLLMClientError
from .models import (
    Character,
    GameSession,
    PlayHistory,
    PlayRequest,
    PlayResponse,
    PersistedSession,
    SessionStats,
    TransformationTag,
    DIFFICULTY_PRESETS,
    CRITICAL_POINTS,
    CriticalPointEvent,
)
from .prompts import (
    FEELING_SYSTEM_PROMPT,
    IMAGE_DESCRIPTION_PROMPT,
    build_feeling_prompt,
    build_enhanced_feeling_prompt,
    get_critical_speech,
)
from .session import session_store
from .endings import judge_ending

logger = logging.getLogger(__name__)


class GameServiceError(RuntimeError):
    """ゲームサービスエラー"""


@dataclass
class StreamEvent:
    """ストリーミングイベント"""

    type: str  # "text", "image", "stats", "tags", "critical", "ending", "complete", "error"
    data: dict


# =============================================================================
# パラメータ計算 (T015)
# =============================================================================

BASE_SPARKLE_LEVEL = {
    "high": 15,
    "medium": 12,
    "low": 10,
}

BASE_CORRUPTION_CATEGORY = {
    "sports": 7,
    "uniform": 6,
    "dress": 8,
    "other": 7,
}

# 順応度変化の衣装カテゴリマッピング
ADAPTATION_BY_CATEGORY = {
    "cosplay": 2,
    "uniform": 1,
    "sports": 1,
    "other": 0,
}

# =============================================================================
# コンテンツフィルタリング (子供向けコンテンツの安全性チェック)
# =============================================================================

# 子供向けコンテンツとして不適切なキーワード（部分一致）
BLOCKED_KEYWORDS = [
    # 暴力・危険
    "ころす", "殺す", "しぬ", "死ぬ", "血", "けが", "怪我",
    "きずつける", "傷つける", "なぐる", "殴る", "ける", "蹴る",
    "ぶき", "武器", "じゅう", "銃", "ナイフ", "けん", "剣",
    "ばくだん", "爆弾", "ばくはつ", "爆発",
    # 性的
    "はだか", "裸", "ぬぐ", "脱ぐ", "したぎ", "下着",
    "みずぎ", "水着", "ビキニ", "セクシー", "えっち", "エッチ",
    "おとな", "大人向け", "18禁",
    # 差別・侮辱
    "ばか", "バカ", "あほ", "アホ", "しね", "死ね",
    "きもい", "キモい", "うざい", "ウザい",
    # アルコール・薬物
    "さけ", "酒", "たばこ", "タバコ", "くすり", "薬物",
    # ホラー・恐怖
    "おばけ", "ゆうれい", "幽霊", "ゾンビ", "しがい", "死骸",
    "こわい", "怖い", "ホラー", "グロ",
    # その他不適切
    "ぬすむ", "盗む", "どろぼう", "泥棒",
    "いじめ", "イジメ",
]

# 許可されるキーワード（ブロックリストの例外）
ALLOWED_EXCEPTIONS = [
    "おばけやしき",  # お化け屋敷（遊園地のアトラクションとして）
    "こわいかお",    # 怖い顔（表情として）
]

# コンテンツフィルターのプロンプト
CONTENT_FILTER_PROMPT = """あなたは子供向けアプリのコンテンツモデレーターです。
以下のテキストが、5〜10歳の子供向け「変身ごっこ遊び」アプリで使用するのに適切かどうかを判断してください。

【判断基準】
適切な例:
- ヒーロー、お姫様、動物、忍者、魔法使いなどへの変身
- かっこいい、かわいい、強い、速いなどのポジティブな表現
- スポーツ選手、宇宙飛行士、医者などの職業

不適切な例:
- 暴力的な表現（殺す、傷つける、血、武器など）
- 性的な表現（裸、下着、水着、セクシーなど）
- 差別的・侮辱的な表現
- ホラー・恐怖表現（幽霊、ゾンビ、グロテスクなど）
- アルコール・薬物に関連する表現

【入力テキスト】
{instruction}

【回答形式】
適切な場合: OK
不適切な場合: NG:理由

1行で回答してください。"""


class ContentFilterError(Exception):
    """コンテンツフィルタリングエラー"""
    pass


def check_content_safety_keywords(instruction: str) -> tuple[bool, str]:
    """キーワードベースでコンテンツをチェックする（高速）
    
    Args:
        instruction: ユーザーの変身指示
        
    Returns:
        (is_safe, message) - 安全ならTrue、不適切ならFalseとエラーメッセージ
    """
    # 小文字化・正規化
    normalized = instruction.lower().replace(" ", "").replace("　", "")
    
    # 例外チェック（許可リストに含まれる場合はスキップ）
    for allowed in ALLOWED_EXCEPTIONS:
        if allowed in normalized:
            return True, ""
    
    # NGキーワードチェック
    for keyword in BLOCKED_KEYWORDS:
        if keyword.lower() in normalized:
            logger.warning(f"Content filter (keyword) blocked: '{instruction}' contains '{keyword}'")
            return False, "申し訳ありません。このアプリでは対象のキーワードはご利用いただけません。"
    
    return True, ""


async def check_content_safety_llm(instruction: str) -> tuple[bool, str]:
    """LLMベースでコンテンツをチェックする（より正確）
    
    Args:
        instruction: ユーザーの変身指示
        
    Returns:
        (is_safe, message) - 安全ならTrue、不適切ならFalseとエラーメッセージ
    """
    if not settings.content_filter_llm_enabled:
        return True, ""
    
    try:
        import httpx
        
        prompt = CONTENT_FILTER_PROMPT.format(instruction=instruction)
        
        # プロバイダーに応じてAPIを呼び出し
        if settings.content_filter_provider == "openrouter":
            headers = {
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": settings.content_filter_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
                "temperature": 0.0,
            }
            url = f"{settings.openrouter_base_url}/chat/completions"
        else:
            # selfhost (LiteLLM Proxy)
            headers = {
                "Content-Type": "application/json",
            }
            if settings.litellm_api_key:
                headers["Authorization"] = f"Bearer {settings.litellm_api_key}"
            payload = {
                "model": settings.content_filter_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
                "temperature": 0.0,
            }
            url = f"{settings.litellm_base_url}/chat/completions"
        
        async with httpx.AsyncClient(timeout=settings.content_filter_timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
        
        # レスポンスを解析（Thinkingモデル対応）
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        
        # <think>タグを除去して最終回答のみ取得
        import re
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        
        content_upper = content.upper()
        
        # レスポンス全体から判定キーワードを探す
        # NGパターン（不適切を示すキーワード）
        ng_patterns = ["NG", "不適切", "ふてきせつ", "できません", "使用不可", "禁止", "ブロック"]
        # OKパターン（適切を示すキーワード）
        ok_patterns = ["OK", "適切", "てきせつ", "問題なし", "問題ありません", "使用可能", "大丈夫"]
        
        # 先にNGパターンをチェック（安全側に倒す）
        for ng in ng_patterns:
            if ng.upper() in content_upper or ng in content:
                logger.warning(f"Content filter (LLM) blocked: '{instruction}' - response: {content[:100]}")
                return False, "申し訳ありません。このアプリでは対象のキーワードはご利用いただけません。"
        
        # OKパターンをチェック
        for ok in ok_patterns:
            if ok.upper() in content_upper or ok in content:
                logger.debug(f"Content filter (LLM) passed: '{instruction}'")
                return True, ""
        
        # 判断できない場合は通過させる（誤検知を避けるため）
        logger.warning(f"Content filter (LLM) unclear response: '{content[:100]}' for '{instruction}'")
        return True, ""
            
    except Exception as e:
        # エラー時は通過させる（可用性優先）
        logger.error(f"Content filter (LLM) error: {e}")
        return True, ""


async def check_content_safety(instruction: str) -> tuple[bool, str]:
    """入力が子供向けコンテンツとして適切かチェックする
    
    キーワードチェック → LLMチェック の2段階でフィルタリング
    
    Args:
        instruction: ユーザーの変身指示
        
    Returns:
        (is_safe, message) - 安全ならTrue、不適切ならFalseとエラーメッセージ
    """
    # 1. キーワードベースのチェック（高速）
    is_safe, message = check_content_safety_keywords(instruction)
    if not is_safe:
        return is_safe, message
    
    # 2. LLMベースのチェック（より正確）
    is_safe, message = await check_content_safety_llm(instruction)
    if not is_safe:
        return is_safe, message
    
    return True, ""


def clamp(value: int, min_val: int, max_val: int) -> int:
    """値を範囲内にクランプ"""
    return max(min_val, min(max_val, value))


def calculate_parameter_change(
    tags: TransformationTags,
    stats: SessionStats,
) -> Tuple[int, int, int]:
    """パラメータ変化量を計算する

    Args:
        tags: 変身タグ
        stats: 現在のセッション統計

    Returns:
        (excitement_delta, immersion_delta, challenge_delta) のタプル
    """
    # 難易度設定を取得
    preset = DIFFICULTY_PRESETS.get(stats.difficulty, DIFFICULTY_PRESETS["normal"])

    # ワクワク度計算
    base_excitement = BASE_SPARKLE_LEVEL.get(tags.sparkle_level, 4)
    category_excitement = BASE_CORRUPTION_CATEGORY.get(tags.costume_category, 1)
    excitement_raw = base_excitement + category_excitement

    # なりきり度が高いほどワクワクしやすい（50を基準）
    immersion_factor = stats.immersion / 50.0
    excitement_raw = int(excitement_raw * immersion_factor)

    # 難易度倍率を適用
    excitement_delta = int(excitement_raw * preset.excitement_multiplier)

    # なりきり度変化（ランダム要素あり）
    immersion_delta = random.randint(-5, 10)

    # チャレンジ度計算
    challenge_raw = ADAPTATION_BY_CATEGORY.get(tags.costume_category, 0)
    challenge_delta = int(challenge_raw * preset.challenge_multiplier)

    return excitement_delta, immersion_delta, challenge_delta


def apply_parameter_change(
    stats: SessionStats,
    excitement_delta: int,
    immersion_delta: int,
    challenge_delta: int,
) -> SessionStats:
    """パラメータ変化を適用する

    Args:
        stats: 現在のセッション統計
        excitement_delta: ワクワク度変化量
        immersion_delta: なりきり度変化量
        challenge_delta: チャレンジ度変化量

    Returns:
        更新されたセッション統計（新しいインスタンス）
    """
    new_excitement = clamp(stats.excitement + excitement_delta, 0, 100)
    new_immersion = clamp(stats.immersion + immersion_delta, 0, 100)
    new_challenge = clamp(stats.challenge + challenge_delta, -50, 50)

    return SessionStats(
        session_id=stats.session_id,
        excitement=new_excitement,
        immersion=new_immersion,
        challenge=new_challenge,
        passed_critical_points=stats.passed_critical_points.copy(),
        difficulty=stats.difficulty,
    )


def check_critical_point(
    old_excitement: int,
    new_excitement: int,
    passed_critical_points: list[int],
) -> CriticalPointEvent | None:
    """臨界点イベントをチェックする

    Args:
        old_excitement: 変化前のワクワク度
        new_excitement: 変化後のワクワク度
        passed_critical_points: 既に通過した臨界点リスト

    Returns:
        発火した臨界点イベント、なければNone
    """
    for cp in CRITICAL_POINTS:
        threshold = cp.threshold
        # 閾値を新たに超えた場合のみ発火
        if (
            old_excitement < threshold <= new_excitement
            and threshold not in passed_critical_points
        ):
            return cp
    return None


class GameService:
    """ゲームサービス

    変身ゲームの全パイプラインを統合。
    1. セッション管理
    2. 画像生成 (ComfyUI)
    3. 画像説明 (LLaVA via LiteLLM)
    4. 心境生成 (LLM via LiteLLM)
    """

    def __init__(self) -> None:
        """初期化"""
        self._comfy_client: Optional[ComfyUIClient] = None
        self._image_service: ImageGenerationService = image_service

    def _get_comfy_client(self) -> ComfyUIClient:
        """ComfyUIクライアントを取得 (遅延初期化)"""
        if self._comfy_client is None:
            # ゲーム用ワークフローを使用
            workflow_path = settings.get_workflow_path("instruct_game")
            self._comfy_client = ComfyUIClient(
                base_url=settings.comfyui_base_url,
                workflow_path=workflow_path,
                client_id=settings.comfyui_client_id,
                request_timeout=settings.comfyui_request_timeout,
                poll_interval=settings.comfyui_poll_interval,
            )
        return self._comfy_client

    async def play(self, request: PlayRequest) -> PlayResponse:
        """変身を実行

        Args:
            request: プレイリクエスト

        Returns:
            PlayResponse

        Raises:
            ValueError: リクエストが不正な場合
            GameServiceError: ゲーム実行エラー
        """
        import asyncio

        logger.info(
            "Play request: session=%s, char=%s, instruction=%s",
            request.session_id,
            request.character_id,
            request.instruction[:50],
        )

        # 1. セッション取得または作成
        session = await self._get_or_create_session(request)
        logger.debug("Session: %s", session.session_id)

        before_image = session.current_image
        pronoun = session.character.pronoun if session.character else "僕"

        # 2. 現在の画像を説明 (並列処理の入力として必要)
        logger.info("Describing current image via LLaVA...")
        before_desc = await self._describe_image(before_image)
        logger.debug("Before: %s...", before_desc[:100] if before_desc else "empty")

        # 3. 画像編集プロンプトを生成 (LLM)
        logger.info("Generating image edit prompt via LLM...")
        image_edit_prompt = await self._generate_image_edit_prompt(
            instruction=request.instruction,
            current_description=before_desc,
        )
        logger.info("Image edit prompt: %s", image_edit_prompt[:100])

        # 4. 並列処理: 画像生成と心境生成を同時実行
        # - 画像生成は時間がかかる (5-10秒)
        # - 心境生成は高速 (1-2秒) - LLaVAでの事後説明を省略し、指示から推測
        logger.info(
            "Starting parallel processing: image generation + feeling generation"
        )

        # 推測される変身後の状態（LLaVAを省略して高速化）
        inferred_after_desc = f"{request.instruction}に変身した姿"

        image_task = asyncio.create_task(
            self._generate_image(before_image, image_edit_prompt)
        )
        feeling_task = asyncio.create_task(
            self._generate_feeling(
                before_desc=before_desc,
                after_desc=inferred_after_desc,
                instruction=request.instruction,
                pronoun=pronoun,
            )
        )

        # 両方の完了を待つ
        after_image, feeling_text = await asyncio.gather(image_task, feeling_task)
        logger.info("Parallel processing completed")
        logger.info("Image generated: %d bytes", len(after_image))
        logger.info(
            "Feeling generated: %s...", feeling_text[:100] if feeling_text else "empty"
        )

        # 5. セッション更新
        history = PlayHistory(
            instruction=request.instruction,
            before_image=before_image,
            after_image=after_image,
            before_description=before_desc,
            after_description=inferred_after_desc,
            feeling_text=feeling_text,
        )
        session.update_image(after_image)
        session.add_history(history)
        session_store.update(session)

        # 6. レスポンス構築
        return PlayResponse(
            session_id=session.session_id,
            after_image=base64.b64encode(after_image).decode("utf-8"),
            feeling_text=feeling_text,
            before_description=before_desc,
            after_description=inferred_after_desc,
        )

    async def _get_or_create_session(self, request: PlayRequest) -> GameSession:
        """セッションを取得または作成

        Args:
            request: プレイリクエスト

        Returns:
            GameSession

        Raises:
            ValueError: リクエストが不正な場合
        """
        # 継続プレイの場合
        if request.session_id:
            session = session_store.get(request.session_id)
            if session is None:
                raise ValueError("指定されたセッションが存在しません")
            return session

        # 新規セッションの場合
        character: Optional[Character] = None
        image_bytes: bytes

        if request.character_id:
            # プリセットキャラクター
            character = character_manager.get_by_id(request.character_id)
            if character is None:
                raise ValueError(
                    f"キャラクターが見つかりません: {request.character_id}"
                )
            try:
                image_bytes = character_manager.get_image_bytes(character)
            except FileNotFoundError as e:
                raise ValueError(str(e)) from e

        elif request.character_image:
            # カスタム画像
            try:
                # Data URL形式の場合
                if request.character_image.startswith("data:"):
                    _, encoded = request.character_image.split(",", 1)
                else:
                    encoded = request.character_image
                image_bytes = base64.b64decode(encoded)
            except Exception as e:
                raise ValueError(f"画像のデコードに失敗しました: {e}") from e
        else:
            raise ValueError(
                "character_id, character_image, session_id のいずれかが必要です"
            )

        # セッション作成
        session = session_store.create(
            image=image_bytes,
            character_id=request.character_id,
            character=character,
        )
        return session

    async def _generate_image(self, image_bytes: bytes, instruction: str) -> tuple[bytes, float | None]:
        """画像を生成 (ImageGenerationService経由)

        プロバイダーはIMAGE_PROVIDER環境変数で切り替え:
        - selfhost: ComfyUI (デフォルト)
        - openrouter: OpenRouter API

        Args:
            image_bytes: 入力画像
            instruction: 変身指示

        Returns:
            (生成された画像, API料金USD)

        Raises:
            GameServiceError: 画像生成に失敗した場合
        """
        try:
            result = await self._image_service.edit_image(
                image_bytes=image_bytes,
                prompt=instruction,
            )
            if not result.images:
                raise GameServiceError("画像が生成されませんでした")
            logger.info(f"画像生成完了: provider={result.provider}, cost={result.cost_usd}")
            return result.images[0], result.cost_usd
        except Exception as e:
            raise GameServiceError(f"画像生成エラー: {e}") from e

    async def _generate_image_edit_prompt(
        self,
        instruction: str,
        current_description: str,
    ) -> str:
        """画像編集プロンプトを生成 (LLMService経由)

        プロバイダーはFEELING_PROVIDER環境変数で切り替え:
        - selfhost: LiteLLM Proxy (デフォルト)
        - openrouter: OpenRouter API

        Args:
            instruction: ユーザーの変身指示（日本語）
            current_description: 現在の画像の説明

        Returns:
            生成された英語プロンプト

        Raises:
            GameServiceError: プロンプト生成に失敗した場合
        """
        try:
            result = await llm_service.generate_image_edit_prompt(
                instruction=instruction,
                current_description=current_description,
            )
            logger.info(f"画像編集プロンプト生成完了: provider={result.provider}")
            return result.content
        except Exception as e:
            # プロンプト生成に失敗した場合は、元の指示をそのまま使用
            logger.warning(
                "Prompt generation failed, using original instruction: %s", e
            )
            return instruction

    async def _describe_image(self, image_bytes: bytes) -> str:
        """画像を説明 (LLMService経由)

        プロバイダーはIMAGE_DESCRIPTION_PROVIDER環境変数で切り替え:
        - selfhost: LiteLLM Proxy (デフォルト)
        - openrouter: OpenRouter API

        Args:
            image_bytes: 画像

        Returns:
            画像の説明

        Raises:
            GameServiceError: 画像説明に失敗した場合
        """
        try:
            result = await llm_service.describe_image(
                image_bytes=image_bytes,
                prompt=IMAGE_DESCRIPTION_PROMPT,
            )
            logger.info(f"画像説明完了: provider={result.provider}, cost={result.cost_usd}")
            return result.content
        except (LLMServiceError, LiteLLMClientError) as e:
            raise GameServiceError(f"画像説明エラー: {e}") from e

    async def _generate_feeling(
        self,
        before_desc: str,
        after_desc: str,
        instruction: str,
        pronoun: str,
    ) -> str:
        """心境を生成 (LLMService経由)

        プロバイダーはFEELING_PROVIDER環境変数で切り替え:
        - selfhost: LiteLLM Proxy (デフォルト)
        - openrouter: OpenRouter API

        Args:
            before_desc: 変身前の説明
            after_desc: 変身後の説明
            instruction: 変身指示
            pronoun: 一人称

        Returns:
            心境テキスト

        Raises:
            GameServiceError: 心境生成に失敗した場合
        """
        user_prompt = build_feeling_prompt(
            before_desc=before_desc,
            after_desc=after_desc,
            instruction=instruction,
            pronoun=pronoun,
        )

        try:
            result = await llm_service.generate_feeling(
                system_prompt=FEELING_SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
            logger.info(f"心境生成完了: provider={result.provider}, cost={result.cost_usd}")
            return result.content
        except (LLMServiceError, LiteLLMClientError) as e:
            raise GameServiceError(f"心境生成エラー: {e}") from e

    async def _generate_feeling_stream(
        self,
        before_desc: str,
        after_desc: str,
        instruction: str,
        pronoun: str,
        excitement: int = 0,
        use_kanji: bool = False,
    ) -> AsyncGenerator[str, None]:
        """心境をストリーミング生成 (LLM)

        ワクワク度に応じて心理段階が変化する強化版プロンプトを使用。(T059)

        Args:
            before_desc: 変身前の説明
            after_desc: 変身後の説明
            instruction: 変身指示
            pronoun: 一人称
            excitement: ワクワク度 (0-100)
            use_kanji: 漢字を使用するかどうか

        Yields:
            テキストチャンク
        """
        # ワクワク度に応じた強化版プロンプトを使用
        system_prompt, user_prompt = build_enhanced_feeling_prompt(
            before_desc=before_desc,
            after_desc=after_desc,
            instruction=instruction,
            excitement=excitement,
            pronoun=pronoun,
            use_kanji=use_kanji,
        )

        try:
            async for chunk in llm_service.generate_feeling_stream(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            ):
                yield chunk
        except (LLMServiceError, LiteLLMClientError) as e:
            logger.error(f"心境ストリーミングエラー: {e}")
            yield "(心境生成に失敗しました)"

    async def play_with_stream(
        self,
        session_id: str | None,
        character_id: str | None,
        character_image: str | None,
        instruction: str,
        base_history_id: str | None = None,
        use_kanji: bool = False,
    ) -> AsyncGenerator[StreamEvent, None]:
        """ストリーミング対応の変身を実行

        テキストと画像を **真に並列** で生成し、完了した順にイベントを送信。
        - テキストチャンクは到着次第ストリーミング
        - 画像は完了次第送信（テキスト完了前でも）

        Args:
            session_id: 既存セッションID
            character_id: キャラクターID
            character_image: Base64画像
            instruction: 変身指示
            base_history_id: 履歴からのベース画像ID
            use_kanji: 漢字を使用するかどうか

        Yields:
            StreamEvent: text/image/complete/error イベント
        """
        logger.info(
            "Stream play: session=%s, char=%s, instruction=%s, base_history=%s",
            session_id,
            character_id,
            instruction[:50] if instruction else "",
            base_history_id,
        )

        # 0. コンテンツフィルタリング（子供向けコンテンツの安全性チェック）
        is_safe, error_message = await check_content_safety(instruction)
        if not is_safe:
            yield StreamEvent(
                type="error",
                data={"message": error_message}
            )
            return

        try:
            # 1. セッション取得または作成
            (
                session,
                character,
                before_image,
            ) = await self._get_or_create_session_for_stream(
                session_id=session_id,
                character_id=character_id,
                character_image=character_image,
            )
            logger.debug("Session: %s", session.id if session else "new")

            # 履歴からのベース画像選択
            if base_history_id:
                image_path = await session_store.select_history_as_base(base_history_id)
                if image_path:
                    full_path = settings.history_images_dir.parent / image_path
                    if full_path.exists():
                        before_image = full_path.read_bytes()
                        logger.info("Using history image as base: %s", base_history_id)

            pronoun = character.pronoun if character else "僕"

            # 現在のstatsを取得 (T059: ワクワク度ベースの心理段階)
            current_stats = await session_store.get_or_create_session_stats(session.id)
            current_excitement = current_stats.excitement

            # 2. 現在の画像を説明
            logger.info("Describing current image via LLaVA...")
            before_desc = await self._describe_image(before_image)
            logger.debug("Before: %s...", before_desc[:100] if before_desc else "empty")

            # 2.1 セッション属性を取得（プロンプトに反映）
            attributes = await session_store.get_session_attribute_texts(session.id)
            attribute_context = ""
            if attributes:
                attribute_context = (
                    "\n\n【対象キャラクターの属性】\n"
                    + "\n".join(f"- {attr}" for attr in attributes)
                    + "\n（これらの属性を画像生成時に考慮してください）"
                )
                logger.info(f"Session attributes: {attributes}")

            # 3. 画像編集プロンプトを生成
            logger.info("Generating image edit prompt...")
            image_edit_prompt = await self._generate_image_edit_prompt(
                instruction=instruction + attribute_context,
                current_description=before_desc,
            )

            # 4. 真の並列処理: asyncio.Queue を使ってイベントを統合
            inferred_after_desc = f"{instruction}に変身した姿"

            # イベントキューを作成
            event_queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()

            # テキスト収集用
            text_chunks: list[str] = []

            async def text_producer():
                """テキストチャンクをキューに送信"""
                try:
                    async for chunk in self._generate_feeling_stream(
                        before_desc=before_desc,
                        after_desc=inferred_after_desc,
                        instruction=instruction,
                        pronoun=pronoun,
                        excitement=current_excitement,
                        use_kanji=use_kanji,
                    ):
                        text_chunks.append(chunk)
                        await event_queue.put(
                            StreamEvent(type="text", data={"chunk": chunk})
                        )
                except Exception as e:
                    logger.error(f"Text streaming error: {e}")
                finally:
                    await event_queue.put(StreamEvent(type="_text_done", data={}))

            async def image_producer():
                """画像生成完了をキューに送信"""
                try:
                    after_image, image_cost = await self._generate_image(
                        before_image, image_edit_prompt
                    )
                    logger.info("Image generated: %d bytes, cost: %s", len(after_image), image_cost)
                    await event_queue.put(
                        StreamEvent(type="_image_ready", data={"image": after_image, "cost": image_cost})
                    )
                except Exception as e:
                    logger.error(f"Image generation error: {e}")
                    await event_queue.put(
                        StreamEvent(type="_image_error", data={"error": str(e)})
                    )

            # 両方のプロデューサーを並列開始
            text_task = asyncio.create_task(text_producer())
            image_task = asyncio.create_task(image_producer())

            # 内部状態
            text_done = False
            image_data: bytes | None = None
            image_cost: float | None = None
            image_error: str | None = None

            # キューからイベントを消費
            while True:
                event = await event_queue.get()
                if event is None:
                    break

                if event.type == "text":
                    # テキストチャンクをそのまま送信
                    yield event
                elif event.type == "_text_done":
                    text_done = True
                elif event.type == "_image_ready":
                    image_data = event.data["image"]
                    image_cost = event.data.get("cost")
                elif event.type == "_image_error":
                    image_error = event.data["error"]

                # 両方完了したらループを抜ける
                if text_done and (image_data is not None or image_error is not None):
                    break

            # タスクの完了を待つ
            await asyncio.gather(text_task, image_task, return_exceptions=True)

            # エラーチェック
            if image_error:
                raise GameServiceError(f"画像生成エラー: {image_error}")
            if image_data is None:
                raise GameServiceError("画像が生成されませんでした")

            full_text = "".join(text_chunks)

            # 5. 履歴に追加 (DatabaseSessionStore使用)
            history = await session_store.add_history(
                session_id=session.id,
                instruction=instruction,
                image_data=image_data,
                feeling_text=full_text,
                before_description=before_desc,
                after_description=inferred_after_desc,
            )

            # 5.2. パラメータ計算と更新 (T015, T016)
            stats = await session_store.get_or_create_session_stats(session.id)
            old_excitement = stats.excitement

            # デフォルトのタグを使用（tag_classifier削除後）
            default_tags = TransformationTag(
                history_id=history.id,
                costume_category="other",
                sparkle_level="medium",
                age_impression="unknown",
            )
            excitement_delta, immersion_delta, challenge_delta = (
                calculate_parameter_change(default_tags, stats)
            )
            new_stats = apply_parameter_change(
                stats, excitement_delta, immersion_delta, challenge_delta
            )

            # 臨界点チェック
            critical_event = check_critical_point(
                old_excitement,
                new_stats.excitement,
                new_stats.passed_critical_points,
            )

            # 臨界点を通過した場合は記録
            if critical_event:
                new_stats.passed_critical_points.append(critical_event.threshold)

            # 更新をDBに保存
            await session_store.update_session_stats(new_stats)

            # statsイベントを送信 (T016)
            yield StreamEvent(
                type="stats",
                data={
                    "excitement": new_stats.excitement,
                    "immersion": new_stats.immersion,
                    "challenge": new_stats.challenge,
                    "excitement_delta": excitement_delta,
                    "immersion_delta": immersion_delta,
                    "challenge_delta": challenge_delta,
                },
            )

            # 臨界点イベントを送信 (T033)
            if critical_event:
                # ランダムな特別セリフを取得
                speech = get_critical_speech(critical_event.threshold)
                yield StreamEvent(
                    type="critical",
                    data={
                        "threshold": critical_event.threshold,
                        "name": critical_event.name,
                        "effect_type": critical_event.effect_type,
                        "speech": speech,
                    },
                )

            # 6. 変身回数をインクリメント
            transformation_count = await session_store.increment_transformation_count(
                session.id
            )

            # 6.1 エンディング判定 (T048)
            tag_counts = await session_store.get_session_tag_counts(session.id)
            achieved_ending_ids = await session_store.get_achieved_ending_ids()
            ending_result = judge_ending(
                new_stats, transformation_count, tag_counts, achieved_ending_ids
            )

            if ending_result.triggered and ending_result.ending:
                # 初達成なら保存
                if ending_result.is_new:
                    await session_store.save_achieved_ending(
                        ending_result.ending_id,
                        session.id,
                    )
                # エンディングイベントを送信
                yield StreamEvent(
                    type="ending",
                    data={
                        "ending_id": ending_result.ending_id,
                        "title": ending_result.ending.title,
                        "description": ending_result.ending.description,
                        "final_speech": ending_result.ending.final_speech,
                        "summary": ending_result.ending.summary,
                        "is_new": ending_result.is_new,
                    },
                )

            # 7. 現在の画像パスを更新
            await session_store.update_session(
                session_id=session.id,
                current_image_path=history.image_path,
            )

            # 8. 画像イベントを送信
            image_b64 = base64.b64encode(image_data).decode("utf-8")
            yield StreamEvent(
                type="image",
                data={"image": image_b64, "history_id": history.id},
            )

            # 8.5 コストイベントを送信（API料金がある場合）
            if image_cost is not None and image_cost > 0:
                yield StreamEvent(
                    type="cost",
                    data={"cost_usd": image_cost, "provider": "openrouter"},
                )

            # 9. 完了イベント
            yield StreamEvent(
                type="complete",
                data={
                    "session_id": session.id,
                    "transformation_count": transformation_count,
                    "before_desc": before_desc,
                    "after_desc": inferred_after_desc,
                },
            )

        except Exception as e:
            logger.exception("Stream play error: %s", e)
            yield StreamEvent(type="error", data={"message": str(e)})

    async def _get_or_create_session_for_stream(
        self,
        session_id: str | None,
        character_id: str | None,
        character_image: str | None,
    ) -> tuple[PersistedSession, Character | None, bytes]:
        """ストリーミング用にセッションを取得または作成

        Args:
            session_id: 既存セッションID
            character_id: キャラクターID
            character_image: Base64画像

        Returns:
            (セッション, キャラクター, 現在の画像バイナリ)
        """
        character: Character | None = None
        image_bytes: bytes

        # 継続プレイの場合
        if session_id:
            session = await session_store.get_session_by_id(session_id)
            if session is None:
                raise ValueError("指定されたセッションが存在しません")

            # キャラクター情報を取得
            if session.character_id:
                character = character_manager.get_by_id(session.character_id)

            # 現在の画像を読み込み
            if session.current_image_path:
                # BASE_DIRからの相対パスとして解決
                from .config import BASE_DIR
                image_path = BASE_DIR / session.current_image_path
                if image_path.exists():
                    image_bytes = image_path.read_bytes()
                else:
                    # ファイルがない場合、元のキャラクター画像を使用
                    if character:
                        image_bytes = character_manager.get_image_bytes(character)
                    else:
                        raise ValueError(f"セッションの画像が見つかりません: {image_path}")
            else:
                # current_image_pathがない場合
                if character:
                    image_bytes = character_manager.get_image_bytes(character)
                else:
                    raise ValueError("セッションに画像がありません")

            return session, character, image_bytes

        # 新規セッションの場合
        if character_id:
            character = character_manager.get_by_id(character_id)
            if character is None:
                raise ValueError(f"キャラクターが見つかりません: {character_id}")
            try:
                image_bytes = character_manager.get_image_bytes(character)
            except FileNotFoundError as e:
                raise ValueError(str(e)) from e
            # 初期画像のパスを保存
            initial_image_path = character.image_path

        elif character_image:
            try:
                if character_image.startswith("data:"):
                    _, encoded = character_image.split(",", 1)
                else:
                    encoded = character_image
                image_bytes = base64.b64decode(encoded)
            except Exception as e:
                raise ValueError(f"画像のデコードに失敗しました: {e}") from e
            # カスタム画像の場合、パスは後で設定
            initial_image_path = ""
        else:
            # アクティブなセッションを探す
            session = await session_store.get_active_session()
            if session:
                if session.character_id:
                    character = character_manager.get_by_id(session.character_id)
                if session.current_image_path:
                    from .config import BASE_DIR
                    image_path = BASE_DIR / session.current_image_path
                    if image_path.exists():
                        return session, character, image_path.read_bytes()
                if character:
                    return (
                        session,
                        character,
                        character_manager.get_image_bytes(character),
                    )
            raise ValueError(
                "character_id, character_image, session_id のいずれかが必要です"
            )

        # セッション作成
        session = await session_store.create_session(
            image_path=initial_image_path,
            character_id=character_id,
        )
        return session, character, image_bytes

    async def improve_quality_with_stream(
        self,
        session_id: str,
    ) -> AsyncGenerator[StreamEvent, None]:
        """画質改善をストリーミングで実行

        劣化した画像を、初期画像+現在の状態説明で再生成することで
        画質をリセットする。

        処理フロー:
        1. 現在の画像の説明を生成
        2. キャラクターの初期画像を取得
        3. 初期画像 + 説明に基づく指示で再生成
        4. 履歴に追加（instruction: "画質改善"）

        Args:
            session_id: セッションID

        Yields:
            StreamEvent: ストリーミングイベント
        """
        try:
            # 0. 処理開始を通知
            yield StreamEvent(type="status", data={"message": "画質改善を開始..."})

            # 1. セッション取得
            session = await session_store.get_session_by_id(session_id)
            if session is None:
                raise GameServiceError(f"セッションが見つかりません: {session_id}")

            # 2. 現在の画像を取得
            current_image_bytes: bytes | None = None
            if session.current_image_path:
                image_path = (
                    settings.history_images_dir.parent / session.current_image_path
                )
                if image_path.exists():
                    current_image_bytes = image_path.read_bytes()

            if current_image_bytes is None:
                raise GameServiceError("現在の画像が見つかりません")

            # 3. キャラクター情報取得
            character: Optional[Character] = None
            if session.character_id:
                character = character_manager.get_by_id(session.character_id)

            pronoun = character.pronoun if character else "僕"

            # 4. 現在の画像を説明
            yield StreamEvent(type="status", data={"message": "画像を分析中..."})

            current_description = await self._describe_image(current_image_bytes)
            logger.info(f"Current description: {current_description[:100]}...")

            # 5. 初期画像を取得
            initial_image_bytes: bytes | None = None
            if character:
                try:
                    initial_image_bytes = character_manager.get_image_bytes(character)
                except FileNotFoundError:
                    pass

            if initial_image_bytes is None:
                raise GameServiceError("初期画像が見つかりません")

            # 6. 画質改善プロンプトを生成（性別維持を明示）
            improve_instruction = (
                f"Recreate this FEMALE character with the exact same outfit, pose, and body type. "
                f"This is a female anime character - DO NOT change the gender. "
                f"Keep the exact same feminine body shape, hairstyle, and face. "
                f"Description of current outfit: {current_description}. "
                f"Make sure colors are vibrant and natural, not brownish or yellowish. "
                f"High quality, detailed anime illustration of a young woman."
            )

            yield StreamEvent(type="status", data={"message": "画質改善中..."})

            # 7. 新しい画像を生成
            new_image, image_cost = await self._generate_image(
                initial_image_bytes, improve_instruction
            )
            logger.info(f"Quality improvement done: {len(new_image)} bytes")

            # 8. 履歴に追加
            instruction = "🎨 画質改善"
            history = await session_store.add_history(
                session_id=session_id,
                instruction=instruction,
                image_data=new_image,
                feeling_text="(画質改善)",
                before_description="",
                after_description=current_description,
            )

            # 9. 現在の画像パスを更新
            await session_store.update_session(
                session_id=session_id,
                current_image_path=history.image_path,
            )

            # 10. 結果を送信
            image_b64 = base64.b64encode(new_image).decode("utf-8")
            yield StreamEvent(
                type="image",
                data={"image": image_b64, "history_id": history.id},
            )

            # コストイベント
            if image_cost is not None and image_cost > 0:
                yield StreamEvent(
                    type="cost",
                    data={"cost_usd": image_cost, "provider": "openrouter"},
                )

            # 完了イベント
            yield StreamEvent(
                type="complete",
                data={"session_id": session_id, "improved": True},
            )

        except Exception as e:
            logger.exception("Quality improvement error: %s", e)
            yield StreamEvent(type="error", data={"message": str(e)})


# グローバルサービスインスタンス
game_service = GameService()
