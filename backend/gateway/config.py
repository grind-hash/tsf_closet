from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from dotenv import load_dotenv


load_dotenv(override=True)

BASE_DIR: Final[Path] = Path(__file__).resolve().parent.parent


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
    # 変身ゲーム用: テキストプロンプトのみで変身 (参照画像不要)
    "instruct_game": "workflows/qwen_image_edit_template_local.json",
    # 参照画像付きワークフロー (衣装画像を参照として指定する場合)
    "instruct_game_with_reference": "workflows/instruct_game_template.json",
}


@dataclass(slots=True)
class Settings:
    """Runtime configuration for the ComfyUI gateway."""

    # ComfyUI設定
    comfyui_base_url: str = os.getenv("COMFYUI_BASE_URL", "http://127.0.0.1:8188")
    comfyui_workflow_path: Path = _resolve_path(
        os.getenv("COMFYUI_WORKFLOW_PATH", "workflows/qwen_image_edit_template.json")
    )
    comfyui_client_id: str = os.getenv("COMFYUI_CLIENT_ID", "fastapi-openai-gateway")
    comfyui_request_timeout: float = float(os.getenv("COMFYUI_REQUEST_TIMEOUT", "180"))
    comfyui_poll_interval: float = float(os.getenv("COMFYUI_POLL_INTERVAL", "1.0"))
    multipart_max_part_size: int = int(
        os.getenv("MULTIPART_MAX_PART_SIZE_BYTES", str(8 * 1024 * 1024))
    )

    # LiteLLM Proxy設定 (画像説明・心境生成用)
    litellm_base_url: str = os.getenv("LITELLM_BASE_URL", "http://192.168.11.91:4000")
    litellm_llava_model: str = os.getenv("LITELLM_LLAVA_MODEL", "ollama/llava:7b")
    litellm_llm_model: str = os.getenv("LITELLM_LLM_MODEL", "ollama/gemma3:4b")
    # 心理状態生成用モデル (gpt-oss:20b対応)
    litellm_feeling_model: str = os.getenv(
        "LITELLM_FEELING_MODEL", "ollama/gpt-oss:20b"
    )
    litellm_request_timeout: float = float(os.getenv("LITELLM_REQUEST_TIMEOUT", "60"))
    litellm_api_key: str = os.getenv("LITELLM_API_KEY", "")

    # 画像生成プロバイダー設定
    # selfhost: ComfyUI (デフォルト), openrouter: OpenRouter API
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

    # 画像説明プロバイダー設定
    # selfhost: LiteLLM Proxy (デフォルト), openrouter: OpenRouter API
    image_description_provider: str = os.getenv("IMAGE_DESCRIPTION_PROVIDER", "selfhost")
    # 心境生成プロバイダー設定
    # selfhost: LiteLLM Proxy (デフォルト), openrouter: OpenRouter API
    feeling_provider: str = os.getenv("FEELING_PROVIDER", "selfhost")

    # OpenRouter LLM設定 (画像説明・心境生成用)
    openrouter_vision_model: str = os.getenv(
        "OPENROUTER_VISION_MODEL", "ollama/gemma3:4b"
    )
    openrouter_llm_model: str = os.getenv(
        "OPENROUTER_LLM_MODEL", "ollama/gemma3:4b"
    )
    openrouter_llm_timeout: float = float(
        os.getenv("OPENROUTER_LLM_TIMEOUT", "60")
    )

    # コンテンツフィルター設定
    # selfhost: LiteLLM Proxy, openrouter: OpenRouter API
    content_filter_provider: str = os.getenv("CONTENT_FILTER_PROVIDER", "selfhost")
    content_filter_model: str = os.getenv(
        "CONTENT_FILTER_MODEL", "ollama/gemma3:4b"
    )
    content_filter_timeout: float = float(
        os.getenv("CONTENT_FILTER_TIMEOUT", "10")
    )
    # LLMベースのコンテンツフィルターを有効にするか
    content_filter_llm_enabled: bool = os.getenv(
        "CONTENT_FILTER_LLM_ENABLED", "true"
    ).lower() == "true"

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
    history_max_count: int = int(os.getenv("HISTORY_MAX_COUNT", "50"))

    def __post_init__(self) -> None:
        if self.multipart_max_part_size <= 0:
            raise ValueError("MULTIPART_MAX_PART_SIZE_BYTES must be a positive integer")

    def ensure_workflow_exists(self, workflow_path: Path | None = None) -> None:
        path = workflow_path or self.comfyui_workflow_path
        if not path.exists():
            raise FileNotFoundError(f"ComfyUI workflow template not found: {path}")

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
