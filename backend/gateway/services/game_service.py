"""
ゲームサービス

着せ替えゲームのコアロジックを実装。
ComfyUI (画像生成) + LiteLLM (画像説明・心境生成) を統合。
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import random
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from ..consts.language import normalize_language
from ..consts.novelai_models import (
    resolve_user_image_model,
    supports_character_references,
)
from ..databases.base import async_session_factory
from ..models import (
    CRITICAL_POINTS,
    DIFFICULTY_PRESETS,
    Character,
    CriticalPointEvent,
    PersistedSession,
    SessionStats,
)
from ..settings.config import BASE_DIR, settings
from .achievement_classifier import classify_for_achievement
from .action_prompts import (
    build_action_image_edit_prompt,
    build_action_prompt,
    get_action_image_edit_system_prompt,
    get_action_novelai_prompt_generation_system,
)
from .anlas_service import get_anlas_balance
from .character_service import (
    apply_character_prompt_tags,
    build_novelai_characters_section,
    build_session_characters_prompt_section,
    load_session_characters_for_prompt,
    upsert_protagonist_session_character,
)
from .character_service import (
    resolve_protagonist_image_identity as _resolve_protagonist_image_identity,
)
from .characters import character_manager
from .clothing_layers import (
    append_clothing_layer_feeling_rule,
    append_clothing_layer_image_rule,
    clothing_layer_negative_suffix,
    ensure_characters_worn_under_layers,
    ensure_worn_under_layers,
    merge_negative_prompt,
    strip_characters_worn_under_layers,
    strip_worn_under_layers_for_image,
)
from .comfy import ComfyUIClient
from .cost_tracker import CostTracker, begin_cost_tracking, record_cost
from .endings import judge_ending
from .gender_congruence import (
    GenderCongruenceResult,
    evaluate_gender_congruence,
    is_gender_aware_feeling_mode,
    normalize_feeling_mode,
    should_use_congruence_llm,
)
from .history_context import (
    build_history_context,
    resolve_history_lookback_enabled,
)
from .image_generation import ImageGenerationService, image_service
from .image_only_prompts import (
    IMAGE_ONLY_TEXT_TO_IMAGE_RULE,
    build_image_only_edit_prompt,
    build_image_only_generate_prompt,
    get_image_only_edit_system_prompt,
    get_image_only_generate_system_prompt,
)
from .image_paths import resolve_stored_image_path
from .litellm_client import LiteLLMClientError
from .llm_json import strip_code_fence
from .llm_service import LLMServiceError, llm_service
from .memory_prompts import build_memory_priority_instruction
from .prompts import (
    FEELING_SYSTEM_PROMPT,
    build_enhanced_feeling_prompt,
    build_feeling_prompt,
    enhance_prompt_for_novelai,
    get_critical_speech,
)
from .providers import resolve_image_provider
from .reality_prompts import (
    build_reality_edit_prompt,
    build_reality_feeling_prompt,
    get_reality_edit_system_prompt,
)
from .self_mode_prompts import build_self_mode_feeling_prompt
from .session import session_store
from .settings_service import settings_service
from .tag_classifier import TransformationTags, classify_tags

logger = logging.getLogger(__name__)

# Position mapping for multi-character V4 prompt
_POSITION_MAP: dict[str, tuple[float, float]] = {
    "center": (0.5, 0.5),
    "left": (0.3, 0.5),
    "right": (0.7, 0.5),
}


def _parse_novelai_prompt_json(
    raw_response: str,
) -> tuple[str, list[dict]] | None:
    """Parse LLM response into (scene_prompt, characters_list).

    Supports two formats:
    - Single character: {"character": "...", "scene": "..."}
    - Multiple characters: {"characters": [{"tags": "...", "position": "center"}, ...], "scene": "..."}

    Returns None if parsing fails.
    """
    parsed = json.loads(strip_code_fence(raw_response))
    scene_prompt = parsed.get("scene", "").strip()
    if not scene_prompt:
        return None

    # Multi-character format: {"characters": [...], "scene": "..."}
    characters_list = parsed.get("characters")
    if isinstance(characters_list, list) and len(characters_list) > 0:
        result_chars = []
        for char_entry in characters_list:
            tags = char_entry.get("tags", "").strip()
            if not tags:
                continue
            pos_name = char_entry.get("position", "center")
            position = _POSITION_MAP.get(pos_name, (0.5, 0.5))
            result_chars.append({"prompt": tags, "position": position})
        if result_chars:
            logger.info(
                "Multi-character prompt parsed: %d characters, scene_len=%d",
                len(result_chars),
                len(scene_prompt),
            )
            return scene_prompt, result_chars

    # Single character format: {"character": "...", "scene": "..."}
    char_prompt = parsed.get("character", "").strip()
    if char_prompt:
        return scene_prompt, [{"prompt": char_prompt, "position": (0.5, 0.5)}]

    return None


def _pending_cost_event(
    tracker: CostTracker, emitted_usd: float
) -> tuple[StreamEvent | None, float]:
    """前回通知した以降に記録された API 料金があれば cost イベントにして返す。"""
    delta = tracker.total_usd - emitted_usd
    if delta > 0:
        return StreamEvent(type="cost", data={"cost_usd": delta}), tracker.total_usd
    return None, emitted_usd


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

# 新計算方式(new)の開花度倍率（難易度別）。
# 従来方式(legacy)より小さくし、変身を重ねても開花度が緩やかに増える。
# これにより resistance_limit (変身15回かつ開花度50未満) が到達可能になる。
BLOOM_MULTIPLIER_NEW = {
    "easy": 0.35,
    "normal": 0.6,
    "hard": 0.9,
}

# 立ち絵再生成の構図基準。変身後は女性想定のため女性立ち絵を固定で使う
STANDING_PORTRAIT_REFERENCE_CHARACTER_ID = "char2"

# 立ち絵構図を固定するDanbooru系タグ。プロバイダ共通で付与する
STANDING_PORTRAIT_COMPOSITION_TAGS = (
    "solo, full body, standing, looking at viewer, arms at sides, "
    "straight-on, feet visible, simple background, white background"
)

# 立ち絵では避けたい構図・トリミング
STANDING_PORTRAIT_NEGATIVE_PROMPT = (
    "cropped, close-up, upper body, portrait, bust shot, cowboy shot, "
    "out of frame, cut off, multiple views, sitting, from behind, "
    "complex background, scenery"
)


def clamp(value: int, min_val: int, max_val: int) -> int:
    """値を範囲内にクランプ"""
    return max(min_val, min(max_val, value))


def calculate_parameter_change(
    tags: TransformationTags,
    stats: SessionStats,
    bloom_calc_method: str = "legacy",
    gender_discomfort: bool = True,
) -> tuple[int, int, int]:
    """パラメータ変化量を計算する

    Args:
        tags: 変身タグ
        stats: 現在のセッション統計
        bloom_calc_method: 開花度増分の計算方式 ("legacy" | "new")
        gender_discomfort: False のとき性別適合服装として開花増分を 0 にする

    Returns:
        (bloom_delta, shame_delta, adaptation_delta) のタプル
    """
    # 難易度設定を取得
    preset = DIFFICULTY_PRESETS.get(stats.difficulty, DIFFICULTY_PRESETS["normal"])

    # 開花度計算
    base_bloom = BASE_CORRUPTION_EXPOSURE.get(tags.exposure_level, 4)
    category_bloom = BASE_CORRUPTION_CATEGORY.get(tags.costume_category, 1)
    bloom_base = base_bloom + category_bloom

    # 羞恥心が高いほど堕落しやすい（50を基準）
    shame_factor = stats.shame / 50.0

    if bloom_calc_method == "new":
        # 新計算方式: 羞恥による増幅を上限1.0に抑え、専用の緩やかな倍率を適用する。
        # 変身回数を重ねても開花度が過度に上がらず、抵抗ルートが成立し得る。
        shame_factor = min(shame_factor, 1.0)
        bloom_multiplier = BLOOM_MULTIPLIER_NEW.get(
            stats.difficulty, BLOOM_MULTIPLIER_NEW["normal"]
        )
    else:
        # 従来方式(legacy): 難易度倍率をそのまま適用する。
        bloom_multiplier = preset.bloom_multiplier

    bloom_raw = int(bloom_base * shame_factor)
    bloom_delta = int(bloom_raw * bloom_multiplier)

    # 羞恥心変化（ランダム要素あり）
    shame_delta = random.randint(-5, 10)

    # 順応度計算
    adaptation_raw = ADAPTATION_BY_CATEGORY.get(tags.costume_category, 0)
    adaptation_delta = int(adaptation_raw * preset.adaptation_multiplier)

    # 元性別と違和感のない服装: 開花は増やさない。羞恥の大幅増も抑える
    if not gender_discomfort:
        bloom_delta = 0
        shame_delta = min(shame_delta, 0)

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
        self._comfy_client: ComfyUIClient | None = None
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
        character: Character | None = None,
        self_profile: dict | None = None,
        base_tags: str = "",
        enable_multiple_people: bool = False,
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
            enable_multiple_people: 複数人表示モード（soloタグを付与しない）

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
        # 複数人表示モードではsoloタグを付与しない
        solo_tag = "" if enable_multiple_people else ", solo"
        return (
            f"masterpiece, best quality, very aesthetic, anime, moe, "
            f"{gender_tag}{solo_tag}, {char_tags}"
        ).rstrip(", ")

    @staticmethod
    async def _get_anlas_event() -> StreamEvent | None:
        """Get Anlas balance as an SSE event (NovelAI provider only)."""
        if resolve_image_provider() != "novelai":
            return None
        try:
            balance = await get_anlas_balance()
            return StreamEvent(
                type="anlas",
                data={
                    "fixed_anlas": balance.fixed_anlas,
                    "purchased_anlas": balance.purchased_anlas,
                    "total_anlas": balance.total_anlas,
                    "usage": {
                        "percent": balance.usage.percent,
                        "is_negative": balance.usage.is_negative,
                        "time_until_next_percent": (
                            balance.usage.time_until_next_percent
                        ),
                    }
                    if balance.usage
                    else None,
                },
            )
        except Exception as e:
            logger.warning("Failed to get Anlas balance: %s", e)
            return None

    def _prepare_clothing_layer_image_payload(
        self,
        prompt: str,
        characters: list[dict] | None,
        *,
        previous_prompt: str | None,
        instruction: str,
        respect_clothing_layers: bool,
        negative_prompt: str | None,
    ) -> tuple[str, str, list[dict] | None, list[dict] | None, str | None]:
        """衣装レイヤーON時に visual / inventory を分離し、送信用と履歴用を返す。

        Returns:
            (state_prompt, image_prompt, state_characters, image_characters, negative)
        """
        state_prompt = prompt or ""
        state_characters = characters
        if respect_clothing_layers:
            state_prompt = ensure_worn_under_layers(
                state_prompt,
                previous_prompt,
                respect_clothing_layers=True,
                instruction=instruction,
            )
            state_characters = ensure_characters_worn_under_layers(
                characters,
                previous_prompt,
                respect_clothing_layers=True,
                instruction=instruction,
            )

        # negative 判定は visual 有無を見るため、state 全文（characters 含む）を渡す
        negative_source_parts: list[str] = []
        if state_characters:
            for char in state_characters:
                prompt_text = char.get("prompt")
                if isinstance(prompt_text, str) and prompt_text.strip():
                    negative_source_parts.append(prompt_text)
        if state_prompt.strip():
            negative_source_parts.append(state_prompt)
        negative_source = (
            "\n".join(negative_source_parts) if negative_source_parts else ""
        )

        layer_negative = clothing_layer_negative_suffix(
            negative_source,
            respect_clothing_layers=respect_clothing_layers,
            instruction=instruction,
        )
        merged_negative = merge_negative_prompt(negative_prompt, layer_negative)

        image_prompt = strip_worn_under_layers_for_image(state_prompt)
        image_characters = strip_characters_worn_under_layers(state_characters)
        return (
            state_prompt,
            image_prompt,
            state_characters,
            image_characters,
            merged_negative,
        )

    async def _generate_image(
        self,
        image_bytes: bytes | None,
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
        novelai_image_model_override: str | None = None,
    ) -> tuple[bytes, float | None, int | None]:
        """画像を生成 (ImageGenerationService経由)

        プロバイダーはIMAGE_PROVIDER環境変数で切り替え:
        - selfhost: ComfyUI (デフォルト)
        - openrouter: OpenRouter API

        Args:
            image_bytes: 入力画像。None の場合はベース画像なしの text-to-image で
                生成する（selfhost/ComfyUI は非対応で画像サービス側がエラーにする）
            instruction: 着せ替え指示（画像APIへ渡す最終プロンプト）
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

            # 保険: 呼び出し側で strip 漏れがあっても inventory 行は画像へ送らない
            image_prompt = strip_worn_under_layers_for_image(instruction)
            image_characters = strip_characters_worn_under_layers(characters)

            if image_bytes is None:
                # ベース画像なし: text-to-image で新規生成する
                result = await self._image_service.generate_image(
                    image_prompt,
                    image_bytes=None,
                    reference_image_bytes=costume_image_bytes,
                    mask_bytes=mask_bytes,
                    workflow_path=workflow_path,
                    negative_prompt=negative_prompt,
                    i2i_strength_override=inpaint_strength,
                    i2i_noise_override=inpaint_noise,
                    nsfw_mode=nsfw_mode,
                    character_references=character_references,
                    seed=seed,
                    characters=image_characters,
                    novelai_model_override=novelai_image_model_override,
                )
            else:
                result = await self._image_service.edit_image(
                    image_bytes=image_bytes,
                    prompt=image_prompt,
                    reference_image_bytes=costume_image_bytes,
                    mask_bytes=mask_bytes,
                    workflow_path=workflow_path,
                    negative_prompt=negative_prompt,
                    inpaint_strength=inpaint_strength,
                    inpaint_noise=inpaint_noise,
                    nsfw_mode=nsfw_mode,
                    character_references=character_references,
                    seed=seed,
                    characters=image_characters,
                    novelai_model_override=novelai_image_model_override,
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
        novelai_model_override: str | None = None,
        novelai_image_model_override: str | None = None,
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
            novelai_model_override: NovelAI テキストモデルのオーバーライド
            novelai_image_model_override: NovelAI 画像モデルのオーバーライド

        Returns:
            (image bytes, API cost USD, seed) or (None, None, None) on failure
        """
        if resolve_image_provider() != "novelai":
            logger.info("Surroundings image generation is only supported with NovelAI")
            return None, None, None

        try:
            # LLM でプロンプト生成
            from .action_prompts import (
                build_surroundings_image_user_prompt,
                get_surroundings_image_prompt_system,
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
                novelai_model_override=novelai_model_override,
            )
            record_cost(getattr(scenery_prompt_result, "cost_usd", None))
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
                novelai_model_override=novelai_image_model_override,
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

    async def _get_memory_priority_suffix(self, language: str = "ja") -> str:
        """保存済みメモリテキストから最優先指示ブロックを取得する。

        メモリテキストが未設定の場合は空文字を返す。
        着せ替え/現実改変/行動の画像編集プロンプトおよび心境モノローグ生成の
        システムプロンプトに付与するために使用する。

        Args:
            language: 出力言語 ("ja" or "en")

        Returns:
            システムプロンプトに付与する追加指示ブロック（空文字の場合あり）
        """
        memory_text = await settings_service.get_memory_text()
        return build_memory_priority_instruction(memory_text or "", language)

    async def _generate_image_edit_prompt(
        self,
        instruction: str,
        current_description: str,
        nsfw_mode: bool = False,
        novelai_model_override: str | None = None,
        use_memory: bool = True,
        respect_clothing_layers: bool = False,
        suppress_gender_discomfort_cues: bool = False,
        history_context: str = "",
    ) -> tuple[str, float | None]:
        """画像編集プロンプトを生成 (LLMService経由)

        プロバイダーはFEELING_PROVIDER環境変数で切り替え:
        - selfhost: LiteLLM Proxy (デフォルト)
        - openrouter: OpenRouter API

        Args:
            instruction: ユーザーの着せ替え指示（日本語）
            current_description: 現在の画像の説明
            nsfw_mode: NSFWモードかどうか
            suppress_gender_discomfort_cues: 性別適合時に恥ずかしさ・官能キューを抑止

        Returns:
            (生成された英語プロンプト, コスト(USD))

        Raises:
            GameServiceError: プロンプト生成に失敗した場合
        """
        try:
            memory_priority_suffix = (
                await self._get_memory_priority_suffix() if use_memory else ""
            )
            memory_priority_suffix = append_clothing_layer_image_rule(
                memory_priority_suffix, respect_clothing_layers
            )

            result = await llm_service.generate_image_edit_prompt(
                instruction=instruction + history_context,
                current_description=current_description,
                provider_override=resolve_image_provider(),
                nsfw_mode=nsfw_mode,
                extra_system_suffix=memory_priority_suffix,
                suppress_gender_discomfort_cues=suppress_gender_discomfort_cues,
            )
            logger.info(
                f"画像編集プロンプト生成完了: provider={result.provider}, cost={result.cost_usd}"
            )
            return result.content, result.cost_usd
        except Exception as e:
            # プロンプト生成に失敗した場合は、元の指示をそのまま使用
            logger.warning(
                "Prompt generation failed, using original instruction: %s", e
            )
            return instruction + history_context, None

    async def _generate_image_only_edit_prompt(
        self,
        instruction: str,
        current_description: str,
        nsfw_mode: bool = False,
        novelai_model_override: str | None = None,
        use_memory: bool = False,
        respect_clothing_layers: bool = False,
        session_characters_section: str = "",
        language: str = "ja",
        text_to_image: bool = False,
    ) -> tuple[str, float | None]:
        """自由な自然言語指示から画像編集プロンプトを生成する。

        text_to_image が True の場合は前画像の説明を使わず、新規生成
        （text-to-image）用のシステム/ユーザープロンプトに切り替える。
        """
        if text_to_image:
            system_prompt = get_image_only_generate_system_prompt(
                resolve_image_provider(),
                nsfw_mode,
            )
        else:
            system_prompt = get_image_only_edit_system_prompt(
                resolve_image_provider(),
                nsfw_mode,
            )
        memory_priority_suffix = (
            await self._get_memory_priority_suffix(language) if use_memory else ""
        )
        system_prompt += append_clothing_layer_image_rule(
            memory_priority_suffix,
            respect_clothing_layers,
        )
        if text_to_image:
            user_prompt = build_image_only_generate_prompt(instruction)
        else:
            user_prompt = build_image_only_edit_prompt(
                instruction=instruction,
                current_description=current_description,
            )
        if session_characters_section:
            user_prompt = f"{user_prompt}\n\n{session_characters_section}"

        try:
            result = await llm_service.generate_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                novelai_model_override=novelai_model_override,
            )
            logger.info(
                "画像のみプロンプト生成完了: provider=%s, cost=%s",
                result.provider,
                result.cost_usd,
            )
            return result.content.strip(), result.cost_usd
        except Exception as e:
            logger.warning(
                "Image-only prompt generation failed, using original instruction: %s",
                e,
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
        novelai_model_override: str | None = None,
        respect_clothing_layers: bool = False,
        history_context: str = "",
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
        user_prompt += history_context

        try:
            result = await llm_service.generate_feeling(
                system_prompt=append_clothing_layer_feeling_rule(
                    FEELING_SYSTEM_PROMPT, respect_clothing_layers
                ),
                user_prompt=user_prompt,
                novelai_model_override=novelai_model_override,
                max_tokens=1024,
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
        enable_multiple_people: bool = False,
        novelai_model_override: str | None = None,
        use_memory: bool = True,
        respect_clothing_layers: bool = False,
        gender_congruence: GenderCongruenceResult | None = None,
        history_context: str = "",
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
            gender_congruence: 性別適合判定結果

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
            enable_multiple_people=enable_multiple_people,
            gender_congruence=gender_congruence,
        )
        user_prompt += history_context
        from .conversation import get_language_rules

        system_prompt = f"{system_prompt}\n\n{get_language_rules(language)}"
        if use_memory:
            system_prompt += await self._get_memory_priority_suffix(language)

        system_prompt = append_clothing_layer_feeling_rule(
            system_prompt, respect_clothing_layers
        )
        async for chunk in self._stream_feeling(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            language=language,
            error_context="心境ストリーミングエラー",
            novelai_model_override=novelai_model_override,
        ):
            yield chunk

    async def _stream_feeling(
        self,
        system_prompt: str,
        user_prompt: str,
        language: str,
        error_context: str = "Feeling stream error",
        novelai_model_override: str | None = None,
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
                novelai_model_override=novelai_model_override,
                max_tokens=1024,
                usage_callback=record_cost,
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
        enable_multiple_people: bool = False,
        novelai_model_override: str | None = None,
        use_memory: bool = True,
        respect_clothing_layers: bool = False,
        history_context: str = "",
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
            enable_multiple_people: 複数人表示モード

        Yields:
            テキストチャンク
        """
        system_prompt, user_prompt = build_self_mode_feeling_prompt(
            before_desc=before_desc,
            after_desc=after_desc,
            instruction=instruction,
            self_profile=self_profile,
            nsfw_mode=nsfw_mode,
            enable_multiple_people=enable_multiple_people,
        )
        user_prompt += history_context
        from .conversation import get_language_rules

        system_prompt = f"{system_prompt}\n\n{get_language_rules(language)}"
        if use_memory:
            system_prompt += await self._get_memory_priority_suffix(language)

        system_prompt = append_clothing_layer_feeling_rule(
            system_prompt, respect_clothing_layers
        )
        async for chunk in self._stream_feeling(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            language=language,
            error_context="自分自身モード心境ストリーミングエラー",
            novelai_model_override=novelai_model_override,
        ):
            yield chunk

    async def _generate_reality_edit_prompt(
        self,
        instruction: str,
        current_description: str,
        nsfw_mode: bool = False,
        image_provider: str = "qwen",
        novelai_model_override: str | None = None,
        use_memory: bool = True,
        respect_clothing_layers: bool = False,
        history_context: str = "",
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
            if use_memory:
                system_prompt += await self._get_memory_priority_suffix()
            system_prompt = append_clothing_layer_image_rule(
                system_prompt, respect_clothing_layers
            )
            user_prompt = build_reality_edit_prompt(
                instruction=instruction + history_context,
                current_description=current_description,
                nsfw_mode=nsfw_mode,
            )
            result = await llm_service.generate_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                novelai_model_override=novelai_model_override,
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
        enable_multiple_people: bool = False,
        novelai_model_override: str | None = None,
        use_memory: bool = True,
        respect_clothing_layers: bool = False,
        history_context: str = "",
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
            enable_multiple_people=enable_multiple_people,
        )
        user_prompt += history_context
        from .conversation import get_language_rules

        system_prompt = f"{system_prompt}\n\n{get_language_rules(language)}"
        if use_memory:
            system_prompt += await self._get_memory_priority_suffix(language)

        system_prompt = append_clothing_layer_feeling_rule(
            system_prompt, respect_clothing_layers
        )
        async for chunk in self._stream_feeling(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            language=language,
            error_context="現実改変心境ストリーミングエラー",
            novelai_model_override=novelai_model_override,
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
        enable_multiple_people: bool = False,
        use_character_panel: bool = True,
        use_memory: bool = False,
        respect_clothing_layers: bool = False,
        use_play_memory: bool = False,
        use_history_lookback: bool | None = None,
        image_only_text_to_image: bool = False,
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
            transformation_type: 変身タイプ (costume=衣装変更, reality=現実改変)
            nsfw_mode_override: ユーザー設定からのNSFWモード（Noneの場合はセッション設定を使用）
            difficulty_override: ユーザー設定からの難易度（Noneの場合はセッション設定を使用）
            seed: 画像生成seed値（未指定時はランダム生成）
            enable_surroundings_image: 周囲状況画像を生成するか（行動モード専用）
            surroundings_include_people: 周囲画像にリアクションする通行人を含めるか
            image_only_text_to_image: 画像のみモードで前画像を使わず text-to-image で
                生成する（image_only 以外の指示タイプでは無視）

        Yields:
            StreamEvent: text/image/complete/error イベント
        """
        tracker = begin_cost_tracking()
        cost_emitted = 0.0
        logger.info(
            "Stream play: session=%s, char=%s, instruction=%s, base_history=%s, nsfw_override=%s",
            session_id,
            character_id,
            instruction[:50] if instruction else "",
            base_history_id,
            nsfw_mode_override,
        )
        original_instruction = instruction
        respect_clothing_layers_for_image = respect_clothing_layers and not bool(
            prompt_override and prompt_override.strip()
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
            history_lookback_enabled = resolve_history_lookback_enabled(
                use_history_lookback,
                instruction_type=instruction_type,
                transformation_type=transformation_type,
            )
            history_lookback_count = settings_service.get_history_lookback_count(
                session.id
            )

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
            if resolve_image_provider() == "novelai":
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
            effective_bloom_calc_method = user_settings.get(
                "bloom_calc_method", "legacy"
            )
            effective_language = normalize_language(
                language_override or user_settings.get("language")
            )
            play_memory_context = ""
            if use_play_memory:
                from .play_memory_service import play_memory_service

                play_memory_context = await play_memory_service.build_context(
                    session.id,
                    enabled=True,
                    language=effective_language,
                )
                instruction += play_memory_context
            image_instruction = original_instruction
            if use_memory:
                image_instruction += play_memory_context
            logger.info(
                f"Effective settings from user: nsfw_mode={effective_nsfw_mode}, "
                f"difficulty={effective_difficulty}, language={effective_language}"
            )

            # NovelAI text model override from user settings
            effective_novelai_text_model: str | None = user_settings.get(
                "novelai_text_model"
            )

            # NovelAI 画像モデル（ユーザー設定 + nsfw_mode から解決）
            effective_novelai_image_model = resolve_user_image_model(
                user_settings, effective_nsfw_mode
            )
            if character_references and not supports_character_references(
                effective_novelai_image_model
            ):
                logger.info(
                    "Dropping %d character references (V5 model %s does not support them)",
                    len(character_references),
                    effective_novelai_image_model,
                )
                character_references = None
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

            # 画像のみモード: 心境・ゲーム状態を生成せず画像履歴だけを更新する
            if instruction_type == "image_only":
                logger.info(
                    "Image-only mode: generating an image without narrative "
                    "(text_to_image=%s)",
                    image_only_text_to_image,
                )
                if image_only_text_to_image and resolve_image_provider() == "selfhost":
                    # ComfyUI の編集ワークフローは text-to-image を持たないため、
                    # LLM 呼び出しの前に拒否する（History は残らない）
                    raise GameServiceError(
                        "画像のみ（i2iなし）はセルフホスト（ComfyUI）では利用できません"
                    )

                last_hist = await session_store.get_latest_history(session.id)
                previous_description: str | None
                if image_only_text_to_image:
                    # 前画像の状態を引き継がず、指示・メモリ・属性だけから新規生成する
                    previous_description = None
                else:
                    previous_description = (
                        last_hist.after_description
                        if last_hist and last_hist.after_description
                        else self._build_initial_prompt(
                            gender,
                            character,
                            self_profile,
                            base_tags=custom_metadata.get("base_tags", ""),
                            enable_multiple_people=enable_multiple_people,
                        )
                    )

                describe_cost: float | None = None
                if image_only_text_to_image:
                    # ベース画像を使わないので Vision による現在画像の説明も行わない
                    current_description = ""
                elif settings.is_novelai_opus_mode:
                    current_description = previous_description or ""
                else:
                    current_description, describe_cost = await self._describe_image(
                        before_image,
                        effective_nsfw_mode,
                    )
                    record_cost(describe_cost)

                attributes = await session_store.get_session_attribute_texts(session.id)
                attribute_context = self._build_attribute_context(attributes)

                session_characters_section = ""
                novelai_characters_section: str | None = None
                if enable_multiple_people and use_character_panel:
                    try:
                        async with async_session_factory() as image_only_db:
                            character_records = (
                                await load_session_characters_for_prompt(
                                    image_only_db,
                                    session.id,
                                )
                            )
                        session_characters_section = (
                            build_session_characters_prompt_section(character_records)
                        )
                        protagonist_name, protagonist_tags = (
                            _resolve_protagonist_image_identity(
                                last_after_description=(
                                    None
                                    if image_only_text_to_image
                                    else (
                                        last_hist.after_description
                                        if last_hist
                                        else None
                                    )
                                ),
                                character=character,
                                self_profile=self_profile,
                                custom_metadata=custom_metadata,
                            )
                        )
                        novelai_characters_section = (
                            build_novelai_characters_section(
                                character_records,
                                protagonist_name=protagonist_name,
                                protagonist_tags=protagonist_tags,
                            )
                            or None
                        )
                    except Exception as exc:
                        logger.debug(
                            "session_character fetch (image-only) skipped: %s",
                            exc,
                        )

                prompt_gen_cost: float | None = None
                image_only_characters: list[dict] | None = None
                if settings.is_novelai_opus_mode:
                    image_only_system = get_action_novelai_prompt_generation_system(
                        nsfw_mode=effective_nsfw_mode,
                        language=effective_language,
                        clothing_color_consistency=clothing_color_consistency,
                        enable_multiple_people=enable_multiple_people,
                    )
                    memory_suffix = (
                        await self._get_memory_priority_suffix(effective_language)
                        if use_memory
                        else ""
                    )
                    memory_suffix = append_clothing_layer_image_rule(
                        memory_suffix,
                        respect_clothing_layers_for_image,
                    )
                    if image_only_text_to_image:
                        # 前プロンプトからの保持ルールを無効化する（system 末尾に付与）
                        memory_suffix += IMAGE_ONLY_TEXT_TO_IMAGE_RULE
                    generated_prompt = await llm_service.generate_novelai_image_prompt(
                        instruction=image_instruction + attribute_context,
                        previous_prompt=previous_description,
                        nsfw_mode=effective_nsfw_mode,
                        language=effective_language,
                        system_prompt_override=image_only_system,
                        novelai_model_override=effective_novelai_text_model,
                        enable_multiple_people=enable_multiple_people,
                        session_characters_section=novelai_characters_section,
                        extra_system_suffix=memory_suffix,
                    )
                    try:
                        parsed_prompt = _parse_novelai_prompt_json(generated_prompt)
                        if parsed_prompt:
                            image_edit_prompt, image_only_characters = parsed_prompt
                        else:
                            raise ValueError("Missing character or scene key")
                    except (json.JSONDecodeError, ValueError, KeyError) as exc:
                        logger.warning(
                            "Image-only prompt split failed, using flat prompt: %s",
                            exc,
                        )
                        image_edit_prompt = generated_prompt
                else:
                    (
                        image_edit_prompt,
                        prompt_gen_cost,
                    ) = await self._generate_image_only_edit_prompt(
                        instruction=image_instruction + attribute_context,
                        current_description=current_description,
                        nsfw_mode=effective_nsfw_mode,
                        novelai_model_override=effective_novelai_text_model,
                        use_memory=use_memory,
                        respect_clothing_layers=respect_clothing_layers_for_image,
                        session_characters_section=session_characters_section,
                        language=effective_language,
                        text_to_image=image_only_text_to_image,
                    )
                    record_cost(prompt_gen_cost)

                final_prompt = image_edit_prompt
                if prompt_override and prompt_override.strip():
                    if resolve_image_provider() == "novelai":
                        final_prompt = self._merge_prompts(
                            image_edit_prompt,
                            prompt_override.strip(),
                        )
                    else:
                        final_prompt = prompt_override.strip()
                if resolve_image_provider() == "novelai":
                    final_prompt = enhance_prompt_for_novelai(
                        final_prompt, nsfw_mode=effective_nsfw_mode
                    )

                image_api_prompt = final_prompt
                image_api_characters = image_only_characters
                image_negative_prompt = negative_prompt
                (
                    final_prompt,
                    image_api_prompt,
                    image_only_characters,
                    image_api_characters,
                    image_negative_prompt,
                ) = self._prepare_clothing_layer_image_payload(
                    final_prompt,
                    image_only_characters,
                    previous_prompt=previous_description,
                    instruction=original_instruction,
                    respect_clothing_layers=respect_clothing_layers_for_image,
                    negative_prompt=negative_prompt,
                )

                after_description = final_prompt
                if image_only_characters and isinstance(
                    image_only_characters[0].get("prompt"), str
                ):
                    after_description = image_only_characters[0]["prompt"]

                image_data, image_cost, image_seed = await self._generate_image(
                    None if image_only_text_to_image else before_image,
                    image_api_prompt,
                    nsfw_mode=effective_nsfw_mode,
                    # text-to-image ではマスクも渡さない（渡すとインペイント経路に入る）
                    mask_bytes=None if image_only_text_to_image else mask_bytes,
                    inpaint_strength=inpaint_strength,
                    inpaint_noise=inpaint_noise,
                    negative_prompt=image_negative_prompt,
                    character_references=character_references,
                    seed=seed,
                    characters=image_api_characters,
                    novelai_image_model_override=effective_novelai_image_model,
                )
                record_cost(image_cost)

                history = await session_store.add_history(
                    session_id=session.id,
                    instruction=original_instruction,
                    image_data=image_data,
                    feeling_text="",
                    before_description=current_description,
                    after_description=after_description,
                    instruction_type="image_only",
                    seed=image_seed,
                )
                await session_store.update_session(
                    session_id=session.id,
                    current_image_path=history.image_path,
                )

                image_b64 = base64.b64encode(image_data).decode("utf-8")
                yield StreamEvent(
                    type="image",
                    data={
                        "image": image_b64,
                        "history_id": history.id,
                        "seed": image_seed,
                    },
                )

                cost_event, cost_emitted = _pending_cost_event(tracker, cost_emitted)
                if cost_event is not None:
                    yield cost_event

                anlas_event = await self._get_anlas_event()
                if anlas_event:
                    yield anlas_event

                yield StreamEvent(
                    type="complete",
                    data={
                        "session_id": session.id,
                        "transformation_count": session.transformation_count,
                        "before_desc": current_description,
                        "after_desc": after_description,
                        "feeling_text": "",
                        "history_id": history.id,
                    },
                )
                return

            # ── action mode: scene-change image + text, skip params/tags ──
            if instruction_type == "action":
                logger.info(
                    "Action mode: generating scene-change image + text in parallel"
                )

                # 開花度ベースの段階説明用に現在のstatesを取得
                action_stats = await session_store.get_or_create_session_stats(
                    session.id
                )

                # セッション属性を取得（テキスト・画像プロンプトの両方に反映）
                action_attributes = await session_store.get_session_attribute_texts(
                    session.id
                )
                action_attribute_context = self._build_attribute_context(
                    action_attributes
                )
                if action_attributes:
                    logger.info(f"Session attributes (action): {action_attributes}")

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
                        enable_multiple_people=enable_multiple_people,
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
                            novelai_model_override=effective_novelai_text_model,
                        )
                        record_cost(getattr(summary_result, "cost_usd", None))
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
                if history_lookback_enabled:
                    try:
                        recent_actions = await session_store.get_recent_instructions(
                            session.id, limit=history_lookback_count
                        )
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

                # 005: マルチキャラクター在席時のプロンプト追加
                multi_char_section: str | None = None
                multi_char_image_section: str | None = None
                if enable_multiple_people and use_character_panel:
                    try:
                        async with async_session_factory() as _mc_db:
                            _mc_records = await load_session_characters_for_prompt(
                                _mc_db, session_id
                            )
                        multi_char_section = (
                            build_session_characters_prompt_section(_mc_records) or None
                        )
                        protagonist_name, protagonist_tags = (
                            _resolve_protagonist_image_identity(
                                last_after_description=(
                                    last_hist.after_description if last_hist else None
                                ),
                                character=character,
                                self_profile=self_profile,
                                custom_metadata=custom_metadata,
                            )
                        )
                        # FR-010: 初期 upsert — DB に主人公レコードが未存在で
                        # 解決されたタグがある場合、CharacterPanel 表示用に
                        # プレースホルダーを作成する。今ターン終了後の
                        # 事後 upsert で最新タグに上書きされる。
                        has_protagonist = any(r.is_protagonist for r in _mc_records)
                        if (
                            not has_protagonist
                            and protagonist_name
                            and protagonist_tags
                        ):
                            try:
                                async with async_session_factory() as _init_db:
                                    await upsert_protagonist_session_character(
                                        _init_db,
                                        session_id,
                                        name=protagonist_name,
                                        appearance_tags=protagonist_tags,
                                    )
                                    await _init_db.commit()
                                # 主人公追加後のレコードをリロード
                                async with async_session_factory() as _mc_db2:
                                    _mc_records = (
                                        await load_session_characters_for_prompt(
                                            _mc_db2, session_id
                                        )
                                    )
                                logger.info(
                                    "[FR-010 action] initial protagonist upsert ok"
                                )
                            except Exception as _init_exc:
                                logger.warning(
                                    "[FR-010 action] initial upsert failed: %s",
                                    _init_exc,
                                )
                        logger.info(
                            "[FR-010 action] enable_multi=%s, records=%d, "
                            "last_hist=%s, protagonist_name=%r, "
                            "protagonist_tags=%r",
                            enable_multiple_people,
                            len(_mc_records),
                            "yes" if last_hist else "no",
                            protagonist_name,
                            (protagonist_tags or "")[:80],
                        )
                        multi_char_image_section = (
                            build_novelai_characters_section(
                                _mc_records,
                                protagonist_name=protagonist_name,
                                protagonist_tags=protagonist_tags,
                            )
                            or None
                        )
                        logger.info(
                            "[FR-010 action] multi_char_image_section=%r",
                            (multi_char_image_section or "")[:400],
                        )
                    except Exception as _mc_exc:
                        logger.debug("session_character fetch skipped: %s", _mc_exc)

                # 行動時の性別適合。feeling_mode=gender_aware かつ self_mode 以外
                action_gender_discomfort = True
                action_feeling_mode = normalize_feeling_mode(
                    user_settings.get("feeling_mode", "legacy")
                )
                if not session.self_mode and is_gender_aware_feeling_mode(
                    action_feeling_mode
                ):
                    action_use_llm = should_use_congruence_llm(
                        action_feeling_mode,
                        bool(user_settings.get("gender_congruence_llm_enabled", False)),
                    )
                    action_congruence = await evaluate_gender_congruence(
                        instruction=original_instruction,
                        original_gender=action_gender,
                        appearance_desc=current_desc or "",
                        session_timeline=recent_actions or None,
                        attributes=action_attributes,
                        instruction_type="action",
                        use_llm=action_use_llm,
                        novelai_model_override=effective_novelai_text_model,
                    )
                    action_gender_discomfort = (
                        action_congruence.should_feel_gender_discomfort
                    )
                    logger.info(
                        "Gender congruence (action): fit=%s discomfort=%s source=%s",
                        action_congruence.fit,
                        action_gender_discomfort,
                        action_congruence.source,
                    )

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
                    enable_multiple_people=enable_multiple_people,
                    lookback_count=history_lookback_count,
                    session_characters_section=multi_char_section,
                    attributes=action_attributes,
                    gender_discomfort=action_gender_discomfort,
                )

                from .conversation import get_language_rules

                act_system = f"{act_system}\n\n{get_language_rules(effective_language)}"
                if use_memory:
                    act_system += await self._get_memory_priority_suffix(
                        effective_language
                    )

                act_system = append_clothing_layer_feeling_rule(
                    act_system, respect_clothing_layers
                )
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
                        enable_multiple_people=enable_multiple_people,
                    )
                    action_memory_suffix = (
                        await self._get_memory_priority_suffix(effective_language)
                        if use_memory
                        else ""
                    )
                    previous_prompt = current_desc  # 前回のafter_description
                    action_memory_suffix = append_clothing_layer_image_rule(
                        action_memory_suffix, respect_clothing_layers_for_image
                    )
                    action_novelai_prompt = (
                        await llm_service.generate_novelai_image_prompt(
                            instruction=(image_instruction + action_attribute_context),
                            previous_prompt=previous_prompt,
                            nsfw_mode=effective_nsfw_mode,
                            language=effective_language,
                            system_prompt_override=action_tag_system,
                            novelai_model_override=effective_novelai_text_model,
                            enable_multiple_people=enable_multiple_people,
                            session_characters_section=multi_char_image_section,
                            extra_system_suffix=action_memory_suffix,
                        )
                    )

                    # PoC: Parse JSON response for character/scene splitting
                    try:
                        result = _parse_novelai_prompt_json(action_novelai_prompt)
                        if result:
                            action_image_prompt, action_characters = result
                            logger.info(
                                "Action prompt split OK: %d characters, scene_len=%d",
                                len(action_characters),
                                len(action_image_prompt),
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
                        image_provider=resolve_image_provider(),
                        nsfw_mode=effective_nsfw_mode,
                    )
                    if use_memory:
                        action_edit_system += await self._get_memory_priority_suffix(
                            effective_language
                        )
                    action_edit_system = append_clothing_layer_image_rule(
                        action_edit_system, respect_clothing_layers_for_image
                    )
                    action_edit_user = build_action_image_edit_prompt(
                        instruction=image_instruction + action_attribute_context,
                        current_description=vision_desc,
                    )
                    # LLM経由で編集プロンプトを生成
                    action_image_prompt_result = await llm_service.generate_text(
                        system_prompt=action_edit_system,
                        user_prompt=action_edit_user,
                        novelai_model_override=effective_novelai_text_model,
                    )
                    record_cost(getattr(action_image_prompt_result, "cost_usd", None))
                    action_image_prompt = action_image_prompt_result.content.strip()
                    action_prompt_desc = action_image_prompt
                    logger.info(
                        "Action non-NovelAI: generated edit prompt len=%d",
                        len(action_image_prompt),
                    )

                # NovelAI品質タグの付与
                if resolve_image_provider() == "novelai" and action_image_prompt:
                    action_image_prompt = enhance_prompt_for_novelai(
                        action_image_prompt, nsfw_mode=effective_nsfw_mode
                    )

                action_image_api_prompt = action_image_prompt
                action_image_api_characters = action_characters
                action_negative_prompt = negative_prompt
                (
                    action_image_prompt,
                    action_image_api_prompt,
                    action_characters,
                    action_image_api_characters,
                    action_negative_prompt,
                ) = self._prepare_clothing_layer_image_payload(
                    action_image_prompt,
                    action_characters,
                    previous_prompt=current_desc,
                    instruction=original_instruction,
                    respect_clothing_layers=respect_clothing_layers_for_image,
                    negative_prompt=negative_prompt,
                )
                # 履歴用: inventory 付き状態を保持
                if action_characters and isinstance(
                    action_characters[0].get("prompt"), str
                ):
                    action_prompt_desc = action_characters[0]["prompt"]
                else:
                    action_prompt_desc = action_image_prompt

                # ── T011: Parallel text + image generation ──
                action_event_queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()
                action_text_chunks: list[str] = []

                async def action_text_producer():
                    """アクションモノローグテキストをイベントキューにストリーミング送信する。"""
                    try:
                        async for chunk in llm_service.generate_feeling_stream(
                            system_prompt=act_system,
                            user_prompt=act_user,
                            novelai_model_override=effective_novelai_text_model,
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
                            action_image_api_prompt,
                            nsfw_mode=effective_nsfw_mode,
                            mask_bytes=mask_bytes,
                            inpaint_strength=action_inpaint_strength,
                            inpaint_noise=inpaint_noise,
                            negative_prompt=action_negative_prompt,
                            character_references=character_references,
                            seed=seed,
                            characters=action_image_api_characters,
                            novelai_image_model_override=effective_novelai_image_model,
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
                        record_cost(action_image_cost)
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
                    # 未確定の生成タグも破棄し、CharacterPanel を誤更新しない
                    action_prompt_desc = current_desc
                    action_characters = None
                elif action_image_data is not None:
                    final_action_image = action_image_data

                # ── T013: Save to history with generated image ──
                history = await session_store.add_history(
                    session_id=session.id,
                    instruction=original_instruction,
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

                # FR-010 / FR-013: 確定タグ直書き + 容姿自然文の自動更新
                # プロンプト構築フェーズではなく add_history 直後に実行し、
                # CharacterPanel に今ターンの見た目を反映する。
                if enable_multiple_people and use_character_panel:
                    await _sync_session_characters_after_turn(
                        session_id=session.id,
                        after_description=action_prompt_desc,
                        character_prompts=action_characters,
                        instruction_text=instruction,
                        character=character,
                        self_profile=self_profile,
                        custom_metadata=custom_metadata,
                        log_label="action",
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

                # コストイベントを送信（ここまでの API 料金の未通知分）
                cost_event, cost_emitted = _pending_cost_event(tracker, cost_emitted)
                if cost_event is not None:
                    yield cost_event

                # US5: Anlas balance event (NovelAI only)
                anlas_event = await self._get_anlas_event()
                if anlas_event:
                    yield anlas_event

                # ── US2 T031-T033: Surroundings image generation (NovelAI only) ──
                surroundings_image_path: str | None = None
                if enable_surroundings_image and resolve_image_provider() == "novelai":
                    logger.info("Generating surroundings image for action...")
                    # 現実改変属性を検出（既に取得済みの action_attributes を再利用）
                    reality_alter_texts = [
                        a for a in action_attributes if a.startswith("[現実改変]")
                    ]
                    has_reality_attrs = len(reality_alter_texts) > 0
                    (
                        surroundings_data,
                        surroundings_cost,
                        surroundings_seed,
                    ) = await self._generate_surroundings_image(
                        instruction=image_instruction,
                        before_description=current_desc,
                        after_description=action_prompt_desc,
                        nsfw_mode=effective_nsfw_mode,
                        include_people=surroundings_include_people,
                        is_reality_change=has_reality_attrs,
                        reality_alter_descriptions=reality_alter_texts
                        if has_reality_attrs
                        else None,
                        novelai_model_override=effective_novelai_text_model,
                        novelai_image_model_override=effective_novelai_image_model,
                    )
                    record_cost(surroundings_cost)

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
                        cost_event, cost_emitted = _pending_cost_event(
                            tracker, cost_emitted
                        )
                        if cost_event is not None:
                            yield cost_event

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
                        "feeling_text": action_full_text,
                        "history_id": history.id,
                    },
                )
                return

            # 現在のstatsを取得 (T059: 開花度ベースの心理段階)
            current_stats = await session_store.get_or_create_session_stats(session.id)
            current_bloom = current_stats.bloom

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
                        enable_multiple_people=enable_multiple_people,
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
                record_cost(describe_cost)
            logger.debug("Before: %s...", before_desc[:100] if before_desc else "empty")

            # 2.1 セッション属性を取得（プロンプトに反映）
            attributes = await session_store.get_session_attribute_texts(session.id)
            attribute_context = self._build_attribute_context(attributes)
            if attributes:
                logger.info(f"Session attributes: {attributes}")

            # 3. 画像編集プロンプトを生成（変身タイプに応じて分岐）
            logger.info(f"Generating image edit prompt... (type={transformation_type})")
            is_reality = transformation_type == "reality"
            transformation_history_context = ""
            if history_lookback_enabled:
                try:
                    recent_history = await session_store.get_recent_instructions(
                        session.id, limit=history_lookback_count
                    )
                    transformation_history_context = build_history_context(
                        recent_history
                    )
                except Exception:
                    logger.debug("変身用セッションタイムラインの取得に失敗")
            image_history_context = (
                ""
                if prompt_override and prompt_override.strip()
                else transformation_history_context
            )

            # 005: マルチキャラクター在席時は登録済みキャラのタグを画像プロンプトに注入 (FR-010)
            dress_up_multi_char_image_section: str | None = None
            logger.info(
                "[FR-010 dress-up] enable_multiple_people=%s",
                enable_multiple_people,
            )
            if enable_multiple_people and use_character_panel:
                try:
                    async with async_session_factory() as _mc_db:
                        _mc_records = await load_session_characters_for_prompt(
                            _mc_db, session.id
                        )
                    _dress_last_hist = await session_store.get_latest_history(
                        session.id
                    )
                    protagonist_name, protagonist_tags = (
                        _resolve_protagonist_image_identity(
                            last_after_description=(
                                _dress_last_hist.after_description
                                if _dress_last_hist
                                else None
                            ),
                            character=character,
                            self_profile=self_profile,
                            custom_metadata=custom_metadata,
                        )
                    )
                    # FR-010: 初期 upsert — DB に主人公レコードが未存在で
                    # 解決されたタグがある場合、CharacterPanel 表示用に
                    # プレースホルダーを作成する。今ターン終了後の
                    # 事後 upsert で最新タグに上書きされる。
                    has_protagonist = any(r.is_protagonist for r in _mc_records)
                    if not has_protagonist and protagonist_name and protagonist_tags:
                        try:
                            async with async_session_factory() as _init_db:
                                await upsert_protagonist_session_character(
                                    _init_db,
                                    session.id,
                                    name=protagonist_name,
                                    appearance_tags=protagonist_tags,
                                )
                                await _init_db.commit()
                            async with async_session_factory() as _mc_db2:
                                _mc_records = await load_session_characters_for_prompt(
                                    _mc_db2, session.id
                                )
                            logger.info(
                                "[FR-010 dress-up] initial protagonist upsert ok"
                            )
                        except Exception as _init_exc:
                            logger.warning(
                                "[FR-010 dress-up] initial upsert failed: %s",
                                _init_exc,
                            )
                    logger.info(
                        "[FR-010 dress-up] records=%d, last_hist=%s, "
                        "protagonist_name=%r, protagonist_tags=%r",
                        len(_mc_records),
                        "yes" if _dress_last_hist else "no",
                        protagonist_name,
                        (protagonist_tags or "")[:80],
                    )
                    dress_up_multi_char_image_section = (
                        build_novelai_characters_section(
                            _mc_records,
                            protagonist_name=protagonist_name,
                            protagonist_tags=protagonist_tags,
                        )
                        or None
                    )
                    logger.info(
                        "[FR-010 dress-up] dress_up_multi_char_image_section=%r",
                        (dress_up_multi_char_image_section or "")[:400],
                    )
                except Exception as _mc_exc:
                    logger.debug(
                        "session_character fetch (dress-up) skipped: %s", _mc_exc
                    )

            # 性別適合判定は feeling_mode=gender_aware のときのみ
            # legacy は従来どおり（常にTSF抵抗心境・開花増分あり）
            feeling_mode = normalize_feeling_mode(
                user_settings.get("feeling_mode", "legacy")
            )
            gender_aware_feeling = is_gender_aware_feeling_mode(feeling_mode)
            dress_up_congruence: GenderCongruenceResult | None = None
            if gender_aware_feeling and not session.self_mode and not is_reality:
                congruence_timeline: list[tuple[str, str]] = []
                try:
                    timeline_raw = await session_store.get_session_timeline(
                        session.id, limit=30
                    )
                    congruence_timeline = list(reversed(timeline_raw))
                except Exception:
                    logger.debug("congruence timeline fetch skipped")
                use_congruence_llm = should_use_congruence_llm(
                    feeling_mode,
                    bool(user_settings.get("gender_congruence_llm_enabled", False)),
                )
                dress_up_congruence = await evaluate_gender_congruence(
                    instruction=original_instruction,
                    original_gender=gender,
                    appearance_desc=before_desc,
                    session_timeline=congruence_timeline,
                    attributes=attributes,
                    instruction_type="dress_up",
                    use_llm=use_congruence_llm,
                    novelai_model_override=effective_novelai_text_model,
                )
                logger.info(
                    "Gender congruence (dress_up): mode=%s fit=%s discomfort=%s "
                    "source=%s llm=%s reason=%s",
                    feeling_mode,
                    dress_up_congruence.fit,
                    dress_up_congruence.should_feel_gender_discomfort,
                    dress_up_congruence.source,
                    use_congruence_llm,
                    dress_up_congruence.reason,
                )
            else:
                logger.info(
                    "Feeling mode=%s — skip gender congruence for dress_up",
                    feeling_mode,
                )

            suppress_gender_image_cues = (
                dress_up_congruence is not None
                and not dress_up_congruence.should_feel_gender_discomfort
            )

            # T008: NovelAI Opusモード用のプロンプト生成
            generated_novelai_prompt: str | None = None
            prompt_gen_cost: float | None = None
            # Phase2: V4 character/scene prompt 分離用
            dress_up_characters: list[dict] | None = None

            if is_novelai_opus_mode:
                dress_up_memory_suffix = (
                    await self._get_memory_priority_suffix(effective_language)
                    if use_memory
                    else ""
                )
                # NovelAI GLM-4.6でプロンプト生成
                dress_up_memory_suffix = append_clothing_layer_image_rule(
                    dress_up_memory_suffix, respect_clothing_layers_for_image
                )
                generated_novelai_prompt = (
                    await llm_service.generate_novelai_image_prompt(
                        instruction=(
                            image_instruction
                            + attribute_context
                            + image_history_context
                        ),
                        previous_prompt=previous_prompt,
                        nsfw_mode=effective_nsfw_mode,
                        language=effective_language,
                        clothing_color_consistency=clothing_color_consistency,
                        enable_multiple_people=enable_multiple_people,
                        novelai_model_override=effective_novelai_text_model,
                        session_characters_section=dress_up_multi_char_image_section,
                        extra_system_suffix=dress_up_memory_suffix,
                        suppress_gender_discomfort_cues=suppress_gender_image_cues,
                    )
                )

                # Phase2: JSONレスポンスをパースしてcharacter/sceneを分離
                try:
                    result = _parse_novelai_prompt_json(generated_novelai_prompt)
                    if result:
                        image_edit_prompt, dress_up_characters = result
                        logger.info(
                            "Dress-up prompt split OK: %d characters, scene_len=%d",
                            len(dress_up_characters),
                            len(image_edit_prompt),
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
                    instruction=image_instruction + attribute_context,
                    current_description=before_desc,
                    nsfw_mode=effective_nsfw_mode,
                    image_provider=resolve_image_provider(),
                    novelai_model_override=effective_novelai_text_model,
                    use_memory=use_memory,
                    respect_clothing_layers=respect_clothing_layers_for_image,
                    history_context=image_history_context,
                )
                record_cost(prompt_gen_cost)
            else:
                # 衣装変更用プロンプト生成（既存）
                (
                    image_edit_prompt,
                    prompt_gen_cost,
                ) = await self._generate_image_edit_prompt(
                    instruction=image_instruction + attribute_context,
                    current_description=before_desc,
                    nsfw_mode=effective_nsfw_mode,
                    novelai_model_override=effective_novelai_text_model,
                    use_memory=use_memory,
                    suppress_gender_discomfort_cues=suppress_gender_image_cues,
                    respect_clothing_layers=respect_clothing_layers_for_image,
                    history_context=image_history_context,
                )
                record_cost(prompt_gen_cost)

            # T009: NovelAI専用 - 直接プロンプト指定とのマージ
            final_prompt = image_edit_prompt
            if prompt_override and prompt_override.strip():
                if is_novelai_opus_mode or resolve_image_provider() == "novelai":
                    # プロンプトオーバーライドを結合（ユーザー指定タグを追加）
                    final_prompt = self._merge_prompts(
                        image_edit_prompt, prompt_override.strip()
                    )
                    logger.info(
                        f"Merged prompt with override: {len(final_prompt)} chars"
                    )
                else:
                    final_prompt = prompt_override.strip()
            if resolve_image_provider() == "novelai":
                # T014: 品質タグを追加
                final_prompt = enhance_prompt_for_novelai(
                    final_prompt, nsfw_mode=effective_nsfw_mode
                )

            # 衣装レイヤー: visual と着用インベントリを分離（履歴は inventory 付きを保持）
            dress_image_prompt = final_prompt
            dress_image_characters = dress_up_characters
            dress_negative_prompt = negative_prompt
            (
                final_prompt,
                dress_image_prompt,
                dress_up_characters,
                dress_image_characters,
                dress_negative_prompt,
            ) = self._prepare_clothing_layer_image_payload(
                final_prompt,
                dress_up_characters,
                previous_prompt=previous_prompt,
                instruction=original_instruction,
                respect_clothing_layers=respect_clothing_layers_for_image,
                negative_prompt=negative_prompt,
            )

            # 4. 真の並列処理: asyncio.Queue を使ってイベントを統合
            # T010: NovelAI Opusモードでは生成プロンプトをafter_descとして使用
            # レイヤーON時は inventory 付き character/state プロンプトを優先して状態継続する
            if is_novelai_opus_mode:
                if (
                    dress_up_characters
                    and isinstance(dress_up_characters[0].get("prompt"), str)
                    and dress_up_characters[0]["prompt"].strip()
                ):
                    inferred_after_desc = dress_up_characters[0]["prompt"]
                elif final_prompt.strip():
                    inferred_after_desc = final_prompt
                elif generated_novelai_prompt:
                    inferred_after_desc = generated_novelai_prompt
                else:
                    inferred_after_desc = f"{instruction}に変身した姿"
            elif is_reality:
                inferred_after_desc = f"「{instruction}」という現実改変により変化した姿"
            else:
                inferred_after_desc = f"{instruction}に変身した姿"
                if respect_clothing_layers_for_image and final_prompt.strip():
                    # 非Opusでも inventory 行があれば心境入力へ載せる
                    inferred_after_desc = (
                        f"{inferred_after_desc}\n\n{final_prompt}"
                        if "WORN_UNDER_LAYERS:" in final_prompt
                        else inferred_after_desc
                    )

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
                            enable_multiple_people=enable_multiple_people,
                            novelai_model_override=effective_novelai_text_model,
                            use_memory=use_memory,
                            respect_clothing_layers=respect_clothing_layers,
                            history_context=transformation_history_context,
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
                            enable_multiple_people=enable_multiple_people,
                            novelai_model_override=effective_novelai_text_model,
                            use_memory=use_memory,
                            respect_clothing_layers=respect_clothing_layers,
                            history_context=transformation_history_context,
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
                            enable_multiple_people=enable_multiple_people,
                            novelai_model_override=effective_novelai_text_model,
                            use_memory=use_memory,
                            gender_congruence=dress_up_congruence,
                            respect_clothing_layers=respect_clothing_layers,
                            history_context=transformation_history_context,
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
                        dress_image_prompt,
                        costume_image_bytes,
                        nsfw_mode=effective_nsfw_mode,
                        mask_bytes=mask_bytes,
                        inpaint_strength=inpaint_strength,
                        inpaint_noise=inpaint_noise,
                        negative_prompt=dress_negative_prompt,
                        character_references=character_references,
                        seed=seed,
                        characters=dress_image_characters,
                        novelai_image_model_override=effective_novelai_image_model,
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
                    record_cost(image_cost)
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
                instruction=original_instruction,
                image_data=image_data,
                feeling_text=full_text,
                before_description=before_desc,
                after_description=inferred_after_desc,
                instruction_type=instruction_type or "dress_up",
                seed=image_seed,
            )

            # FR-010 / FR-013: 確定タグ直書き + 容姿自然文の自動更新
            # プロンプト構築フェーズではなく add_history 直後に実行し、
            # CharacterPanel に今ターンの見た目を反映する。
            # 現実改変ケースも Opus では inferred_after_desc / dress_up_characters
            # から同一パスで処理される。
            if enable_multiple_people and use_character_panel:
                await _sync_session_characters_after_turn(
                    session_id=session.id,
                    after_description=inferred_after_desc,
                    character_prompts=dress_up_characters,
                    instruction_text=original_instruction,
                    character=character,
                    self_profile=self_profile,
                    custom_metadata=custom_metadata,
                    log_label="dress-up",
                )

            # 5.1. タグ分類 (T023)
            tags = classify_tags(original_instruction)
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
                reality_attr_text = f"[現実改変] {original_instruction}"
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

            # 実績ヘルパーはルーター側にあり、モジュールレベルで import すると
            # routes パッケージ経由で game_router と循環するため遅延 import する。
            # self_mode 分岐の外側で束縛しないと self_mode 側で未定義になる
            from ..routes.achievements_router import (
                ACHIEVEMENTS,
                check_achievement,
                check_achievements,
                get_global_stats,
                get_user_achievements,
                save_user_achievement,
                update_achievement_counts,
            )

            # ── self_mode: skip parameter/critical/ending/achievement (US5 T026) ──
            if not session.self_mode:
                # 5.2. パラメータ計算と更新 (T015, T016)
                stats = await session_store.get_or_create_session_stats(session.id)
                old_bloom = stats.bloom

                # 現実改変は服装適合で開花を止めない。通常着せ替えのみ discomfort を反映
                gender_discomfort_for_params = True
                if not is_reality and dress_up_congruence is not None:
                    gender_discomfort_for_params = (
                        dress_up_congruence.should_feel_gender_discomfort
                    )

                bloom_delta, shame_delta, adaptation_delta = calculate_parameter_change(
                    tags,
                    stats,
                    bloom_calc_method=effective_bloom_calc_method,
                    gender_discomfort=gender_discomfort_for_params,
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

                # spec 004 (T010): stat 変動ログを (session_id, history_id) 単位で記録
                # delta は clamp 後の実適用差分 (new_value - prev_value)。
                # delta=0 はヘルパ側でスキップされる。
                await session_store.record_parameter_change_log(
                    session_id=session.id,
                    history_id=history.id,
                    stat_changes=[
                        (
                            "bloom",
                            new_stats.bloom - stats.bloom,
                            stats.bloom,
                            new_stats.bloom,
                        ),
                        (
                            "shame",
                            new_stats.shame - stats.shame,
                            stats.shame,
                            new_stats.shame,
                        ),
                        (
                            "adaptation",
                            new_stats.adaptation - stats.adaptation,
                            stats.adaptation,
                            new_stats.adaptation,
                        ),
                    ],
                    reason=instruction_type or "dress_up",
                )

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
                        gender=gender,
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

            # self_mode: self系実績のみ判定
            if session.self_mode:
                try:
                    user_achievements = get_user_achievements()
                    already_unlocked = {
                        ua.achievement_id for ua in user_achievements if ua.unlocked
                    }
                    self_stats = get_global_stats()
                    self_achievements = [
                        a for a in ACHIEVEMENTS.values() if a.category == "self"
                    ]
                    for achievement in self_achievements:
                        if achievement.id in already_unlocked:
                            continue
                        if check_achievement(achievement, self_stats):
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
                                f"Self-mode achievement unlocked: {achievement.name}"
                            )
                except Exception as e:
                    logger.warning(f"Self-mode achievement check failed: {e}")

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

            # 8.5 コストイベントを送信（この手番で記録された API 料金の未通知分）
            cost_event, cost_emitted = _pending_cost_event(tracker, cost_emitted)
            if cost_event is not None:
                yield cost_event

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
                    "feeling_text": full_text,
                    "history_id": history.id,
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
                resolved = resolve_stored_image_path(session.current_image_path)
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
                    resolved = resolve_stored_image_path(session.current_image_path)
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
        tracker = begin_cost_tracking()
        cost_emitted = 0.0
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
                resolved = resolve_stored_image_path(session.current_image_path)
                if resolved:
                    current_image_bytes = resolved.read_bytes()

            if current_image_bytes is None:
                raise GameServiceError("現在の画像が見つかりません")

            # 3. キャラクター情報取得
            character: Character | None = None
            if session.character_id:
                character = character_manager.get_by_id(session.character_id)

            # 4. 現在の画像を説明
            yield StreamEvent(type="status", data={"message": "画像を分析中..."})

            current_description, describe_cost = await self._describe_image(
                current_image_bytes
            )
            record_cost(describe_cost)
            logger.info(f"Current description: {current_description[:100]}...")

            # 5. 初期画像を取得
            initial_image_bytes: bytes | None = None
            if character:
                with contextlib.suppress(FileNotFoundError):
                    initial_image_bytes = character_manager.get_image_bytes(character)

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
            # 画像モデルはユーザー設定から解決（この経路のnsfwは従来どおりFalse固定）
            user_settings = await session_store.get_user_settings()
            new_image, image_cost, improve_seed = await self._generate_image(
                initial_image_bytes,
                improve_instruction,
                novelai_image_model_override=resolve_user_image_model(
                    user_settings, False
                ),
            )
            record_cost(image_cost)
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
            cost_event, cost_emitted = _pending_cost_event(tracker, cost_emitted)
            if cost_event is not None:
                yield cost_event

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

    async def generate_standing_portrait(
        self,
        session_id: str,
        nsfw_mode: bool | None = None,
    ) -> tuple[bytes, float | None]:
        """現在の姿を、初期立ち絵と同じ構図の全身立ち絵として再生成する

        履歴には保存せず、生成結果のみを返す（おまけ機能）。

        Args:
            session_id: セッションID

        Returns:
            (生成された画像, API料金USD)

        Raises:
            GameServiceError: セッション・画像が見つからない、または生成に失敗した場合
        """
        session = await session_store.get_session_by_id(session_id)
        if session is None:
            raise GameServiceError(f"セッションが見つかりません: {session_id}")

        current_image_bytes: bytes | None = None
        if session.current_image_path:
            resolved = resolve_stored_image_path(session.current_image_path)
            if resolved:
                current_image_bytes = resolved.read_bytes()

        if current_image_bytes is None:
            raise GameServiceError("現在の画像が見つかりません")

        if nsfw_mode is None:
            stats = await session_store.get_session_stats(session_id)
            effective_nsfw_mode = bool(stats.nsfw_mode) if stats else False
        else:
            effective_nsfw_mode = nsfw_mode

        # 構図の基準となる立ち絵。変身後は女性想定のため常に char2 を参照する
        reference_character = character_manager.get_by_id(
            STANDING_PORTRAIT_REFERENCE_CHARACTER_ID
        )
        if reference_character is None:
            raise GameServiceError("立ち絵の参照キャラクターが見つかりません")
        try:
            reference_image_bytes = character_manager.get_image_bytes(
                reference_character
            )
        except FileNotFoundError as e:
            raise GameServiceError(f"立ち絵の参照画像が見つかりません: {e}") from e

        # NovelAI Opusモードでは Vision LLM が使えないため、
        # 直近履歴に保存された生成プロンプト(after_description)を現在の姿の記述として使う
        tracker = begin_cost_tracking()
        describe_cost: float | None = None
        if settings.is_novelai_opus_mode:
            latest_history = await session_store.get_latest_history(session_id)
            current_description = (
                latest_history.after_description if latest_history else None
            )
            if not current_description:
                raise GameServiceError("NovelAIモードでは、変身履歴が1件以上必要です")
            instruction = enhance_prompt_for_novelai(
                f"{current_description}, {STANDING_PORTRAIT_COMPOSITION_TAGS}",
                nsfw_mode=effective_nsfw_mode,
            )
        else:
            current_description, describe_cost = await self._describe_image(
                current_image_bytes, nsfw_mode=effective_nsfw_mode
            )
            record_cost(describe_cost)
            instruction = (
                "Redraw this character as a full body standing reference sheet, "
                "keeping the exact same camera framing, character scale, and centered "
                "composition as the input image. "
                "Replace the appearance and outfit with the following: "
                f"{current_description}. "
                f"Composition tags: {STANDING_PORTRAIT_COMPOSITION_TAGS}. "
                "High quality, detailed anime illustration."
            )

        user_settings = await session_store.get_user_settings()
        new_image, image_cost, _seed = await self._generate_image(
            reference_image_bytes,
            instruction,
            nsfw_mode=effective_nsfw_mode,
            negative_prompt=STANDING_PORTRAIT_NEGATIVE_PROMPT,
            novelai_image_model_override=resolve_user_image_model(
                user_settings, effective_nsfw_mode
            ),
        )
        record_cost(image_cost)

        return new_image, tracker.total_usd or None

    async def preview_prompts(
        self,
        session_id: str | None,
        instruction: str,
        transformation_type: str = "costume",
        instruction_type: str | None = None,
        respect_clothing_layers: bool = False,
        use_history_lookback: bool | None = None,
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
        effective_novelai_text_model: str | None = None
        history_context = ""
        history_lookback_enabled = resolve_history_lookback_enabled(
            use_history_lookback,
            instruction_type=instruction_type,
            transformation_type=transformation_type,
        )
        history_lookback_count = settings_service.get_history_lookback_count(
            session_id if session_id else "default"
        )

        if session_id:
            try:
                # セッションと統計情報を個別に取得
                session = await session_store.get_session_by_id(session_id)
                if session:
                    stats = await session_store.get_or_create_session_stats(session_id)

                    # ユーザー設定からnsfw_modeを取得
                    user_settings = await session_store.get_user_settings(session_id)
                    nsfw_mode = user_settings.get("nsfw_mode", False)
                    effective_novelai_text_model = user_settings.get(
                        "novelai_text_model"
                    )
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
                    instruction += self._build_attribute_context(attributes)

                    # self_mode の場合、プロフィールから性別・一人称を取得
                    if session.self_mode:
                        self_profile = await session_store.get_self_profile()
                        if self_profile:
                            gender = self_profile.get("gender", gender)
                            pronoun = self_profile.get("pronoun", pronoun)
                            personality = self_profile.get("personality", "")

                    if history_lookback_enabled:
                        try:
                            recent_history = (
                                await session_store.get_recent_instructions(
                                    session_id, limit=history_lookback_count
                                )
                            )
                            if instruction_type == "action":
                                recent_actions = recent_history
                            else:
                                history_context = build_history_context(recent_history)
                        except Exception:
                            pass

                    # action プレビュー用: 前回サマリー
                    if instruction_type == "action":
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
                                    novelai_model_override=effective_novelai_text_model,
                                )
                                record_cost(getattr(summary_result, "cost_usd", None))
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
                lookback_count=history_lookback_count,
            )
            act_system += await self._get_memory_priority_suffix()

            act_system = append_clothing_layer_feeling_rule(
                act_system, respect_clothing_layers
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
                action_tag_system = append_clothing_layer_image_rule(
                    action_tag_system, respect_clothing_layers
                )
                novelai_tag_prompt = action_tag_system
                image_edit_prompt = "(NovelAI Opus: タグはLLMが動的生成)"
            else:
                action_edit_system = get_action_image_edit_system_prompt(
                    image_provider=resolve_image_provider(),
                    nsfw_mode=nsfw_mode,
                )
                action_edit_system += await self._get_memory_priority_suffix()
                action_edit_system = append_clothing_layer_image_rule(
                    action_edit_system, respect_clothing_layers
                )
                image_edit_prompt = action_edit_system

            # 周辺画像プロンプトプレビュー（現実改変属性含む）
            has_reality_attrs = len(reality_alter_texts) > 0
            from .action_prompts import (
                build_surroundings_image_user_prompt,
                get_surroundings_image_prompt_system,
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
                image_provider=resolve_image_provider(),
                novelai_model_override=effective_novelai_text_model,
                respect_clothing_layers=respect_clothing_layers,
                history_context=history_context,
            )
        else:
            image_edit_prompt, _ = await self._generate_image_edit_prompt(
                instruction=instruction,
                current_description=current_description,
                nsfw_mode=nsfw_mode,
                novelai_model_override=effective_novelai_text_model,
                respect_clothing_layers=respect_clothing_layers,
                history_context=history_context,
            )

        from .prompts import build_feeling_prompt, get_psychological_stage

        stage = get_psychological_stage(bloom, nsfw_mode)
        system_prompt = stage["system_prompt"]

        system_prompt = append_clothing_layer_feeling_rule(
            system_prompt, respect_clothing_layers
        )
        user_prompt = build_feeling_prompt(
            before_desc=current_description or "着せ替え前の状態",
            after_desc=f"{instruction}に変身した姿",
            instruction=instruction,
            pronoun=pronoun,
        )
        user_prompt += history_context

        return {
            "image_edit_prompt": image_edit_prompt,
            "feeling_system_prompt": system_prompt,
            "feeling_user_prompt": user_prompt,
            "instruction_type": instruction_type or transformation_type,
            "novelai_tag_prompt": None,
        }

    def _build_attribute_context(self, attributes: list[str] | None) -> str:
        """属性リストをプロンプト用コンテキスト文字列に整形する。

        "[現実改変]" プレフィックス属性は場面全体に適用される世界設定として、
        それ以外はキャラクター固有の属性として、それぞれ別見出しで整形する。
        """
        if not attributes:
            return ""
        reality_attrs = [a for a in attributes if a.startswith("[現実改変]")]
        normal_attrs = [a for a in attributes if not a.startswith("[現実改変]")]
        parts: list[str] = []
        if normal_attrs:
            parts.append(
                "【対象キャラクターの属性】\n"
                + "\n".join(f"- {attr}" for attr in normal_attrs)
            )
        if reality_attrs:
            parts.append(
                "【現実改変ルール（場面全体に適用 ― 全キャラクターに影響）】\n"
                + "\n".join(f"- {attr}" for attr in reality_attrs)
                + "\n（このルールは主人公だけでなく場面内の全員に適用してください）"
            )
        if not parts:
            return ""
        return "\n\n" + "\n\n".join(parts)


# グローバルサービスインスタンス
game_service = GameService()


async def _sync_session_characters_after_turn(
    *,
    session_id: str,
    after_description: str | None,
    character_prompts: list[dict] | None,
    instruction_text: str,
    character: Any | None,
    self_profile: dict | None,
    custom_metadata: dict | None,
    log_label: str,
) -> None:
    """Persist post-turn appearance onto session_character rows (FR-010 / FR-013).

    1. Prefer confirmed Opus character prompts as appearance_tags source of truth.
    2. Fall back to resolving tags from after_description / base identity.
    3. Best-effort LLM update for appearance_natural (and residual tag diffs).

    Failures are logged and never raised to the caller.
    """
    try:
        post_name, post_tags = _resolve_protagonist_image_identity(
            last_after_description=after_description,
            character=character,
            self_profile=self_profile,
            custom_metadata=custom_metadata,
        )
        # Confirmed character prompt overrides extract/fallback when present.
        if (
            character_prompts
            and isinstance(character_prompts[0], dict)
            and isinstance(character_prompts[0].get("prompt"), str)
            and character_prompts[0]["prompt"].strip()
        ):
            post_tags = character_prompts[0]["prompt"].strip()

        async with async_session_factory() as db:
            if post_name and post_tags:
                await upsert_protagonist_session_character(
                    db,
                    session_id,
                    name=post_name,
                    appearance_tags=post_tags,
                )
            if character_prompts:
                applied = await apply_character_prompt_tags(
                    db, session_id, character_prompts
                )
                if applied:
                    logger.info(
                        "[FR-010 %s] applied character prompt tags to %d row(s)",
                        log_label,
                        applied,
                    )
            await db.commit()

        if post_name and post_tags:
            logger.info(
                "[FR-010 %s] post-history upsert ok name=%r tags=%r",
                log_label,
                post_name,
                post_tags[:80],
            )
    except Exception as exc:  # noqa: BLE001 - best-effort panel sync
        logger.warning(
            "[FR-010 %s] post-history upsert failed: %s",
            log_label,
            exc,
        )

    await _async_apply_appearance_updates(session_id, instruction_text)


async def _async_apply_appearance_updates(session_id: str, action_text: str) -> None:
    """005 US2: Action / dress-up 後にキャラクター容姿の差分を適用する。

    失敗時はログに記録し、アクション応答へは伝播させない (FR-014)。
    """
    try:
        # session_character の取得
        async with async_session_factory() as db:
            records = await load_session_characters_for_prompt(db, session_id)
        if not records:
            return

        # 出力言語をユーザー設定から解決（取得失敗時は ja 既定）
        try:
            user_settings = await session_store.get_user_settings(session_id)
            effective_language = normalize_language(user_settings.get("language"))
        except Exception:  # noqa: BLE001 - 設定取得失敗は致命的でない
            effective_language = normalize_language(None)

        characters_payload = [
            {
                "id": r.id,
                "name": r.name,
                "appearance_natural": r.appearance_natural or "",
                "appearance_tags": r.appearance_tags or "",
                "appearance_lock": bool(getattr(r, "appearance_lock", False)),
                "exclude_from_effects": bool(getattr(r, "exclude_from_effects", False)),
            }
            for r in records
        ]

        updates = await llm_service.infer_appearance_updates(
            characters_payload,
            action_text,
            language=effective_language,
        )
        if not updates:
            return

        from .character_service import apply_appearance_updates

        async with async_session_factory() as db:
            await apply_appearance_updates(db, session_id, updates)
            await db.commit()
    except Exception as exc:
        logger.warning(
            "auto-appearance update skipped (session=%s): %s", session_id, exc
        )
