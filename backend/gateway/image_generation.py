"""
画像生成サービス

セルフホスト（ComfyUI）とOpenRouterの切り替えロジック付き画像生成処理。
デフォルトはセルフホストを使用。
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

import httpx

from .comfy import ComfyUIClient, ComfyUIResult
from .config import settings

logger = logging.getLogger(__name__)

# プロバイダータイプ
ProviderType = Literal["selfhost", "openrouter"]


@dataclass
class UsageInfo:
    """API使用量情報"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ImageGenerationResult:
    """画像生成結果"""

    images: List[bytes]
    provider: ProviderType
    # OpenRouter使用時のAPI料金情報
    usage: Optional[UsageInfo] = None
    cost_usd: Optional[float] = None  # USD単位の料金
    model: Optional[str] = None


class OpenRouterImageError(Exception):
    """OpenRouter画像生成エラー"""


class OpenRouterImageClient:
    """OpenRouter経由の画像生成クライアント"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.api_key = api_key or settings.openrouter_api_key
        self.base_url = base_url or settings.openrouter_base_url
        self.model = model or settings.openrouter_image_model
        self.timeout = timeout or settings.openrouter_image_timeout

        if not self.api_key:
            raise ValueError("OpenRouter API key is required")

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://interactive-changing-room.local",
            "X-Title": "Interactive Changing Room",
        }

    async def generate(
        self,
        prompt: str,
        image_bytes: Optional[bytes] = None,
    ) -> ImageGenerationResult:
        """画像を生成する

        Args:
            prompt: 画像生成プロンプト
            image_bytes: 編集元画像（指定時は画像編集モード）

        Returns:
            ImageGenerationResult: 生成された画像

        Raises:
            OpenRouterImageError: API呼び出しに失敗した場合
        """
        messages: List[Dict[str, Any]] = []

        # 編集元画像がある場合はマルチモーダル形式
        if image_bytes:
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_b64}"
                            },
                        },
                    ],
                }
            )
        else:
            messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "modalities": ["image", "text"],
            "messages": messages,
            # 料金情報をレスポンスに含める
            "usage": {"include": True},
        }

        logger.debug(
            f"OpenRouter image generation request: model={self.model}, "
            f"prompt_length={len(prompt)}, has_image={image_bytes is not None}"
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._get_headers(),
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()

            # デバッグ: レスポンス構造を出力
            logger.info(f"OpenRouter response keys: {result.keys()}")
            if "choices" in result and result["choices"]:
                choice = result["choices"][0]
                logger.info(f"Choice keys: {choice.keys()}")
                if "message" in choice:
                    msg = choice["message"]
                    logger.info(f"Message keys: {msg.keys()}")
                    if "content" in msg:
                        content = msg["content"]
                        if isinstance(content, str):
                            logger.info(f"Content type: str, length: {len(content)}, prefix: {content[:100] if len(content) > 100 else content}")
                        elif isinstance(content, list):
                            logger.info(f"Content type: list, len: {len(content)}")
                            for i, item in enumerate(content[:2]):  # 最初の2つだけ
                                logger.info(f"  Content[{i}]: {type(item)}, keys: {item.keys() if isinstance(item, dict) else 'N/A'}")

            # レスポンスから画像を抽出
            images = self._extract_images(result)

            if not images:
                logger.warning("No images returned from OpenRouter")
                raise OpenRouterImageError("No images in response")

            # 使用量・料金情報を抽出
            usage_info, cost_usd = self._extract_usage(result)

            if cost_usd is not None:
                logger.info(
                    f"OpenRouter generated {len(images)} image(s), "
                    f"cost: ${cost_usd:.6f} USD"
                )
            else:
                logger.info(f"OpenRouter generated {len(images)} image(s)")

            return ImageGenerationResult(
                images=images,
                provider="openrouter",
                usage=usage_info,
                cost_usd=cost_usd,
                model=self.model,
            )

        except httpx.HTTPStatusError as e:
            error_body = e.response.text if e.response else "No response body"
            logger.error(f"OpenRouter API error: {e.response.status_code} - {error_body}")
            raise OpenRouterImageError(
                f"API error: {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            logger.error(f"OpenRouter request error: {e}")
            raise OpenRouterImageError(f"Request error: {e}") from e

    def _extract_images(self, response: Dict[str, Any]) -> List[bytes]:
        """レスポンスから画像データを抽出

        OpenRouterのGemini画像生成レスポンスは以下の形式:
        - message.images: 画像データのリスト（Gemini形式）
        - message.content: テキストまたはdata:imageのURL（他モデル）
        """
        images: List[bytes] = []

        choices = response.get("choices", [])
        for choice in choices:
            message = choice.get("message", {})

            # Gemini形式: message.images フィールド
            images_field = message.get("images")
            if images_field and isinstance(images_field, list):
                for img in images_field:
                    if isinstance(img, str):
                        # Base64データの場合
                        if img.startswith("data:image"):
                            try:
                                _, b64_data = img.split(",", 1)
                                images.append(base64.b64decode(b64_data))
                            except (ValueError, base64.binascii.Error) as e:
                                logger.warning(f"Failed to decode image from images field: {e}")
                        else:
                            # 純粋なBase64の場合
                            try:
                                images.append(base64.b64decode(img))
                            except base64.binascii.Error as e:
                                logger.warning(f"Failed to decode raw base64: {e}")
                    elif isinstance(img, dict):
                        # Gemini形式: {'type': '...', 'image_url': {...}, 'index': 0}
                        image_url_field = img.get("image_url")
                        
                        # image_urlが辞書の場合 {'url': 'data:image/...'}
                        if isinstance(image_url_field, dict):
                            url = image_url_field.get("url") or image_url_field.get("data")
                        elif isinstance(image_url_field, str):
                            url = image_url_field
                        else:
                            # フォールバック: 他のキーを試す
                            url = (
                                img.get("url")
                                or img.get("b64_json")
                                or img.get("data")
                            )
                        
                        if url and isinstance(url, str):
                            if url.startswith("data:image"):
                                try:
                                    _, b64_data = url.split(",", 1)
                                    images.append(base64.b64decode(b64_data))
                                    logger.debug(f"Extracted image from images[].image_url")
                                except (ValueError, base64.binascii.Error) as e:
                                    logger.warning(f"Failed to decode image_url: {e}")
                            else:
                                # 純粋なBase64の場合
                                try:
                                    images.append(base64.b64decode(url))
                                    logger.debug(f"Extracted raw base64 from images[]")
                                except base64.binascii.Error as e:
                                    logger.warning(f"Failed to decode raw base64: {e}")

            # 従来形式: content が data:image で始まる文字列
            content = message.get("content")
            if isinstance(content, str) and content.startswith("data:image"):
                try:
                    _, b64_data = content.split(",", 1)
                    images.append(base64.b64decode(b64_data))
                except (ValueError, base64.binascii.Error) as e:
                    logger.warning(f"Failed to decode image from content: {e}")

            # 従来形式: content がリスト（マルチパート）
            elif isinstance(content, list):
                for part in content:
                    if part.get("type") == "image_url":
                        url = part.get("image_url", {}).get("url", "")
                        if url.startswith("data:image"):
                            try:
                                _, b64_data = url.split(",", 1)
                                images.append(base64.b64decode(b64_data))
                            except (ValueError, base64.binascii.Error) as e:
                                logger.warning(f"Failed to decode image: {e}")

        return images

    def _extract_usage(
        self, response: Dict[str, Any]
    ) -> tuple[Optional[UsageInfo], Optional[float]]:
        """レスポンスから使用量・料金情報を抽出

        OpenRouterのレスポンスには以下が含まれる:
        - usage: {prompt_tokens, completion_tokens, total_tokens}
        - usage.cost または別途 x-openrouter-cost ヘッダー
        """
        usage_data = response.get("usage", {})
        usage_info: Optional[UsageInfo] = None
        cost_usd: Optional[float] = None

        if usage_data:
            usage_info = UsageInfo(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )
            # OpenRouterは usage.cost にUSD料金を返す場合がある
            if "cost" in usage_data:
                cost_usd = float(usage_data["cost"])

        # 代替: x-openrouter-cost ヘッダーから料金取得
        # (httpxのレスポンスオブジェクトが必要なため、ここでは対応しない)

        return usage_info, cost_usd


class ImageGenerationService:
    """プロバイダー切り替え付き画像生成サービス"""

    def __init__(self, provider: Optional[ProviderType] = None):
        """
        Args:
            provider: 使用するプロバイダー（未指定時は環境変数から取得）
        """
        self._default_provider: ProviderType = provider or self._resolve_provider()
        self._comfy_client: Optional[ComfyUIClient] = None
        self._openrouter_client: Optional[OpenRouterImageClient] = None

    def _resolve_provider(self) -> ProviderType:
        """環境変数からプロバイダーを解決"""
        provider = settings.image_provider.lower()
        if provider in ("selfhost", "openrouter"):
            return provider  # type: ignore
        logger.warning(
            f"Unknown IMAGE_PROVIDER '{provider}', falling back to 'selfhost'"
        )
        return "selfhost"

    def _get_comfy_client(self) -> ComfyUIClient:
        """ComfyUIクライアントを取得（遅延初期化）"""
        if self._comfy_client is None:
            self._comfy_client = ComfyUIClient()
        return self._comfy_client

    def _get_openrouter_client(self) -> OpenRouterImageClient:
        """OpenRouterクライアントを取得（遅延初期化）"""
        if self._openrouter_client is None:
            self._openrouter_client = OpenRouterImageClient()
        return self._openrouter_client

    async def generate_image(
        self,
        prompt: str,
        image_bytes: Optional[bytes] = None,
        *,
        provider_override: Optional[ProviderType] = None,
        **comfy_kwargs: Any,
    ) -> ImageGenerationResult:
        """画像を生成する

        Args:
            prompt: 画像生成プロンプト
            image_bytes: 編集元画像（オプション）
            provider_override: 一時的にプロバイダーを変更
            **comfy_kwargs: ComfyUI用の追加パラメータ

        Returns:
            ImageGenerationResult: 生成された画像
        """
        provider = provider_override or self._default_provider

        logger.info(f"Image generation with provider: {provider}")

        if provider == "openrouter":
            client = self._get_openrouter_client()
            return await client.generate(prompt=prompt, image_bytes=image_bytes)
        else:
            # セルフホスト (ComfyUI)
            client = self._get_comfy_client()

            if image_bytes is None:
                # 新規生成の場合はダミー画像が必要（ComfyUIの仕様）
                # 実際の使用ケースに応じて調整が必要
                raise ValueError(
                    "ComfyUI requires an input image. "
                    "Use edit_image() instead or provide image_bytes."
                )

            result: ComfyUIResult = await client.image_edit(
                image_bytes=image_bytes,
                prompt=prompt,
                **comfy_kwargs,
            )
            return ImageGenerationResult(images=result.images, provider="selfhost")

    async def edit_image(
        self,
        image_bytes: bytes,
        prompt: str,
        *,
        provider_override: Optional[ProviderType] = None,
        **comfy_kwargs: Any,
    ) -> ImageGenerationResult:
        """画像を編集する

        Args:
            image_bytes: 編集元画像
            prompt: 編集指示プロンプト
            provider_override: 一時的にプロバイダーを変更
            **comfy_kwargs: ComfyUI用の追加パラメータ

        Returns:
            ImageGenerationResult: 編集された画像
        """
        return await self.generate_image(
            prompt=prompt,
            image_bytes=image_bytes,
            provider_override=provider_override,
            **comfy_kwargs,
        )

    async def health_check(self) -> Dict[str, bool]:
        """各プロバイダーの接続状態を確認

        Returns:
            各プロバイダーの接続可否
        """
        results: Dict[str, bool] = {}

        # ComfyUI チェック
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{settings.comfyui_base_url}/system_stats")
                results["selfhost"] = resp.status_code == 200
        except Exception:
            results["selfhost"] = False

        # OpenRouter チェック
        if settings.openrouter_api_key:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(
                        f"{settings.openrouter_base_url}/models",
                        headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                    )
                    results["openrouter"] = resp.status_code == 200
            except Exception:
                results["openrouter"] = False
        else:
            results["openrouter"] = False

        return results


# グローバルサービスインスタンス
image_service = ImageGenerationService()
