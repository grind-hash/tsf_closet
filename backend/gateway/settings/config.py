from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv


# BASE_DIR = backend/
BASE_DIR: Final[Path] = Path(__file__).resolve().parent.parent.parent

# .envファイルのパスを解決（ENV_FILEで上書き可能、コンテナ対応）
_env_file = os.getenv("ENV_FILE", str(BASE_DIR.parent / ".env"))
load_dotenv(_env_file, override=True)

# ログレベル設定
LOG_LEVEL: Final[str] = os.getenv("LOG_LEVEL", "INFO").upper()


def configure_logging() -> None:
    """アプリケーション全体のロギング設定を適用"""
    level = getattr(logging, LOG_LEVEL, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # uvicornのログレベルも設定
    logging.getLogger("uvicorn").setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(level)
    logging.getLogger("uvicorn.error").setLevel(level)


def _resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


# 利用可能なワークフロー名とパスのマッピング
DEFAULT_WORKFLOWS: Final[dict[str, str]] = {
    "default": "workflows/qwen_image_edit_template.json",
    "qwen_image_edit": "workflows/qwen_image_edit_template.json",
    "qwen_image_edit_local": "workflows/qwen_image_edit_template_local.json",
    # 着せ替えゲーム用: テキストプロンプトのみで着せ替え (参照画像不要)
    "instruct_game": "workflows/qwen_image_edit_template_local.json",
    # 着せ替えゲーム用 NSFW: NSFW向けモデルを使用
    "instruct_game_nsfw": "workflows/qwen_image_edit_template_local_nsfw.json",
    # 参照画像付きワークフロー (衣装画像を参照として指定する場合)
    "instruct_game_with_reference": "workflows/instruct_game_template.json",
    # txt2img (背景など編集元画像が無い生成用)。編集用と同じモデル構成で
    # LoadImage を EmptySD3LatentImage に置き換えたもの
    "qwen_image_txt2img_local": "workflows/qwen_image_txt2img_template_local.json",
    "qwen_image_txt2img_local_nsfw": (
        "workflows/qwen_image_txt2img_template_local_nsfw.json"
    ),
}


@dataclass(slots=True)
class Settings:
    """Runtime configuration for the ComfyUI gateway."""

    # ComfyUI設定
    comfyui_base_url: str = os.getenv("COMFYUI_BASE_URL", "http://127.0.0.1:8188")
    comfyui_workflow_path: Path = _resolve_path(
        os.getenv("COMFYUI_WORKFLOW_PATH", "workflows/qwen_image_edit_template.json")
    )
    # txt2img 用ワークフロー。未設定なら編集用ワークフローの命名規則から導出する
    # (get_txt2img_workflow_path を参照)
    comfyui_txt2img_workflow_path: Path | None = (
        _resolve_path(os.environ["COMFYUI_TXT2IMG_WORKFLOW_PATH"])
        if os.getenv("COMFYUI_TXT2IMG_WORKFLOW_PATH")
        else None
    )
    comfyui_client_id: str = os.getenv("COMFYUI_CLIENT_ID", "fastapi-openai-gateway")
    comfyui_request_timeout: float = float(os.getenv("COMFYUI_REQUEST_TIMEOUT", "180"))
    comfyui_poll_interval: float = float(os.getenv("COMFYUI_POLL_INTERVAL", "1.0"))
    multipart_max_part_size: int = int(
        os.getenv("MULTIPART_MAX_PART_SIZE_BYTES", str(8 * 1024 * 1024))
    )

    # LiteLLM Proxy設定 (画像説明・心境生成用)
    litellm_base_url: str = os.getenv("LITELLM_BASE_URL", "http://127.0.0.1:4000")
    litellm_llava_model: str = os.getenv("LITELLM_LLAVA_MODEL", "ollama/llava:7b")
    litellm_llm_model: str = os.getenv("LITELLM_LLM_MODEL", "ollama/llama3.2:1b")
    # 心理状態生成用モデル (gpt-oss:20b対応)
    litellm_feeling_model: str = os.getenv(
        "LITELLM_FEELING_MODEL", "ollama/gpt-oss:20b"
    )
    litellm_request_timeout: float = float(os.getenv("LITELLM_REQUEST_TIMEOUT", "60"))
    litellm_api_key: str = os.getenv("LITELLM_API_KEY", "")

    # デバッグ設定
    enable_prompt_preview: bool = (
        os.getenv("ENABLE_PROMPT_PREVIEW", "false").lower() == "true"
    )

    # 画像生成プロバイダー設定
    # selfhost: ComfyUI (デフォルト), openrouter: OpenRouter API, novelai: NovelAI Image API
    image_provider: str = os.getenv("IMAGE_PROVIDER", "selfhost")

    # OpenRouter画像生成設定
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_base_url: str = os.getenv(
        "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
    )
    openrouter_image_model: str = os.getenv(
        "OPENROUTER_IMAGE_MODEL", "google/gemini-2.5-flash-image"
    )
    openrouter_image_timeout: float = float(
        os.getenv("OPENROUTER_IMAGE_TIMEOUT", "120")
    )

    # NovelAI 画像生成設定
    novelai_api_key: str = os.getenv("NOVELAI_API_KEY", "").strip()
    # NSFWモード用（フル）モデル
    novelai_model: str = os.getenv("NOVELAI_MODEL", "nai-diffusion-4-5-full")
    novelai_inpaint_model: str = os.getenv(
        "NOVELAI_INPAINT_MODEL", "nai-diffusion-4-5-full-inpainting"
    )
    # 非NSFWモード用（Curated）モデル - NSFWプロンプトを自動ブロック
    novelai_curated_model: str = os.getenv(
        "NOVELAI_CURATED_MODEL", "nai-diffusion-4-5-curated"
    )
    novelai_curated_inpaint_model: str = os.getenv(
        "NOVELAI_CURATED_INPAINT_MODEL", "nai-diffusion-4-5-curated-inpainting"
    )
    novelai_inpaint_fallback_model: str = os.getenv(
        "NOVELAI_INPAINT_FALLBACK_MODEL", ""
    )
    novelai_inpaint_action: str = os.getenv("NOVELAI_INPAINT_ACTION", "infill")
    novelai_size: str = os.getenv("NOVELAI_SIZE", "portrait")
    novelai_steps: int = int(os.getenv("NOVELAI_STEPS", "28"))
    novelai_scale: float = float(os.getenv("NOVELAI_SCALE", "5.0"))
    novelai_uc_preset: str = os.getenv("NOVELAI_UC_PRESET", "light")
    novelai_negative_prompt: str = os.getenv(
        "NOVELAI_NEGATIVE_PROMPT",
        "lowres, bad anatomy, bad hands, text, logo, watermark, blurry, extra digits, deformed",
    )
    novelai_i2i_strength: float = float(os.getenv("NOVELAI_I2I_STRENGTH", "0.9"))
    novelai_i2i_noise: float = float(os.getenv("NOVELAI_I2I_NOISE", "0.0"))
    novelai_mask_dilate_px: int = int(os.getenv("NOVELAI_MASK_DILATE_PX", "0"))

    # 画像説明プロバイダー設定
    # selfhost: LiteLLM Proxy (デフォルト), openrouter: OpenRouter API
    image_description_provider: str = os.getenv(
        "IMAGE_DESCRIPTION_PROVIDER", "selfhost"
    )
    # 心境生成プロバイダー設定
    # selfhost: LiteLLM Proxy (デフォルト), openrouter: OpenRouter API, novelai: NovelAI Text API
    feeling_provider: str = os.getenv("FEELING_PROVIDER", "selfhost")

    # NovelAI テキストAPI設定 (心境生成用)
    # OpenAI互換エンドポイント: https://text.novelai.net/oa/v1
    # 注意: stream=true が必須 (falseだとtoken_idsが返される)
    novelai_text_base_url: str = os.getenv(
        "NOVELAI_TEXT_BASE_URL", "https://text.novelai.net/oa/v1"
    )
    novelai_text_model: str = os.getenv("NOVELAI_TEXT_MODEL", "glm-4-6")
    novelai_text_timeout: float = float(os.getenv("NOVELAI_TEXT_TIMEOUT", "60"))

    # OpenRouter LLM設定 (画像説明・心境生成用)
    openrouter_vision_model: str = os.getenv(
        "OPENROUTER_VISION_MODEL", "mistralai/ministral-14b-2512"
    )
    openrouter_llm_model: str = os.getenv("OPENROUTER_LLM_MODEL", "x-ai/grok-4.1-fast")
    openrouter_llm_timeout: float = float(os.getenv("OPENROUTER_LLM_TIMEOUT", "60"))

    # キャラクター設定
    characters_dir: Path = _resolve_path(
        os.getenv("CHARACTERS_DIR", "images/characters")
    )

    # データ永続化設定
    database_path: Path = _resolve_path(
        os.getenv("DATABASE_PATH", "data/database.sqlite")
    )
    history_images_dir: Path = _resolve_path(
        os.getenv("HISTORY_IMAGES_DIR", "data/history_images")
    )
    # マスク履歴保存先 (デフォルト: data/history_masks)
    history_masks_dir: Path = _resolve_path(
        os.getenv("HISTORY_MASKS_DIR", "data/history_masks")
    )
    # Prompt Expander の生成/アップロード画像保存先 (デフォルト: data/prompt_expander_images)
    prompt_expander_images_dir: Path = _resolve_path(
        os.getenv("PROMPT_EXPANDER_IMAGES_DIR", "data/prompt_expander_images")
    )
    # マスクプリセット保存先 (デフォルト: data/preset_masks)
    preset_masks_dir: Path = _resolve_path(
        os.getenv("PRESET_MASKS_DIR", "data/preset_masks")
    )
    # 3D アバター(VRM)の保存先 (デフォルト: data/avatar_models)
    avatar_models_dir: Path = _resolve_path(
        os.getenv("AVATAR_MODELS_DIR", "data/avatar_models")
    )
    # VRM アップロードの上限バイト数 (デフォルト: 128 MiB)。
    # multipart_max_part_size(8 MiB)は画像プロキシ専用で、VRM には使わない
    avatar_upload_max_bytes: int = int(
        os.getenv("AVATAR_UPLOAD_MAX_BYTES", str(128 * 1024 * 1024))
    )
    history_max_count: int = int(os.getenv("HISTORY_MAX_COUNT", "50"))

    # AivisSpeech (Windows only)
    aivis_engine_base_url: str = os.getenv(
        "AIVIS_ENGINE_BASE_URL", "http://127.0.0.1:10101"
    )
    aivis_engine_startup_timeout: float = float(
        os.getenv("AIVIS_ENGINE_STARTUP_TIMEOUT", "300")
    )
    aivis_engine_download_url: str = os.getenv(
        "AIVIS_ENGINE_DOWNLOAD_URL",
        "https://github.com/Aivis-Project/AivisSpeech/releases/download/1.1.0-preview.4/AivisSpeech-Windows-x64-1.1.0-preview.4.zip",
    )
    aivis_default_model_url: str = os.getenv(
        "AIVIS_DEFAULT_MODEL_URL",
        "https://hub.aivis-project.com/aivm-models/7fc08a41-b64d-456d-8b22-8e1284674775",
    )
    aivis_download_timeout: float = float(os.getenv("AIVIS_DOWNLOAD_TIMEOUT", "300"))
    # CPUモードでの音声合成は数十秒〜数分かかることがあるため、GPUモードより長めの
    # デフォルト値にしている。環境変数で調整可能。
    aivis_synthesis_timeout: float = float(os.getenv("AIVIS_SYNTHESIS_TIMEOUT", "300"))
    aivis_max_download_bytes: int = int(
        os.getenv("AIVIS_MAX_DOWNLOAD_BYTES", str(2 * 1024 * 1024 * 1024))
    )
    aivis_allowed_download_hosts: str = os.getenv(
        "AIVIS_ALLOWED_DOWNLOAD_HOSTS",
        "github.com,objects.githubusercontent.com,release-assets.githubusercontent.com,hub.aivis-project.com",
    )

    def __post_init__(self) -> None:
        if self.multipart_max_part_size <= 0:
            raise ValueError("MULTIPART_MAX_PART_SIZE_BYTES must be a positive integer")

    @property
    def is_novelai_opus_mode(self) -> bool:
        """NovelAI Opus mode: both image and description providers are novelai."""
        return (
            self.image_provider == "novelai"
            and self.image_description_provider == "novelai"
        )

    def ensure_workflow_exists(self, workflow_path: Path | None = None) -> None:
        path = workflow_path or self.comfyui_workflow_path
        if not path.exists():
            raise FileNotFoundError(f"ComfyUI workflow template not found: {path}")

    def get_txt2img_workflow_path(self, edit_workflow_path: Path | None = None) -> Path:
        """編集元画像なしの生成(背景など)に使うワークフローのパスを返す。

        優先順位:
        1. COMFYUI_TXT2IMG_WORKFLOW_PATH
        2. 編集用ワークフローのファイル名の "image_edit" を "image_txt2img" に
           置き換えたファイル (例: qwen_image_edit_template_local_nsfw.json →
           qwen_image_txt2img_template_local_nsfw.json) が存在すればそれ
        3. 同梱の qwen_image_txt2img_template_local.json
        """
        if self.comfyui_txt2img_workflow_path is not None:
            return self.comfyui_txt2img_workflow_path
        edit_path = edit_workflow_path or self.comfyui_workflow_path
        derived_name = edit_path.name.replace("image_edit", "image_txt2img")
        if derived_name != edit_path.name:
            derived_path = edit_path.with_name(derived_name)
            if derived_path.exists():
                return derived_path
        return _resolve_path(DEFAULT_WORKFLOWS["qwen_image_txt2img_local"])

    def get_workflow_path(self, workflow_name: str | None = None) -> Path:
        """ワークフロー名からパスを取得する。

        Args:
            workflow_name: ワークフロー名 (例: "instruct_game", "default")
                          Noneの場合はデフォルトのワークフローパスを返す

        Returns:
            Path: ワークフローファイルのパス

        Raises:
            ValueError: 未知のワークフロー名が指定された場合
        """
        if workflow_name is None:
            return self.comfyui_workflow_path

        if workflow_name in DEFAULT_WORKFLOWS:
            return _resolve_path(DEFAULT_WORKFLOWS[workflow_name])

        raise ValueError(
            f"Unknown workflow: {workflow_name}. "
            f"Available workflows: {list(DEFAULT_WORKFLOWS.keys())}"
        )


settings = Settings()
