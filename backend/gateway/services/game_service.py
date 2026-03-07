"""
ゲームサービス

着せ替えゲームのコアロジックを実装。
ComfyUI (画像生成) + LiteLLM (画像説明・心境生成) を統合。
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncGenerator, Optional, Tuple

from .characters import character_manager
from .comfy import ComfyUIClient
from ..settings.config import settings, BASE_DIR
from .image_generation import image_service, ImageGenerationService
from .llm_service import llm_service, LLMServiceError
from .litellm_client import LiteLLMClientError
from ..models import (
    Character,
    GameSession,
    PlayHistory,
    PlayRequest,
    PlayResponse,
    PersistedSession,
    SessionStats,
    DIFFICULTY_PRESETS,
    CRITICAL_POINTS,
    CriticalPointEvent,
)
from .prompts import (
    FEELING_SYSTEM_PROMPT,
    build_feeling_prompt,
    build_enhanced_feeling_prompt,
    get_critical_speech,
)
from .reality_prompts import (
    build_reality_feeling_prompt,
    build_reality_edit_prompt,
    get_reality_edit_system_prompt,
)
from .action_prompts import (
    build_action_prompt,
    build_action_image_edit_prompt,
    get_action_image_edit_system_prompt,
    get_action_novelai_prompt_generation_system,
)
from .self_mode_prompts import build_self_mode_feeling_prompt
from .session import session_store
from .tag_classifier import classify_tags, TransformationTags
from .endings import judge_ending
from ..routes.achievements_router import (
    check_achievements,
    save_user_achievement,
    get_user_achievements,
    get_global_stats,
    update_achievement_counts,
)
from .achievement_classifier import classify_for_achievement
from .anlas_service import get_anlas_balance
from ..consts.language import normalize_language

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

# 露出度別の基本開花度増加値
BASE_CORRUPTION_EXPOSURE = {
    "high": 8,
    "medium": 4,
    "low": 2,
}

# 衣装カテゴリ別の追加開花度
BASE_CORRUPTION_CATEGORY = {
    "underwear": 5,  # 下着系は高い
    "swimsuit": 4,  # 水着系
    "cosplay": 3,  # コスプレ系
    "maid": 2,  # メイド系
    "gothic_lolita": 2,  # ゴスロリ
    "sports": 1,  # スポーツ系
    "uniform": 1,  # 制服系
    "dress": 1,  # ドレス系
    "other": 1,  # その他
}

# 順応度変化の衣装カテゴリマッピング
ADAPTATION_BY_CATEGORY = {
    "maid": 3,
    "gothic_lolita": 3,
    "dress": 2,
    "cosplay": 2,
    "uniform": 1,
    "sports": 1,
    "swimsuit": -1,
    "underwear": -2,
    "other": 0,
}


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
        (bloom_delta, shame_delta, adaptation_delta) のタプル
    """
    # 難易度設定を取得
    preset = DIFFICULTY_PRESETS.get(stats.difficulty, DIFFICULTY_PRESETS["normal"])

    # 開花度計算
    base_bloom = BASE_CORRUPTION_EXPOSURE.get(tags.exposure_level, 4)
    category_bloom = BASE_CORRUPTION_CATEGORY.get(tags.costume_category, 1)
    bloom_raw = base_bloom + category_bloom

    # 羞恥心が高いほど堕落しやすい（50を基準）
    shame_factor = stats.shame / 50.0
    bloom_raw = int(bloom_raw * shame_factor)

    # 難易度倍率を適用
    bloom_delta = int(bloom_raw * preset.bloom_multiplier)

    # 羞恥心変化（ランダム要素あり）
    shame_delta = random.randint(-5, 10)

    # 順応度計算
    adaptation_raw = ADAPTATION_BY_CATEGORY.get(tags.costume_category, 0)
    adaptation_delta = int(adaptation_raw * preset.adaptation_multiplier)

    return bloom_delta, shame_delta, adaptation_delta


def apply_parameter_change(
    stats: SessionStats,
    bloom_delta: int,
    shame_delta: int,
    adaptation_delta: int,
) -> SessionStats:
    """パラメータ変化を適用する

    Args:
        stats: 現在のセッション統計
        bloom_delta: 開花度変化量
        shame_delta: 羞恥心変化量
        adaptation_delta: 順応度変化量

    Returns:
        更新されたセッション統計（新しいインスタンス）
    """
    new_bloom = clamp(stats.bloom + bloom_delta, 0, 100)
    new_shame = clamp(stats.shame + shame_delta, 0, 100)
    new_adaptation = clamp(stats.adaptation + adaptation_delta, -50, 50)

    return SessionStats(
        session_id=stats.session_id,
        bloom=new_bloom,
        shame=new_shame,
        adaptation=new_adaptation,
        passed_critical_points=stats.passed_critical_points.copy(),
        difficulty=stats.difficulty,
        nsfw_mode=stats.nsfw_mode,
        enable_prompt_preview=stats.enable_prompt_preview,
    )


def check_critical_point(
    old_bloom: int,
    new_bloom: int,
    passed_critical_points: list[int],
) -> CriticalPointEvent | None:
    """臨界点イベントをチェックする

    Args:
        old_bloom: 変化前の開花度
        new_bloom: 変化後の開花度
        passed_critical_points: 既に通過した臨界点リスト

    Returns:
        発火した臨界点イベント、なければNone
    """
    for cp in CRITICAL_POINTS:
        threshold = cp.threshold
        # 閾値を新たに超えた場合のみ発火
        if (
            old_bloom < threshold <= new_bloom
            and threshold not in passed_critical_points
        ):
            return cp
    return None


class GameService:
    """ゲームサービス

    着せ替えゲームの全パイプラインを統合。
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

    def _load_custom_session_metadata(self, session_id: str) -> dict:
        metadata_path = (
            settings.history_images_dir / "custom" / f"session_{session_id}.json"
        )
        if not metadata_path.exists():
            return {}
        try:
            return json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    @staticmethod
    def _build_initial_prompt(
        gender: str,
        character: Optional["Character"] = None,
        self_profile: dict | None = None,
        base_tags: str = "",
    ) -> str:
        """NovelAI Opusモードの初回用初期プロンプトを構築

        履歴がない初回ターンで、LLMへの性別・外見情報を提供する。
        self_modeではプレイヤー名はNovelAIタグのノイズとなるため含めない。
        base_tagsがあればDanbooruタグ形式の英語タグを優先的に使用する。

        Args:
            gender: 性別 ("man" or "woman")
            character: キャラクターオブジェクト
            self_profile: 自分自身モードのプロフィール
            base_tags: Danbooru形式の外見タグ (直接指定)

        Returns:
            NovelAIタグ形式の初期プロンプト
        """
        gender_tag = "1boy" if gender == "man" else "1girl"
        # 直接指定のbase_tagsを最優先
        if base_tags:
            char_tags = base_tags
        elif character and not self_profile:
            char_tags = character.base_tags or character.description
        else:
            char_tags = ""
        return (
            f"masterpiece, best quality, very aesthetic, "
            f"{gender_tag}, solo, {char_tags}"
        ).rstrip(", ")

    @staticmethod
    def _enhance_novelai_prompt(prompt: str, nsfw_mode: bool) -> str:
        """NovelAI向けに品質タグとNSFWキーワードを付与する

        Args:
            prompt: 元のプロンプト
            nsfw_mode: NSFWモードの有無

        Returns:
            品質タグ付きのプロンプト
        """
        from .prompts import enhance_prompt_for_novelai

        result = enhance_prompt_for_novelai(prompt)
        if nsfw_mode and "nsfw" not in result.lower():
            result = result + ", nsfw"
        return result

    @staticmethod
    def _resolve_image_path(image_path_str: str) -> Path | None:
        """Resolve an image path by trying data-relative then BASE_DIR-relative.

        Args:
            image_path_str: relative image path stored in session

        Returns:
            Resolved absolute Path if found, None otherwise
        """
        from ..settings.config import BASE_DIR

        # data-relative (history_images etc.)
        candidate = settings.history_images_dir.parent / image_path_str
        if candidate.exists():
            return candidate

        # BASE_DIR-relative (character images etc.)
        candidate = BASE_DIR / image_path_str
        if candidate.exists():
            return candidate

        return None

    async def play(self, request: PlayRequest) -> PlayResponse:
        """着せ替えを実行

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
        before_desc, _desc_cost = await self._describe_image(before_image)
        logger.debug("Before: %s...", before_desc[:100] if before_desc else "empty")

        # 3. 画像編集プロンプトを生成 (LLM)
        logger.info("Generating image edit prompt via LLM...")
        image_edit_prompt, _prompt_cost = await self._generate_image_edit_prompt(
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
        (
            (after_image, _img_cost, _img_seed),
            (feeling_text, _feel_cost),
        ) = await asyncio.gather(image_task, feeling_task)
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

    @staticmethod
    async def _get_anlas_event() -> StreamEvent | None:
        """Get Anlas balance as an SSE event (NovelAI provider only)."""
        if settings.image_provider != "novelai":
            return None
        try:
            balance = await get_anlas_balance()
            return StreamEvent(
                type="anlas",
                data={
                    "fixed_anlas": balance.fixed_anlas,
                    "purchased_anlas": balance.purchased_anlas,
                    "total_anlas": balance.total_anlas,
                },
            )
        except Exception as e:
            logger.warning("Failed to get Anlas balance: %s", e)
            return None

    async def _generate_image(
        self,
        image_bytes: bytes,
        instruction: str,
        costume_image_bytes: bytes | None = None,
        nsfw_mode: bool = False,
        mask_bytes: bytes | None = None,
        inpaint_strength: float | None = None,
        inpaint_noise: float | None = None,
        negative_prompt: str | None = None,
        character_references: list[dict] | None = None,
        seed: int | None = None,
        characters: list[dict] | None = None,
    ) -> tuple[bytes, float | None, int | None]:
        """画像を生成 (ImageGenerationService経由)

        プロバイダーはIMAGE_PROVIDER環境変数で切り替え:
        - selfhost: ComfyUI (デフォルト)
        - openrouter: OpenRouter API

        Args:
            image_bytes: 入力画像
            instruction: 着せ替え指示
            costume_image_bytes: 参照衣装画像（オプション）
            nsfw_mode: NSFWモード (Trueの場合NSFWワークフローを使用)
            character_references: 精密参照画像パラメータのリスト（NovelAI専用）
            seed: 画像生成seed値（未指定時はNovelAIプロバイダーでランダム生成）
            characters: V4キャラクタープロンプト分離用（NovelAI専用）

        Returns:
            (生成された画像, API料金USD, seed値)

        Raises:
            GameServiceError: 画像生成に失敗した場合
        """
        try:
            # NSFWモードに応じてワークフローを選択
            workflow_name = "instruct_game_nsfw" if nsfw_mode else "instruct_game"
            workflow_path = settings.get_workflow_path(workflow_name)
            logger.info(f"Using workflow: {workflow_name} ({workflow_path})")

            result = await self._image_service.edit_image(
                image_bytes=image_bytes,
                prompt=instruction,
                reference_image_bytes=costume_image_bytes,
                mask_bytes=mask_bytes,
                workflow_path=workflow_path,
                negative_prompt=negative_prompt,
                inpaint_strength=inpaint_strength,
                inpaint_noise=inpaint_noise,
                nsfw_mode=nsfw_mode,
                character_references=character_references,
                seed=seed,
                characters=characters,
            )
            if not result.images:
                raise GameServiceError("画像が生成されませんでした")
            logger.info(
                f"画像生成完了: provider={result.provider}, cost={result.cost_usd}, seed={result.seed}"
            )
            return result.images[0], result.cost_usd, result.seed
        except Exception as e:
            raise GameServiceError(f"画像生成エラー: {e}") from e

    async def _generate_surroundings_image(
        self,
        instruction: str,
        before_description: str,
        after_description: str,
        nsfw_mode: bool = False,
        include_people: bool = False,
        is_reality_change: bool = False,
        reality_alter_descriptions: list[str] | None = None,
    ) -> tuple[bytes | None, float | None, int | None]:
        """Generate surroundings image (NovelAI txt2img, US2)

        Args:
            instruction: Action instruction
            before_description: Description before the action
            after_description: Description after the action
            nsfw_mode: NSFW mode
            include_people: Include reactive bystanders in the image
            is_reality_change: Reality-change mode (bystanders are indifferent)
            reality_alter_descriptions: Active reality alteration texts

        Returns:
            (image bytes, API cost USD, seed) or (None, None, None) on failure
        """
        if settings.image_provider != "novelai":
            logger.info("Surroundings image generation is only supported with NovelAI")
            return None, None, None

        try:
            # LLM でプロンプト生成
            from .action_prompts import (
                get_surroundings_image_prompt_system,
                build_surroundings_image_user_prompt,
            )

            system_prompt = get_surroundings_image_prompt_system(
                nsfw_mode=nsfw_mode,
                include_people=include_people,
                is_reality_change=is_reality_change,
                reality_alter_descriptions=reality_alter_descriptions,
            )
            user_prompt = build_surroundings_image_user_prompt(
                instruction=instruction,
                before_description=before_description,
                after_description=after_description,
                include_people=include_people,
                is_reality_change=is_reality_change,
                reality_alter_descriptions=reality_alter_descriptions,
            )

            scenery_prompt_result = await llm_service.generate_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            scenery_prompt = scenery_prompt_result.content.strip()
            logger.info(
                "Surroundings prompt generated: %d chars",
                len(scenery_prompt),
            )

            # Image generation: portrait for bystanders, landscape for bg-only
            scenery_size = "portrait" if include_people else "landscape"
            result = await self._image_service.generate_scenery(
                prompt=scenery_prompt,
                size=scenery_size,
                nsfw_mode=nsfw_mode,
                include_people=include_people,
            )

            if not result.images:
                logger.warning("Surroundings image generation returned no images")
                return None, None, None

            logger.info(
                "Surroundings image generated: %d bytes, seed=%s",
                len(result.images[0]),
                result.seed,
            )
            return result.images[0], result.cost_usd, result.seed

        except Exception as e:
            logger.warning("Surroundings image generation failed: %s", e)
            return None, None, None

    async def _generate_image_edit_prompt(
        self,
        instruction: str,
        current_description: str,
        preserve_elements: list[str] | None = None,
        change_scope: str = "full",
        custom_preserve_text: str = "",
        nsfw_mode: bool = False,
    ) -> tuple[str, float | None]:
        """画像編集プロンプトを生成 (LLMService経由)

        プロバイダーはFEELING_PROVIDER環境変数で切り替え:
        - selfhost: LiteLLM Proxy (デフォルト)
        - openrouter: OpenRouter API

        Args:
            instruction: ユーザーの着せ替え指示（日本語）
            current_description: 現在の画像の説明
            preserve_elements: 保持する要素のリスト
            change_scope: 変更対象 (full, upper, lower, accessories, shoes)
            custom_preserve_text: カスタム保持指示（自由記述）
            nsfw_mode: NSFWモードかどうか

        Returns:
            (生成された英語プロンプト, コスト(USD))

        Raises:
            GameServiceError: プロンプト生成に失敗した場合
        """
        try:
            print("-----------")
            print(instruction, current_description)
            result = await llm_service.generate_image_edit_prompt(
                instruction=instruction,
                current_description=current_description,
                preserve_elements=preserve_elements,
                change_scope=change_scope,
                custom_preserve_text=custom_preserve_text,
                provider_override=settings.image_provider,
                nsfw_mode=nsfw_mode,
            )
            logger.info(
                f"画像編集プロンプト生成完了: provider={result.provider}, cost={result.cost_usd}"
            )
            print(result.content)
            return result.content, result.cost_usd
        except Exception as e:
            # プロンプト生成に失敗した場合は、元の指示をそのまま使用
            logger.warning(
                "Prompt generation failed, using original instruction: %s", e
            )
            return instruction, None

    def _merge_prompts(self, base_prompt: str, override_prompt: str) -> str:
        """ベースプロンプトとオーバーライドプロンプトをマージする (T009)

        NovelAI用タグプロンプトを結合する。
        オーバーライドプロンプトのタグをベースプロンプトに追加する。

        Args:
            base_prompt: LLMで生成されたベースプロンプト
            override_prompt: ユーザー指定のオーバーライドプロンプト

        Returns:
            マージされたプロンプト
        """
        if not override_prompt:
            return base_prompt
        if not base_prompt:
            return override_prompt

        # カンマ区切りのタグとして結合
        # オーバーライドプロンプトを先頭に追加（優先度高い）
        merged = f"{override_prompt.strip()}, {base_prompt.strip()}"
        return merged

    async def _describe_image(
        self, image_bytes: bytes, nsfw_mode: bool = False
    ) -> tuple[str, float | None]:
        """画像を説明 (LLMService経由)

        プロバイダーはIMAGE_DESCRIPTION_PROVIDER環境変数で切り替え:
        - selfhost: LiteLLM Proxy (デフォルト)
        - openrouter: OpenRouter API

        Args:
            image_bytes: 画像
            nsfw_mode: NSFWモードかどうか

        Returns:
            (画像の説明, コスト(USD))

        Raises:
            GameServiceError: 画像説明に失敗した場合
        """
        from .prompts import get_image_description_prompt

        prompt = get_image_description_prompt(nsfw_mode)
        try:
            result = await llm_service.describe_image(
                image_bytes=image_bytes,
                prompt=prompt,
            )
            logger.info(
                f"画像説明完了: provider={result.provider}, cost={result.cost_usd}"
            )
            return result.content, result.cost_usd
        except (LLMServiceError, LiteLLMClientError) as e:
            raise GameServiceError(f"画像説明エラー: {e}") from e

    async def _generate_feeling(
        self,
        before_desc: str,
        after_desc: str,
        instruction: str,
        pronoun: str,
    ) -> tuple[str, float | None]:
        """心境を生成 (LLMService経由)

        プロバイダーはFEELING_PROVIDER環境変数で切り替え:
        - selfhost: LiteLLM Proxy (デフォルト)
        - openrouter: OpenRouter API

        Args:
            before_desc: 着せ替え前の説明
            after_desc: 着せ替え後の説明
            instruction: 着せ替え指示
            pronoun: 一人称

        Returns:
            (心境テキスト, コスト(USD))

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
            logger.info(
                f"心境生成完了: provider={result.provider}, cost={result.cost_usd}"
            )
            return result.content, result.cost_usd
        except (LLMServiceError, LiteLLMClientError) as e:
            raise GameServiceError(f"心境生成エラー: {e}") from e

    async def _generate_feeling_stream(
        self,
        before_desc: str,
        after_desc: str,
        instruction: str,
        pronoun: str,
        bloom: int = 0,
        attributes: list[str] | None = None,
        nsfw_mode: bool = False,
        transformation_count: int = 0,
        language: str = "ja",
        personality: str = "",
        description: str = "",
        used_openings: list[str] | None = None,
    ) -> AsyncGenerator[str, None]:
        """LLM経由で心境テキストをストリーミング生成する。

        開花度に応じた心理段階プロンプト (T059) を使用し、
        性格が指定されている場合は注入する (US2)。

        Args:
            before_desc: 着せ替え前の説明
            after_desc: 着せ替え後の説明
            instruction: 着せ替え指示
            pronoun: 一人称
            bloom: 開花度 (0-100)
            attributes: キャラクター属性リスト
            nsfw_mode: NSFWモードの有無
            transformation_count: 現在の変身回数（初回判定用）
            language: 出力言語
            personality: キャラクターの性格テキスト
            description: キャラクターの説明テキスト
            used_openings: 最近使用した書き出し（重複排除用）

        Yields:
            テキストチャンク
        """
        # 開花度に応じた強化版プロンプトを使用
        system_prompt, user_prompt = build_enhanced_feeling_prompt(
            before_desc=before_desc,
            after_desc=after_desc,
            instruction=instruction,
            bloom=bloom,
            pronoun=pronoun,
            attributes=attributes,
            nsfw_mode=nsfw_mode,
            transformation_count=transformation_count,
            personality=personality,
            description=description,
            used_openings=used_openings,
        )
        from .conversation import get_language_rules

        system_prompt = f"{system_prompt}\n\n{get_language_rules(language)}"

        async for chunk in self._stream_feeling(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            language=language,
            error_context="心境ストリーミングエラー",
        ):
            yield chunk

    async def _stream_feeling(
        self,
        system_prompt: str,
        user_prompt: str,
        language: str,
        error_context: str = "Feeling stream error",
    ) -> AsyncGenerator[str, None]:
        """Common helper: stream feeling text from LLM with error handling.

        Args:
            system_prompt: system prompt (language rules already appended by caller)
            user_prompt: user prompt
            language: output language for fallback message
            error_context: log message prefix on error

        Yields:
            text chunks
        """
        try:
            async for chunk in llm_service.generate_feeling_stream(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            ):
                yield chunk
        except (LLMServiceError, LiteLLMClientError) as e:
            logger.error(f"{error_context}: {e}")
            if language == "en":
                yield "(Failed to generate inner monologue)"
            else:
                yield "(心境生成に失敗しました)"

    async def _generate_self_mode_feeling_stream(
        self,
        before_desc: str,
        after_desc: str,
        instruction: str,
        self_profile: dict,
        nsfw_mode: bool = False,
        language: str = "ja",
    ) -> AsyncGenerator[str, None]:
        """自分自身モードの心境テキストをユーザーの性格プロフィールでストリーミング生成する。

        心理段階やパラメータ依存なし (R-007)。

        Args:
            before_desc: 着せ替え前の説明
            after_desc: 着せ替え後の説明
            instruction: 着せ替え指示
            self_profile: パース済みの自分自身プロフィール辞書
            nsfw_mode: NSFWモードの有無
            language: 出力言語

        Yields:
            テキストチャンク
        """
        system_prompt, user_prompt = build_self_mode_feeling_prompt(
            before_desc=before_desc,
            after_desc=after_desc,
            instruction=instruction,
            self_profile=self_profile,
            nsfw_mode=nsfw_mode,
        )
        from .conversation import get_language_rules

        system_prompt = f"{system_prompt}\n\n{get_language_rules(language)}"

        async for chunk in self._stream_feeling(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            language=language,
            error_context="自分自身モード心境ストリーミングエラー",
        ):
            yield chunk

    async def _generate_reality_edit_prompt(
        self,
        instruction: str,
        current_description: str,
        nsfw_mode: bool = False,
        image_provider: str = "qwen",
    ) -> tuple[str, float | None]:
        """現実改変用画像編集プロンプトを生成 (LLMService経由)

        Args:
            instruction: ユーザーの現実改変指示（日本語）
            current_description: 現在の画像の説明
            nsfw_mode: NSFWモードかどうか
            image_provider: 画像生成プロバイダー ("qwen" or "novelai")

        Returns:
            (生成された英語プロンプト, コスト(USD))

        Raises:
            GameServiceError: プロンプト生成に失敗した場合
        """
        try:
            system_prompt = get_reality_edit_system_prompt(nsfw_mode, image_provider)
            user_prompt = build_reality_edit_prompt(
                instruction=instruction,
                current_description=current_description,
                nsfw_mode=nsfw_mode,
            )
            result = await llm_service.generate_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            logger.info(
                f"現実改変編集プロンプト生成完了: provider={result.provider}, cost={result.cost_usd}"
            )
            return result.content, result.cost_usd
        except (LLMServiceError, LiteLLMClientError) as e:
            raise GameServiceError(f"現実改変プロンプト生成エラー: {e}") from e

    async def _generate_reality_feeling_stream(
        self,
        before_desc: str,
        after_desc: str,
        instruction: str,
        pronoun: str,
        bloom: int = 0,
        attributes: list[str] | None = None,
        nsfw_mode: bool = False,
        language: str = "ja",
    ) -> AsyncGenerator[str, None]:
        """現実改変用心境をストリーミング生成 (LLM)

        開花度に応じて心理段階が変化する現実改変専用プロンプトを使用。

        Args:
            before_desc: 現実改変前の説明
            after_desc: 現実改変後の説明
            instruction: 現実改変指示
            pronoun: 一人称
            bloom: 開花度 (0-100)
            attributes: キャラクターに付与された属性リスト
            nsfw_mode: NSFWモードかどうか

        Yields:
            テキストチャンク
        """
        # 現実改変用プロンプトを使用
        system_prompt, user_prompt = build_reality_feeling_prompt(
            before_desc=before_desc,
            after_desc=after_desc,
            instruction=instruction,
            bloom=bloom,
            pronoun=pronoun,
            attributes=attributes,
            nsfw_mode=nsfw_mode,
        )
        from .conversation import get_language_rules

        system_prompt = f"{system_prompt}\n\n{get_language_rules(language)}"

        async for chunk in self._stream_feeling(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            language=language,
            error_context="現実改変心境ストリーミングエラー",
        ):
            yield chunk

    async def play_with_stream(
        self,
        session_id: str | None,
        character_id: str | None,
        character_image: str | None,
        instruction: str,
        base_history_id: str | None = None,
        costume_image: str | None = None,
        preserve_elements: list[str] | None = None,
        change_scope: str = "full",
        custom_preserve_text: str = "",
        transformation_type: str = "costume",
        mask_image: str | None = None,
        mask_id: str | None = None,
        inpaint_strength: float | None = None,
        inpaint_noise: float | None = None,
        negative_prompt: str | None = None,
        prompt_override: str | None = None,
        nsfw_mode_override: bool | None = None,
        difficulty_override: str | None = None,
        language_override: str | None = None,
        character_references: list[dict] | None = None,
        instruction_type: str | None = None,
        seed: int | None = None,
        enable_surroundings_image: bool = False,
        surroundings_include_people: bool = False,
        clothing_color_consistency: bool = False,
    ) -> AsyncGenerator[StreamEvent, None]:
        """ストリーミング対応の着せ替えを実行

        テキストと画像を **真に並列** で生成し、完了した順にイベントを送信。
        - テキストチャンクは到着次第ストリーミング
        - 画像は完了次第送信（テキスト完了前でも）

        Args:
            session_id: 既存セッションID
            character_id: キャラクターID
            character_image: Base64画像
            instruction: 着せ替え/現実改変指示
            base_history_id: 履歴からのベース画像ID
            costume_image: 衣装参照画像（Base64）
            preserve_elements: 保持する要素のリスト
            change_scope: 変更対象 (full, upper, lower, accessories, shoes)
            custom_preserve_text: カスタム保持指示（自由記述）
            transformation_type: 変身タイプ (costume=衣装変更, reality=現実改変)
            nsfw_mode_override: ユーザー設定からのNSFWモード（Noneの場合はセッション設定を使用）
            difficulty_override: ユーザー設定からの難易度（Noneの場合はセッション設定を使用）
            seed: 画像生成seed値（未指定時はランダム生成）
            enable_surroundings_image: 周囲状況画像を生成するか（行動モード専用）
            surroundings_include_people: 周囲画像にリアクションする通行人を含めるか

        Yields:
            StreamEvent: text/image/complete/error イベント
        """
        logger.info(
            "Stream play: session=%s, char=%s, instruction=%s, base_history=%s, nsfw_override=%s",
            session_id,
            character_id,
            instruction[:50] if instruction else "",
            base_history_id,
            nsfw_mode_override,
        )

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

            custom_metadata = self._load_custom_session_metadata(session.id)
            pronoun = (
                character.pronoun if character else custom_metadata.get("pronoun", "僕")
            )
            # キャラクター、自分自身プロフィール、カスタムメタデータから性別を解決
            gender = (
                character.gender if character else custom_metadata.get("gender", "man")
            )

            # 衣装参照画像をデコード
            costume_image_bytes: bytes | None = None
            if costume_image:
                try:
                    if costume_image.startswith("data:"):
                        _, encoded = costume_image.split(",", 1)
                    else:
                        encoded = costume_image
                    costume_image_bytes = base64.b64decode(encoded)
                    logger.info(
                        f"Costume reference image: {len(costume_image_bytes)} bytes"
                    )
                except Exception as e:
                    logger.warning(f"Failed to decode costume image: {e}")

            # マスク画像をデコード (NovelAI専用)
            mask_bytes: bytes | None = None
            if settings.image_provider == "novelai":
                logger.info(
                    f"[Inpaint Debug] mask_image provided: {mask_image is not None and len(mask_image) > 0 if mask_image else False}, mask_id: {mask_id}"
                )
                try:
                    if mask_image:
                        raw = mask_image
                        if raw.startswith("data:"):
                            _, raw = raw.split(",", 1)
                        mask_bytes = base64.b64decode(raw)
                        logger.info(
                            f"[Inpaint Debug] Decoded mask_image: {len(mask_bytes)} bytes"
                        )
                    elif mask_id:
                        if mask_id.startswith("system:"):
                            name = mask_id.split(":", 1)[1]
                            path = BASE_DIR / "images" / "masks" / name
                        else:
                            safe_id = mask_id.split(":", 1)[-1]
                            path = settings.history_masks_dir / f"{safe_id}.png"
                        if path and path.exists():  # type: ignore
                            mask_bytes = path.read_bytes()
                            logger.info(
                                f"[Inpaint Debug] Loaded mask from file: {path}, {len(mask_bytes)} bytes"
                            )
                        else:
                            logger.warning(
                                f"[Inpaint Debug] Mask file not found: {path}"
                            )
                except Exception as e:
                    logger.warning(f"Failed to decode/load mask: {e}")

                logger.info(
                    f"[Inpaint Debug] Final mask_bytes: {len(mask_bytes) if mask_bytes else 0} bytes"
                )

            # 現在のstatsを取得 (T059: 開花度ベースの心理段階)
            current_stats = await session_store.get_or_create_session_stats(session.id)
            current_bloom = current_stats.bloom

            # ユーザー設定を取得（DB永続化されたnsfw_mode, difficulty）
            user_settings = await session_store.get_user_settings()

            # ユーザー設定を使用（リクエストでオーバーライドされた場合はそちらを優先）
            effective_nsfw_mode = (
                nsfw_mode_override
                if nsfw_mode_override is not None
                else user_settings["nsfw_mode"]
            )
            effective_difficulty = (
                difficulty_override
                if difficulty_override is not None
                else user_settings["difficulty"]
            )
            effective_language = normalize_language(
                language_override or user_settings.get("language")
            )
            logger.info(
                f"Effective settings from user: nsfw_mode={effective_nsfw_mode}, "
                f"difficulty={effective_difficulty}, language={effective_language}"
            )

            # ── self_mode: load user profile for profile-based text gen (US5 T026) ──
            self_profile: dict | None = None
            if session.self_mode:
                self_profile = await session_store.get_self_profile()
                logger.info(
                    "Self mode active: self_profile=%s",
                    "loaded" if self_profile else "not set",
                )
                # 自分自身プロフィールから性別・一人称を上書き
                if self_profile:
                    gender = self_profile.get("gender", gender)
                    pronoun = self_profile.get("pronoun", pronoun)

            # ── action mode: scene-change image + text, skip params/tags ──
            if instruction_type == "action":
                logger.info(
                    "Action mode: generating scene-change image + text in parallel"
                )

                # 開花度ベースの段階説明用に現在のstatesを取得
                action_stats = await session_store.get_or_create_session_stats(
                    session.id
                )

                # コンテキスト用に現在の画像を説明（最新履歴のafter_descriptionを再利用）
                last_hist = await session_store.get_latest_history(session.id)
                current_desc = (
                    last_hist.after_description
                    if last_hist and last_hist.after_description
                    else None
                )
                if not current_desc:
                    # 初回: 性別・外見情報から初期コンテキストを構築
                    custom_base_tags = custom_metadata.get("base_tags", "")
                    current_desc = self._build_initial_prompt(
                        gender,
                        character,
                        self_profile,
                        base_tags=custom_base_tags,
                    )

                logger.info("current_desc:%s", current_desc)

                # 前ターンの状況サマリーを生成
                # 初期状態レコード（instruction="初期状態"）はプレイ前の仮データなのでスキップ
                previous_situation_summary: str | None = None
                if (
                    last_hist
                    and last_hist.feeling_text
                    and last_hist.instruction != "初期状態"
                ):
                    try:
                        from .action_prompts import SITUATION_SUMMARY_SYSTEM_PROMPT

                        summary_user = (
                            f"行動: 「{last_hist.instruction}」\n\n"
                            f"モノローグ:\n{last_hist.feeling_text}"
                        )
                        summary_result = await llm_service.generate_text(
                            system_prompt=SITUATION_SUMMARY_SYSTEM_PROMPT,
                            user_prompt=summary_user,
                        )
                        previous_situation_summary = summary_result.content.strip()
                        logger.info(
                            "Previous situation summary: %s",
                            previous_situation_summary,
                        )
                    except Exception as e:
                        logger.warning("Failed to generate situation summary: %s", e)
                        previous_situation_summary = None

                # 履歴+会話をマージしたタイムラインから最近の指示を取得
                recent_actions: list[tuple[str, str]] = []
                try:
                    timeline = await session_store.get_session_timeline(
                        session.id, limit=30
                    )
                    # 新しい順 → 時系列順に反転
                    recent_actions = list(reversed(timeline))
                except Exception:
                    logger.debug("セッションタイムラインの取得に失敗")

                # アクションテキストプロンプトを構築
                #   - self_mode: 自分自身プロフィールの性格を使用
                #   - 変身前 (transformation_count==0): 日常生活プロンプト
                action_personality = ""
                action_description = ""
                if self_profile:
                    action_personality = self_profile.get("personality", "")
                elif character:
                    action_personality = character.personality
                    action_description = character.description

                action_gender = (
                    self_profile.get("gender", gender) if self_profile else gender
                )

                logger.info("action_gender=%s", action_gender)

                act_system, act_user = build_action_prompt(
                    instruction=instruction,
                    current_description=current_desc,
                    pronoun=pronoun,
                    bloom=action_stats.bloom,
                    nsfw_mode=effective_nsfw_mode,
                    personality=action_personality,
                    description=action_description,
                    recent_actions=recent_actions or None,
                    transformation_count=session.transformation_count,
                    gender=action_gender,
                    previous_situation_summary=previous_situation_summary,
                )

                from .conversation import get_language_rules

                act_system = f"{act_system}\n\n{get_language_rules(effective_language)}"

                # ── T007: NovelAI Opus mode detection for action ──
                is_action_novelai_opus = settings.is_novelai_opus_mode

                # T010: Action-specific default i2i_strength (0.85)
                action_inpaint_strength = (
                    inpaint_strength if inpaint_strength is not None else 0.85
                )

                # ── T008/T009: Generate scene-change image prompt ──
                action_image_prompt: str | None = None
                action_novelai_prompt: str | None = None
                action_prompt_desc: str = current_desc  # after_description用
                # PoC: V4 character/scene prompt splitting
                action_characters: list[dict] | None = None

                if is_action_novelai_opus:
                    # T008: NovelAI Opus path — GLM-4.6 tag generation
                    # アクション専用のシステムプロンプトで場面転換を生成
                    action_tag_system = get_action_novelai_prompt_generation_system(
                        nsfw_mode=effective_nsfw_mode,
                        language=effective_language,
                        clothing_color_consistency=clothing_color_consistency,
                    )
                    previous_prompt = current_desc  # 前回のafter_description
                    action_novelai_prompt = (
                        await llm_service.generate_novelai_image_prompt(
                            instruction=instruction,
                            previous_prompt=previous_prompt,
                            nsfw_mode=effective_nsfw_mode,
                            language=effective_language,
                            system_prompt_override=action_tag_system,
                        )
                    )

                    # PoC: Parse JSON response for character/scene splitting
                    try:
                        raw = action_novelai_prompt.strip()
                        # Strip markdown code fence if present
                        if raw.startswith("```"):
                            raw = raw.split("\n", 1)[-1]
                            if raw.endswith("```"):
                                raw = raw[: -len("```")]
                            raw = raw.strip()
                        parsed = json.loads(raw)
                        char_prompt = parsed.get("character", "").strip()
                        scene_prompt = parsed.get("scene", "").strip()
                        if char_prompt and scene_prompt:
                            # Use scene as the base prompt, character as Character object
                            action_image_prompt = scene_prompt
                            action_characters = [
                                {"prompt": char_prompt, "position": (0.5, 0.5)}
                            ]
                            logger.info(
                                "Action prompt split OK: char_len=%d, scene_len=%d",
                                len(char_prompt),
                                len(scene_prompt),
                            )
                        else:
                            raise ValueError("Missing character or scene key")
                    except (json.JSONDecodeError, ValueError, KeyError) as e:
                        # Fallback: use raw response as flat prompt (backward compat)
                        logger.warning(
                            "Action prompt split failed, using flat prompt: %s", e
                        )
                        action_image_prompt = action_novelai_prompt
                        action_characters = None

                    action_prompt_desc = action_novelai_prompt
                    logger.info(
                        "Action NovelAI Opus: generated prompt len=%d",
                        len(action_image_prompt),
                    )
                else:
                    # T009: Non-NovelAI path — Vision LLM + scene-change prompt
                    vision_desc, _ = await self._describe_image(
                        before_image, effective_nsfw_mode
                    )
                    action_edit_system = get_action_image_edit_system_prompt(
                        image_provider=settings.image_provider,
                        nsfw_mode=effective_nsfw_mode,
                    )
                    action_edit_user = build_action_image_edit_prompt(
                        instruction=instruction,
                        current_description=vision_desc,
                    )
                    # LLM経由で編集プロンプトを生成
                    action_image_prompt_result = await llm_service.generate_text(
                        system_prompt=action_edit_system,
                        user_prompt=action_edit_user,
                    )
                    action_image_prompt = action_image_prompt_result.content.strip()
                    action_prompt_desc = action_image_prompt
                    logger.info(
                        "Action non-NovelAI: generated edit prompt len=%d",
                        len(action_image_prompt),
                    )

                # NovelAI品質タグの付与
                if settings.image_provider == "novelai" and action_image_prompt:
                    action_image_prompt = self._enhance_novelai_prompt(
                        action_image_prompt, effective_nsfw_mode
                    )

                # ── T011: Parallel text + image generation ──
                action_event_queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()
                action_text_chunks: list[str] = []

                async def action_text_producer():
                    """アクションモノローグテキストをイベントキューにストリーミング送信する。"""
                    try:
                        async for chunk in llm_service.generate_feeling_stream(
                            system_prompt=act_system,
                            user_prompt=act_user,
                        ):
                            action_text_chunks.append(chunk)
                            await action_event_queue.put(
                                StreamEvent(type="text", data={"chunk": chunk})
                            )
                    except (LLMServiceError, LiteLLMClientError) as e:
                        logger.error(f"Action text streaming error: {e}")
                        fallback_msg = "(行動テキスト生成に失敗しました)"
                        action_text_chunks.append(fallback_msg)
                        await action_event_queue.put(
                            StreamEvent(type="text", data={"chunk": fallback_msg})
                        )
                    finally:
                        await action_event_queue.put(
                            StreamEvent(type="_text_done", data={})
                        )

                async def action_image_producer():
                    """シーン変更画像を生成しキューに結果を送信する。"""
                    try:
                        after_img, img_cost, img_seed = await self._generate_image(
                            before_image,
                            action_image_prompt,
                            nsfw_mode=effective_nsfw_mode,
                            mask_bytes=mask_bytes,
                            inpaint_strength=action_inpaint_strength,
                            inpaint_noise=inpaint_noise,
                            negative_prompt=negative_prompt,
                            character_references=character_references,
                            seed=seed,
                            characters=action_characters,
                        )
                        logger.info(
                            "Action image generated: %d bytes, cost=%s, seed=%s",
                            len(after_img),
                            img_cost,
                            img_seed,
                        )
                        await action_event_queue.put(
                            StreamEvent(
                                type="_image_ready",
                                data={
                                    "image": after_img,
                                    "cost": img_cost,
                                    "seed": img_seed,
                                },
                            )
                        )
                    except Exception as e:
                        logger.error(f"Action image generation error: {e}")
                        await action_event_queue.put(
                            StreamEvent(type="_image_error", data={"error": str(e)})
                        )

                # 両プロデューサーを並列開始
                action_text_task = asyncio.create_task(action_text_producer())
                action_image_task = asyncio.create_task(action_image_producer())

                # キューからイベントを消費
                action_text_done = False
                action_image_data: bytes | None = None
                action_image_cost: float | None = None
                action_image_error: str | None = None
                action_image_seed: int | None = None

                while True:
                    event = await action_event_queue.get()
                    if event is None:
                        break

                    if event.type == "text":
                        yield event
                    elif event.type == "_text_done":
                        action_text_done = True
                    elif event.type == "_image_ready":
                        action_image_data = event.data["image"]
                        action_image_cost = event.data.get("cost")
                        action_image_seed = event.data.get("seed")
                    elif event.type == "_image_error":
                        action_image_error = event.data["error"]

                    # 両方完了？
                    if action_text_done and (
                        action_image_data is not None or action_image_error is not None
                    ):
                        break

                await asyncio.gather(
                    action_text_task, action_image_task, return_exceptions=True
                )

                # ── T015: Fallback — if image failed, use text-only ──
                action_full_text = "".join(action_text_chunks)
                final_action_image = before_image  # デフォルト: 前回の画像を保持

                if action_image_error:
                    logger.warning(
                        "Action image generation failed, falling back to text-only: %s",
                        action_image_error,
                    )
                    # 前回の画像を現在の画像として維持（変更なし）
                    action_prompt_desc = current_desc
                elif action_image_data is not None:
                    final_action_image = action_image_data

                # ── T013: Save to history with generated image ──
                history = await session_store.add_history(
                    session_id=session.id,
                    instruction=instruction,
                    image_data=final_action_image,
                    feeling_text=action_full_text,
                    before_description=current_desc,
                    after_description=action_prompt_desc,
                    instruction_type="action",
                    seed=action_image_seed,
                )

                # セッションの現在の画像をアクション結果で更新
                if history.image_path:
                    await session_store.update_session(
                        session_id=session.id,
                        current_image_path=history.image_path,
                    )

                # ── T012: SSE events — image, cost, complete ──
                if action_image_data is not None:
                    # 生成されたシーン画像のイベントを送信
                    image_b64 = base64.b64encode(action_image_data).decode("utf-8")
                    yield StreamEvent(
                        type="image",
                        data={
                            "image": image_b64,
                            "history_id": history.id,
                            "seed": action_image_seed,
                        },
                    )

                # コストイベントを送信（該当する場合）
                if action_image_cost is not None:
                    yield StreamEvent(
                        type="cost",
                        data={"cost_usd": action_image_cost},
                    )

                # US5: Anlas balance event (NovelAI only)
                anlas_event = await self._get_anlas_event()
                if anlas_event:
                    yield anlas_event

                # ── US2 T031-T033: Surroundings image generation (NovelAI only) ──
                surroundings_image_path: str | None = None
                if enable_surroundings_image and settings.image_provider == "novelai":
                    logger.info("Generating surroundings image for action...")
                    # Detect reality-change from session attributes
                    action_attrs = await session_store.get_session_attribute_texts(
                        session.id
                    )
                    reality_alter_texts = [
                        a for a in action_attrs if a.startswith("[現実改変]")
                    ]
                    has_reality_attrs = len(reality_alter_texts) > 0
                    (
                        surroundings_data,
                        surroundings_cost,
                        surroundings_seed,
                    ) = await self._generate_surroundings_image(
                        instruction=instruction,
                        before_description=current_desc,
                        after_description=action_prompt_desc,
                        nsfw_mode=effective_nsfw_mode,
                        include_people=surroundings_include_people,
                        is_reality_change=has_reality_attrs,
                        reality_alter_descriptions=reality_alter_texts
                        if has_reality_attrs
                        else None,
                    )

                    if surroundings_data is not None:
                        # Save to file
                        import uuid

                        surroundings_filename = f"surroundings_{uuid.uuid4().hex}.png"
                        surroundings_dir = settings.history_images_dir
                        surroundings_dir.mkdir(parents=True, exist_ok=True)
                        surroundings_path = surroundings_dir / surroundings_filename
                        surroundings_path.write_bytes(surroundings_data)
                        # Store as relative path (e.g. history_images/surroundings_xxx.png)
                        surroundings_image_path = str(
                            surroundings_path.relative_to(
                                settings.history_images_dir.parent
                            )
                        )

                        # Update history with surroundings path
                        await session_store.update_history_surroundings(
                            history_id=history.id,
                            surroundings_image_path=surroundings_image_path,
                        )

                        # Emit SSE event
                        surroundings_b64 = base64.b64encode(surroundings_data).decode(
                            "utf-8"
                        )
                        yield StreamEvent(
                            type="surroundings_image",
                            data={
                                "image": surroundings_b64,
                                "history_id": history.id,
                                "seed": surroundings_seed,
                            },
                        )

                        # Emit cost if any
                        if surroundings_cost is not None:
                            yield StreamEvent(
                                type="cost",
                                data={"cost_usd": surroundings_cost},
                            )

                        # Refresh Anlas balance after surroundings generation
                        anlas_event2 = await self._get_anlas_event()
                        if anlas_event2:
                            yield anlas_event2

                        logger.info(
                            "Surroundings image saved: %s", surroundings_image_path
                        )
                    else:
                        logger.info("Surroundings image generation skipped or failed")

                # T014: Complete event — transformation_count unchanged
                yield StreamEvent(
                    type="complete",
                    data={
                        "session_id": session.id,
                        "transformation_count": session.transformation_count,
                        "before_desc": current_desc,
                        "after_desc": action_prompt_desc,
                        "history_id": history.id,
                    },
                )
                return

            # 現在の変身回数を取得（初回変身判定用）
            current_transformation_count = session.transformation_count

            # T007: NovelAI Opusモード判定
            is_novelai_opus_mode = settings.is_novelai_opus_mode

            # 前回のプロンプトを取得（NovelAI Opusモード用）
            previous_prompt: str | None = None
            if is_novelai_opus_mode:
                # 履歴から前回のafter_description（=生成プロンプト）を取得
                last_history = await session_store.get_latest_history(session.id)
                if last_history and last_history.after_description:
                    previous_prompt = last_history.after_description
                else:
                    # 初回: 性別・外見情報から初期プロンプトを構築
                    custom_base_tags_dress = custom_metadata.get("base_tags", "")
                    previous_prompt = self._build_initial_prompt(
                        gender,
                        character,
                        self_profile,
                        base_tags=custom_base_tags_dress,
                    )
                logger.info(
                    f"NovelAI Opus mode: previous_prompt={'yes' if previous_prompt else 'no'}"
                )

            # 2. 現在の画像を説明 (NovelAI Opusモードではスキップ)
            describe_cost: float | None = None
            if is_novelai_opus_mode:
                # T010: Vision LLMをスキップ
                # before_desc は前回のプロンプトまたは初期プロンプト（previous_promptは必ず値あり）
                before_desc = previous_prompt
                logger.info("NovelAI Opus mode: Skipping Vision LLM (describe_image)")
            else:
                logger.info("Describing current image via LLaVA...")
                before_desc, describe_cost = await self._describe_image(
                    before_image, effective_nsfw_mode
                )
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

            # 3. 画像編集プロンプトを生成（変身タイプに応じて分岐）
            logger.info(f"Generating image edit prompt... (type={transformation_type})")
            is_reality = transformation_type == "reality"

            # T008: NovelAI Opusモード用のプロンプト生成
            generated_novelai_prompt: str | None = None
            prompt_gen_cost: float | None = None
            # Phase2: V4 character/scene prompt 分離用
            dress_up_characters: list[dict] | None = None

            if is_novelai_opus_mode:
                # NovelAI GLM-4.6でプロンプト生成
                generated_novelai_prompt = (
                    await llm_service.generate_novelai_image_prompt(
                        instruction=instruction + attribute_context,
                        previous_prompt=previous_prompt,
                        nsfw_mode=effective_nsfw_mode,
                        language=effective_language,
                        clothing_color_consistency=clothing_color_consistency,
                    )
                )

                # Phase2: JSONレスポンスをパースしてcharacter/sceneを分離
                try:
                    raw = generated_novelai_prompt.strip()
                    # マークダウンコードフェンスを除去
                    if raw.startswith("```"):
                        raw = raw.split("\n", 1)[-1]
                        if raw.endswith("```"):
                            raw = raw[: -len("```")]
                        raw = raw.strip()
                    parsed = json.loads(raw)
                    char_prompt = parsed.get("character", "").strip()
                    scene_prompt = parsed.get("scene", "").strip()
                    if char_prompt and scene_prompt:
                        image_edit_prompt = scene_prompt
                        dress_up_characters = [
                            {"prompt": char_prompt, "position": (0.5, 0.5)}
                        ]
                        logger.info(
                            "Dress-up prompt split OK: char_len=%d, scene_len=%d",
                            len(char_prompt),
                            len(scene_prompt),
                        )
                    else:
                        raise ValueError("Missing character or scene key")
                except (json.JSONDecodeError, ValueError, KeyError) as e:
                    # フォールバック: フラットプロンプトとして使用（後方互換）
                    logger.warning(
                        "Dress-up prompt split failed, using flat prompt: %s", e
                    )
                    image_edit_prompt = generated_novelai_prompt
                    dress_up_characters = None

                logger.info(
                    "NovelAI Opus: Generated prompt len=%d, split=%s",
                    len(image_edit_prompt),
                    dress_up_characters is not None,
                )
            elif is_reality:
                # 現実改変用プロンプト生成（T016: image_provider対応）
                (
                    image_edit_prompt,
                    prompt_gen_cost,
                ) = await self._generate_reality_edit_prompt(
                    instruction=instruction + attribute_context,
                    current_description=before_desc,
                    nsfw_mode=effective_nsfw_mode,
                    image_provider=settings.image_provider,
                )
            else:
                # 衣装変更用プロンプト生成（既存）
                (
                    image_edit_prompt,
                    prompt_gen_cost,
                ) = await self._generate_image_edit_prompt(
                    instruction=instruction + attribute_context,
                    current_description=before_desc,
                    preserve_elements=preserve_elements,
                    change_scope=change_scope,
                    custom_preserve_text=custom_preserve_text,
                    nsfw_mode=effective_nsfw_mode,
                )

            # T009: NovelAI専用 - 直接プロンプト指定とのマージ
            final_prompt = image_edit_prompt
            if prompt_override and prompt_override.strip():
                if is_novelai_opus_mode or settings.image_provider == "novelai":
                    # プロンプトオーバーライドを結合（ユーザー指定タグを追加）
                    final_prompt = self._merge_prompts(
                        image_edit_prompt, prompt_override.strip()
                    )
                    logger.info(
                        f"Merged prompt with override: {len(final_prompt)} chars"
                    )
                else:
                    final_prompt = prompt_override.strip()
            if settings.image_provider == "novelai":
                # T014: 品質タグを追加
                final_prompt = self._enhance_novelai_prompt(
                    final_prompt, effective_nsfw_mode
                )

            # 4. 真の並列処理: asyncio.Queue を使ってイベントを統合
            # T010: NovelAI Opusモードでは生成プロンプトをafter_descとして使用
            if is_novelai_opus_mode and generated_novelai_prompt:
                inferred_after_desc = generated_novelai_prompt
            elif is_reality:
                inferred_after_desc = f"「{instruction}」という現実改変により変化した姿"
            else:
                inferred_after_desc = f"{instruction}に変身した姿"

            # イベントキューを作成
            event_queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()

            # 最近の履歴からused_openingsを抽出 (US3 重複排除)
            used_openings: list[str] = []
            try:
                recent_history = await session_store.get_history(session.id)
                for h in recent_history[-10:]:
                    if h.feeling_text:
                        # 先頭30文字までを書き出し㊲グネチャーとして抽出
                        opening_sig = h.feeling_text[:30].split("\n")[0]
                        if opening_sig:
                            used_openings.append(opening_sig)
            except Exception:
                logger.debug("Could not extract used_openings from history")

            # テキスト収集用
            text_chunks: list[str] = []

            async def text_producer():
                """テキストチャンクをキューに送信"""
                try:
                    if session.self_mode and self_profile:
                        # 自分自身モード: プロフィールベースのテキスト、心理段階なし (US5)
                        async for chunk in self._generate_self_mode_feeling_stream(
                            before_desc=before_desc,
                            after_desc=inferred_after_desc,
                            instruction=instruction,
                            self_profile=self_profile,
                            nsfw_mode=effective_nsfw_mode,
                            language=effective_language,
                        ):
                            text_chunks.append(chunk)
                            await event_queue.put(
                                StreamEvent(type="text", data={"chunk": chunk})
                            )
                    elif is_reality:
                        # 現実改変用心境生成（ストリーミング）
                        async for chunk in self._generate_reality_feeling_stream(
                            before_desc=before_desc,
                            after_desc=inferred_after_desc,
                            instruction=instruction,
                            pronoun=pronoun,
                            bloom=current_bloom,
                            attributes=attributes,
                            nsfw_mode=effective_nsfw_mode,
                            language=effective_language,
                        ):
                            text_chunks.append(chunk)
                            await event_queue.put(
                                StreamEvent(type="text", data={"chunk": chunk})
                            )
                    else:
                        # 衣装変更用心境生成（既存）
                        async for chunk in self._generate_feeling_stream(
                            before_desc=before_desc,
                            after_desc=inferred_after_desc,
                            instruction=instruction,
                            pronoun=pronoun,
                            bloom=current_bloom,
                            attributes=attributes,
                            nsfw_mode=effective_nsfw_mode,
                            transformation_count=current_transformation_count,
                            language=effective_language,
                            personality=character.personality if character else "",
                            description=character.description if character else "",
                            used_openings=used_openings,
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
                    after_image, image_cost, img_seed = await self._generate_image(
                        before_image,
                        final_prompt,
                        costume_image_bytes,
                        nsfw_mode=effective_nsfw_mode,
                        mask_bytes=mask_bytes,
                        inpaint_strength=inpaint_strength,
                        inpaint_noise=inpaint_noise,
                        negative_prompt=negative_prompt,
                        character_references=character_references,
                        seed=seed,
                        characters=dress_up_characters,
                    )
                    logger.info(
                        "Image generated: %d bytes, cost: %s",
                        len(after_image),
                        image_cost,
                    )
                    await event_queue.put(
                        StreamEvent(
                            type="_image_ready",
                            data={
                                "image": after_image,
                                "cost": image_cost,
                                "seed": img_seed,
                            },
                        )
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
            image_seed: int | None = None

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
                    image_seed = event.data.get("seed")
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
                instruction_type=instruction_type or "dress_up",
                seed=image_seed,
            )

            # 5.1. タグ分類 (T023)
            tags = classify_tags(instruction)
            await session_store.save_transformation_tag(
                history_id=history.id,
                costume_category=tags.costume_category,
                exposure_level=tags.exposure_level,
                age_impression=tags.age_impression,
            )

            # タグイベントを送信 (T024)
            yield StreamEvent(
                type="tags",
                data={
                    "costume_category": tags.costume_category,
                    "exposure_level": tags.exposure_level,
                    "age_impression": tags.age_impression,
                },
            )

            # 5.1.5 現実改変時: 指示文をセッション属性に自動追加
            if is_reality:
                reality_attr_text = f"[現実改変] {instruction}"
                existing_attrs = await session_store.get_session_attribute_texts(
                    session.id
                )
                if reality_attr_text not in existing_attrs:
                    new_attr = await session_store.add_session_attribute(
                        session.id, reality_attr_text
                    )
                    logger.info(f"Auto-added reality attribute: {reality_attr_text}")
                    yield StreamEvent(
                        type="reality_attribute_added",
                        data={
                            "attribute_id": new_attr["id"],
                            "attribute_text": reality_attr_text,
                        },
                    )

            # ── self_mode: skip parameter/critical/ending/achievement (US5 T026) ──
            if not session.self_mode:
                # 5.2. パラメータ計算と更新 (T015, T016)
                stats = await session_store.get_or_create_session_stats(session.id)
                old_bloom = stats.bloom

                bloom_delta, shame_delta, adaptation_delta = calculate_parameter_change(
                    tags, stats
                )

                # 現実改変の場合はパラメータ変動を増幅
                if is_reality:
                    # 開花度を大きく上昇 (現実改変は影響大)
                    bloom_reality_boost = random.randint(5, 15)
                    bloom_delta += bloom_reality_boost

                    # 羞恥心へのインパクト
                    shame_reality_boost = 5 + random.randint(-2, 2)
                    shame_delta += shame_reality_boost

                    # 順応度を揺さぶる
                    adaptation_reality_boost = random.randint(-3, 3)
                    adaptation_delta += adaptation_reality_boost

                    logger.info(
                        f"Reality alteration boost: bloom+{bloom_reality_boost}, "
                        f"shame+{shame_reality_boost}, adapt+{adaptation_reality_boost}"
                    )

                new_stats = apply_parameter_change(
                    stats, bloom_delta, shame_delta, adaptation_delta
                )

                # 臨界点チェック
                critical_event = check_critical_point(
                    old_bloom,
                    new_stats.bloom,
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
                        "bloom": new_stats.bloom,
                        "shame": new_stats.shame,
                        "adaptation": new_stats.adaptation,
                        "bloom_delta": bloom_delta,
                        "shame_delta": shame_delta,
                        "adaptation_delta": adaptation_delta,
                        "passedCriticalPoints": new_stats.passed_critical_points,
                        "difficulty": new_stats.difficulty,
                        "nsfwMode": new_stats.nsfw_mode,
                        "enablePromptPreview": settings.enable_prompt_preview,  # statsの取得方法によっては欠落する可能性があるため、settingsから取得
                    },
                )

                # 臨界点イベントを送信 (T033)
                if critical_event:
                    # ランダムな特別セリフを取得
                    speech = get_critical_speech(
                        critical_event.threshold, pronoun=pronoun
                    )
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

            if not session.self_mode:
                # 6.1 エンディング判定 (T048)
                has_session_ending = (
                    await session_store.has_achieved_ending_for_session(session.id)
                )
                if not has_session_ending:
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
                                "badge": ending_result.ending.badge,
                                "is_new": ending_result.is_new,
                            },
                        )

                # 6.1.5 実績分類処理 - テキスト生成完了後に変身指示を分類してカウント更新
                try:
                    classification_result = await classify_for_achievement(
                        query=instruction,
                        gender="man",  # デフォルトで男性（キャラクターの元の性別）
                    )
                    categories = list(classification_result.categories)
                    if is_reality and "REALITY_ALTER" not in categories:
                        categories.append("REALITY_ALTER")
                    if categories:
                        update_achievement_counts(categories)
                        logger.info(
                            f"Achievement classification: categories={categories}"
                        )
                except Exception as e:
                    # 分類エラーはメイン処理を妨げない（フェイルセーフ設計）
                    logger.warning(f"Achievement classification failed: {e}")

                # 6.2 実績判定 (T066)
                try:
                    # 既存の解除済み実績を取得（グローバル管理）
                    user_achievements = get_user_achievements()
                    already_unlocked = {
                        ua.achievement_id for ua in user_achievements if ua.unlocked
                    }

                    # 累積統計を取得して実績判定用に変換
                    achievement_stats = get_global_stats()
                    # 現在のセッションの最新値で上書き
                    # Note: transform_countはincrement後の値を直接使用（DB同期問題を回避）
                    achievement_stats.transform_count = transformation_count
                    achievement_stats.bloom = new_stats.bloom
                    achievement_stats.shame = new_stats.shame
                    achievement_stats.adaptation = new_stats.adaptation

                    # 新規解除された実績をチェック
                    newly_unlocked = check_achievements(
                        session.id, achievement_stats, already_unlocked
                    )

                    # 新規解除された実績を保存してイベント送信 (T067)
                    for achievement in newly_unlocked:
                        save_user_achievement(session.id, achievement.id)
                        yield StreamEvent(
                            type="achievement",
                            data={
                                "achievement_id": achievement.id,
                                "name": achievement.name,
                                "description": achievement.description,
                                "icon": achievement.icon,
                                "category": achievement.category,
                            },
                        )
                        logger.info(
                            f"Achievement unlocked: {achievement.name} for session {session.id}"
                        )
                except Exception as e:
                    logger.warning(f"Achievement check failed: {e}")

            # 7. 現在の画像パスを更新
            await session_store.update_session(
                session_id=session.id,
                current_image_path=history.image_path,
            )

            # 8. 画像イベントを送信
            image_b64 = base64.b64encode(image_data).decode("utf-8")
            yield StreamEvent(
                type="image",
                data={
                    "image": image_b64,
                    "history_id": history.id,
                    "seed": image_seed,
                },
            )

            # 8.5 コストイベントを送信（API料金がある場合）
            # 画像生成コスト + Vision LLMコスト + プロンプト生成LLMコストを合算
            total_api_cost = sum(
                c for c in [image_cost, describe_cost, prompt_gen_cost] if c is not None
            )
            if total_api_cost > 0:
                yield StreamEvent(
                    type="cost",
                    data={"cost_usd": total_api_cost},
                )

            # US5: Anlas balance event (NovelAI only)
            anlas_event = await self._get_anlas_event()
            if anlas_event:
                yield anlas_event

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
            # current_image_path は2種類のパターンがある:
            # 1. キャラクター初期画像: images/characters/... (BASE_DIR からの相対パス)
            # 2. 履歴画像: history_images/... (data/ からの相対パス)
            logger.info(
                f"[DEBUG] Session current_image_path: {session.current_image_path}"
            )
            if session.current_image_path:
                resolved = self._resolve_image_path(session.current_image_path)
                if resolved:
                    image_bytes = resolved.read_bytes()
                    logger.info(
                        f"[DEBUG] Loaded image from: {resolved} ({len(image_bytes)} bytes)"
                    )
                else:
                    logger.warning(
                        "[DEBUG] Image file not found, falling back to character image!"
                    )
                    if character:
                        image_bytes = character_manager.get_image_bytes(character)
                    else:
                        raise ValueError("セッションの画像が見つかりません")
            else:
                # current_image_pathがない場合
                logger.warning(
                    "[DEBUG] current_image_path is empty, falling back to character image!"
                )
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
                    resolved = self._resolve_image_path(session.current_image_path)
                    if resolved:
                        return session, character, resolved.read_bytes()
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
                resolved = self._resolve_image_path(session.current_image_path)
                if resolved:
                    current_image_bytes = resolved.read_bytes()

            if current_image_bytes is None:
                raise GameServiceError("現在の画像が見つかりません")

            # 3. キャラクター情報取得
            character: Optional[Character] = None
            if session.character_id:
                character = character_manager.get_by_id(session.character_id)

            # 4. 現在の画像を説明
            yield StreamEvent(type="status", data={"message": "画像を分析中..."})

            current_description, describe_cost = await self._describe_image(
                current_image_bytes
            )
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
            new_image, image_cost, improve_seed = await self._generate_image(
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
                seed=improve_seed,
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
                data={
                    "image": image_b64,
                    "history_id": history.id,
                    "seed": improve_seed,
                },
            )

            # コストイベント
            total_api_cost = sum(
                c for c in [image_cost, describe_cost] if c is not None
            )
            if total_api_cost > 0:
                yield StreamEvent(
                    type="cost",
                    data={"cost_usd": total_api_cost},
                )

            # US5: Anlas balance event (NovelAI only)
            anlas_event = await self._get_anlas_event()
            if anlas_event:
                yield anlas_event

            # 完了イベント
            yield StreamEvent(
                type="complete",
                data={"session_id": session_id, "improved": True},
            )

        except Exception as e:
            logger.exception("Quality improvement error: %s", e)
            yield StreamEvent(type="error", data={"message": str(e)})

    async def preview_prompts(
        self,
        session_id: str | None,
        instruction: str,
        transformation_type: str = "costume",
        preserve_elements: list[str] | None = None,
        change_scope: str = "full",
        custom_preserve_text: str = "",
        instruction_type: str | None = None,
    ) -> dict:
        """プロンプトのプレビューを生成する

        instruction_type が "action" の場合はアクション専用プロンプトを構築する。
        それ以外は衣装変更/現実改変のプロンプトを構築する。
        """

        current_description = ""
        nsfw_mode = False
        bloom = 0
        transformation_count = 0
        gender = "man"
        pronoun = "僕"
        personality = ""
        description = ""
        session = None
        recent_actions: list[tuple[str, str]] = []
        previous_situation_summary: str | None = None
        reality_alter_texts: list[str] = []

        if session_id:
            try:
                # セッションと統計情報を個別に取得
                session = await session_store.get_session_by_id(session_id)
                if session:
                    stats = await session_store.get_or_create_session_stats(session_id)

                    # ユーザー設定からnsfw_modeを取得
                    user_settings = await session_store.get_user_settings(session_id)
                    nsfw_mode = user_settings.get("nsfw_mode", False)
                    bloom = stats.bloom
                    transformation_count = session.transformation_count

                    # 履歴から最新の画像説明を取得
                    history_items = await session_store.get_history(session_id)
                    if history_items:
                        current_description = history_items[-1].after_description

                    # セッション属性を取得（プロンプトに反映）
                    attributes = await session_store.get_session_attribute_texts(
                        session_id
                    )
                    # 現実改変属性を抽出（周辺プロンプトプレビュー用）
                    reality_alter_texts = [
                        a for a in (attributes or []) if a.startswith("[現実改変]")
                    ]
                    instruction += self._format_attribute_context(attributes)

                    # self_mode の場合、プロフィールから性別・一人称を取得
                    if session.self_mode:
                        self_profile = await session_store.get_self_profile()
                        if self_profile:
                            gender = self_profile.get("gender", gender)
                            pronoun = self_profile.get("pronoun", pronoun)
                            personality = self_profile.get("personality", "")

                    # action プレビュー用: タイムラインと前回サマリー
                    if instruction_type == "action":
                        try:
                            timeline = await session_store.get_session_timeline(
                                session_id, limit=30
                            )
                            recent_actions = list(reversed(timeline))
                        except Exception:
                            pass

                        last_hist = await session_store.get_latest_history(session_id)
                        if (
                            last_hist
                            and last_hist.feeling_text
                            and last_hist.instruction != "初期状態"
                        ):
                            try:
                                from .action_prompts import (
                                    SITUATION_SUMMARY_SYSTEM_PROMPT,
                                )

                                summary_user = (
                                    f"行動: 「{last_hist.instruction}」\n\n"
                                    f"モノローグ:\n{last_hist.feeling_text}"
                                )
                                summary_result = await llm_service.generate_text(
                                    system_prompt=SITUATION_SUMMARY_SYSTEM_PROMPT,
                                    user_prompt=summary_user,
                                )
                                previous_situation_summary = (
                                    summary_result.content.strip()
                                )
                            except Exception:
                                previous_situation_summary = None

            except Exception as e:
                logger.warning(f"Preview prompts session fetch error: {e}")

        # -- action モードのプレビュー --
        if instruction_type == "action":
            act_system, act_user = build_action_prompt(
                instruction=instruction,
                current_description=current_description or "不明",
                pronoun=pronoun,
                bloom=bloom,
                nsfw_mode=nsfw_mode,
                personality=personality,
                description=description,
                recent_actions=recent_actions or None,
                transformation_count=transformation_count,
                gender=gender,
                previous_situation_summary=previous_situation_summary,
            )

            # 画像プロンプト（NovelAI Opus / その他で分岐）
            image_edit_prompt = ""
            novelai_tag_prompt: str | None = None
            if settings.is_novelai_opus_mode:
                action_tag_system = get_action_novelai_prompt_generation_system(
                    nsfw_mode=nsfw_mode,
                    language=settings.language
                    if hasattr(settings, "language")
                    else "ja",
                )
                novelai_tag_prompt = action_tag_system
                image_edit_prompt = "(NovelAI Opus: タグはLLMが動的生成)"
            else:
                action_edit_system = get_action_image_edit_system_prompt(
                    image_provider=settings.image_provider,
                    nsfw_mode=nsfw_mode,
                )
                image_edit_prompt = action_edit_system

            # 周辺画像プロンプトプレビュー（現実改変属性含む）
            has_reality_attrs = len(reality_alter_texts) > 0
            from .action_prompts import (
                get_surroundings_image_prompt_system,
                build_surroundings_image_user_prompt,
            )

            surroundings_system = get_surroundings_image_prompt_system(
                nsfw_mode=nsfw_mode,
                include_people=True,
                is_reality_change=has_reality_attrs,
                reality_alter_descriptions=reality_alter_texts
                if has_reality_attrs
                else None,
            )
            surroundings_user = build_surroundings_image_user_prompt(
                instruction=instruction,
                before_description=current_description or "不明",
                after_description="(アクション後の状態)",
                include_people=True,
                is_reality_change=has_reality_attrs,
                reality_alter_descriptions=reality_alter_texts
                if has_reality_attrs
                else None,
            )

            return {
                "image_edit_prompt": image_edit_prompt,
                "feeling_system_prompt": act_system,
                "feeling_user_prompt": act_user,
                "instruction_type": "action",
                "novelai_tag_prompt": novelai_tag_prompt,
                "surroundings_system_prompt": surroundings_system,
                "surroundings_user_prompt": surroundings_user,
            }

        # -- 衣装変更 / 現実改変のプレビュー --
        image_edit_prompt = ""
        if transformation_type == "reality":
            image_edit_prompt, _ = await self._generate_reality_edit_prompt(
                instruction=instruction,
                current_description=current_description,
                nsfw_mode=nsfw_mode,
                image_provider=settings.image_provider,
            )
        else:
            image_edit_prompt, _ = await self._generate_image_edit_prompt(
                instruction=instruction,
                current_description=current_description,
                preserve_elements=preserve_elements,
                change_scope=change_scope,
                custom_preserve_text=custom_preserve_text,
                nsfw_mode=nsfw_mode,
            )

        from .prompts import build_feeling_prompt, get_psychological_stage

        stage = get_psychological_stage(bloom, nsfw_mode)
        system_prompt = stage["system_prompt"]

        user_prompt = build_feeling_prompt(
            before_desc=current_description or "着せ替え前の状態",
            after_desc=f"{instruction}に変身した姿",
            instruction=instruction,
            pronoun=pronoun,
        )

        return {
            "image_edit_prompt": image_edit_prompt,
            "feeling_system_prompt": system_prompt,
            "feeling_user_prompt": user_prompt,
            "instruction_type": instruction_type or transformation_type,
            "novelai_tag_prompt": None,
        }

    def _format_attribute_context(self, attributes: list[str] | None) -> str:
        """属性リストをコンテキスト文字列に整形"""
        if not attributes:
            return ""
        return (
            "\n\n【対象キャラクターの属性】\n"
            + "\n".join(f"- {attr}" for attr in attributes)
            + "\n（これらの属性を画像生成時に考慮してください）"
        )


# グローバルサービスインスタンス
game_service = GameService()
