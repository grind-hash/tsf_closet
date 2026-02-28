"""
画像生成サービス

セルフホスト（ComfyUI）とOpenRouterの切り替えロジック付き画像生成処理。
デフォルトはセルフホストを使用。
"""

from __future__ import annotations

import base64
import logging
import random
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Dict, List, Literal, Optional

import httpx
from PIL import Image, ImageFilter

from .comfy import ComfyUIClient, ComfyUIResult
from ..settings.config import settings
from novelai import AsyncNovelAI
from novelai.types import Character, CharacterReference, GenerateImageParams, I2iParams
from novelai.exceptions import NovelAIError
from novelai._utils.converter import async_convert_user_params_to_api_request

logger = logging.getLogger(__name__)

# プロバイダータイプ
ProviderType = Literal["selfhost", "openrouter", "novelai"]


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
    seed: Optional[int] = None


class OpenRouterImageError(Exception):
    """OpenRouter画像生成エラー"""


class NovelAIImageError(Exception):
    """NovelAI画像生成エラー"""


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
            "X-Title": "TSF Game",
        }

    async def generate(
        self,
        prompt: str,
        image_bytes: Optional[bytes] = None,
        reference_image_bytes: Optional[bytes] = None,
    ) -> ImageGenerationResult:
        """画像を生成する

        Args:
            prompt: 画像生成プロンプト
            image_bytes: 編集元画像（指定時は画像編集モード）
            reference_image_bytes: 衣装参照画像（オプション）

        Returns:
            ImageGenerationResult: 生成された画像

        Raises:
            OpenRouterImageError: API呼び出しに失敗した場合
        """
        messages: List[Dict[str, Any]] = []

        # 編集元画像がある場合はマルチモーダル形式
        if image_bytes:
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            content: List[Dict[str, Any]] = [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                },
            ]
            # 衣装参照画像がある場合は追加
            if reference_image_bytes:
                ref_b64 = base64.b64encode(reference_image_bytes).decode("utf-8")
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{ref_b64}"},
                    }
                )
                logger.info("Adding costume reference image to request")
            messages.append({"role": "user", "content": content})
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
            f"prompt_length={len(prompt)}, has_image={image_bytes is not None}, "
            f"has_reference={reference_image_bytes is not None}"
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
                            logger.info(
                                f"Content type: str, length: {len(content)}, prefix: {content[:100] if len(content) > 100 else content}"
                            )
                        elif isinstance(content, list):
                            logger.info(f"Content type: list, len: {len(content)}")
                            for i, item in enumerate(content[:2]):  # 最初の2つだけ
                                logger.info(
                                    f"  Content[{i}]: {type(item)}, keys: {item.keys() if isinstance(item, dict) else 'N/A'}"
                                )

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
            logger.error(
                f"OpenRouter API error: {e.response.status_code} - {error_body}"
            )
            raise OpenRouterImageError(f"API error: {e.response.status_code}") from e
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
                                logger.warning(
                                    f"Failed to decode image from images field: {e}"
                                )
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
                            url = image_url_field.get("url") or image_url_field.get(
                                "data"
                            )
                        elif isinstance(image_url_field, str):
                            url = image_url_field
                        else:
                            # フォールバック: 他のキーを試す
                            url = (
                                img.get("url") or img.get("b64_json") or img.get("data")
                            )

                        if url and isinstance(url, str):
                            if url.startswith("data:image"):
                                try:
                                    _, b64_data = url.split(",", 1)
                                    images.append(base64.b64decode(b64_data))
                                    logger.debug(
                                        "Extracted image from images[].image_url"
                                    )
                                except (ValueError, base64.binascii.Error) as e:
                                    logger.warning(f"Failed to decode image_url: {e}")
                            else:
                                # 純粋なBase64の場合
                                try:
                                    images.append(base64.b64decode(url))
                                    logger.debug("Extracted raw base64 from images[]")
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


class NovelAIImageClient:
    """NovelAI経由の画像生成クライアント"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        inpaint_model: Optional[str] = None,
        inpaint_action: Optional[str] = None,
        inpaint_fallback_model: Optional[str] = None,
        size: Optional[str] = None,
        steps: Optional[int] = None,
        scale: Optional[float] = None,
        uc_preset: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        i2i_strength: Optional[float] = None,
        i2i_noise: Optional[float] = None,
        nsfw_mode: bool = True,
    ):
        self.api_key = api_key or settings.novelai_api_key
        self.nsfw_mode = nsfw_mode
        # NSFWモードに応じてモデルを選択
        # NSFWモード: fullモデル（明示的に有効化された場合のみ）
        # 非NSFWモード: curatedモデル（NSFWプロンプトを自動ブロック）
        if nsfw_mode:
            self.model = model or settings.novelai_model
            self.inpaint_model = inpaint_model or settings.novelai_inpaint_model
        else:
            self.model = model or settings.novelai_curated_model
            self.inpaint_model = inpaint_model or settings.novelai_curated_inpaint_model
        self.inpaint_fallback_model = (
            inpaint_fallback_model or settings.novelai_inpaint_fallback_model
        )
        logger.info(
            f"NovelAIImageClient initialized: nsfw_mode={nsfw_mode}, "
            f"model={self.model}, inpaint_model={self.inpaint_model}"
        )
        self.inpaint_action = inpaint_action or settings.novelai_inpaint_action
        self.size = size or settings.novelai_size
        self.steps = steps or settings.novelai_steps
        self.scale = scale or settings.novelai_scale
        self.uc_preset = uc_preset or settings.novelai_uc_preset
        self.negative_prompt = negative_prompt or settings.novelai_negative_prompt
        self.i2i_strength = i2i_strength or settings.novelai_i2i_strength
        self.i2i_noise = i2i_noise or settings.novelai_i2i_noise
        self._client: Optional[AsyncNovelAI] = None

        if not self.api_key:
            raise ValueError("NOVELAI_API_KEY is required for NovelAI provider")

    async def _get_client(self) -> AsyncNovelAI:
        if self._client is None:
            self._client = AsyncNovelAI(api_key=self.api_key)
        return self._client

    def _format_prompt(self, prompt: str) -> str:
        """NovelAI向けに軽く整形

        - 改行や余分な空白を削除
        - 長文指示でもタグ列として扱えるようにカンマ区切りを優先
        """
        compact = " ".join(prompt.strip().split())
        compact = compact.replace("、", ", ").replace("。", ", ")
        # NovelAIでの「before/after並列」誤生成を防ぐため、単一カット指示を強調
        no_panel_suffix = (
            ", single frame, one character only, single shot, single pose, "
            "show only the transformed state, solo portrait, one subject, "
            "no before/after panels, no split screen, no side-by-side comparison, "
            "no duplicate characters, no twins, no clones, center composition, "
            "same person, same face, same hairstyle, same hair color, same skin tone"
        )
        return compact + no_panel_suffix

    async def generate(
        self,
        prompt: str,
        image_bytes: Optional[bytes] = None,
        reference_image_bytes: Optional[bytes] = None,  # 未使用（今後の拡張用）
        mask_bytes: Optional[bytes] = None,
        negative_prompt_override: Optional[str] = None,
        inpaint_strength_override: Optional[float] = None,
        noise_override: Optional[float] = None,
        character_references: Optional[List[Dict[str, Any]]] = None,
        seed: Optional[int] = None,
        characters: Optional[List[Dict[str, Any]]] = None,
    ) -> ImageGenerationResult:
        """画像生成 / 画像変換 (i2i)"""
        client = await self._get_client()

        # i2i強度の決定:
        # 1. フロントエンドから明示的に指定された場合はそれを優先
        # 2. 指定がない場合はサーバー設定のデフォルト値を使用
        # （マスクの有無にかかわらず、フロントエンドの指定値を尊重）
        if inpaint_strength_override is not None:
            strength = inpaint_strength_override
        else:
            strength = self.i2i_strength
        if strength > 0.99:
            strength = 0.99
        noise = noise_override or self.i2i_noise
        neg_prompt = negative_prompt_override or self.negative_prompt

        normalized_mask = mask_bytes
        logger.info(
            f"[Inpaint Debug] mask_bytes provided: {mask_bytes is not None}, image_bytes provided: {image_bytes is not None}"
        )
        if mask_bytes is not None and image_bytes is not None:
            try:
                base_img = Image.open(BytesIO(image_bytes))
                mask_img = Image.open(BytesIO(mask_bytes)).convert("RGBA")

                # マスク取得: アルファチャンネルまたはRGB輝度を使用
                # フロントエンドから不透明な白黒画像が送られる場合はRGBを使用
                alpha = mask_img.split()[-1]
                alpha_data = list(alpha.getdata())
                alpha_white = sum(1 for a in alpha_data if a > 128)
                alpha_ratio = alpha_white / len(alpha_data) if alpha_data else 0

                # アルファが99%以上白（=不透明）の場合、RGB輝度を使用
                if alpha_ratio > 0.99:
                    logger.info(
                        "[Inpaint Debug] Mask is fully opaque, using luminance from RGB"
                    )
                    # グレースケール変換（輝度）
                    mask_l_direct = mask_img.convert("L")
                    alpha = mask_l_direct  # 白い部分が変更領域

                # デバッグ: マスク統計
                alpha_debug = list(alpha.getdata())
                white_pixels = sum(1 for a in alpha_debug if a > 0)
                total_pixels = len(alpha_debug)
                logger.info(
                    f"[Inpaint Debug] Mask size: {mask_img.size}, White pixels: {white_pixels}/{total_pixels} ({100 * white_pixels / total_pixels:.1f}%)"
                )

                # PoC準拠: 104x152へ縮小→ベース解像度へ最近傍拡大→二値化→任意膨張
                small_size = (104, 152)
                alpha_small = alpha.resize(small_size, Image.NEAREST)
                alpha_up = alpha_small.resize(base_img.size, Image.NEAREST)

                if settings.novelai_mask_dilate_px > 0:
                    k = max(3, settings.novelai_mask_dilate_px * 2 + 1)
                    alpha_up = alpha_up.filter(ImageFilter.MaxFilter(size=k))

                binary = alpha_up.point(lambda a: 255 if a > 0 else 0)

                # デバッグ: 正規化後のマスク統計
                binary_data = list(binary.getdata())
                final_white = sum(1 for b in binary_data if b > 0)
                final_total = len(binary_data)
                logger.info(
                    f"[Inpaint Debug] Final mask white pixels: {final_white}/{final_total} ({100 * final_white / final_total:.1f}%)"
                )

                # PoCと同じくモノクロ(L)マスクPNGを送る
                mask_l = binary.convert("L")
                buf = BytesIO()
                mask_l.save(buf, format="PNG")
                normalized_mask = buf.getvalue()
                logger.info(
                    f"[Inpaint Debug] Normalized mask size: {len(normalized_mask)} bytes"
                )
            except Exception as e:
                logger.warning(f"Failed to normalize mask: {e}")

        i2i_params: Optional[I2iParams] = None
        if image_bytes is not None:
            i2i_params = I2iParams(
                image=image_bytes,
                mask=normalized_mask,
                strength=strength,
                noise=noise,
            )

        print(self._format_prompt(prompt))

        extra_negative = ", split screen, before and after, side by side, duplicate characters, mirrored panels, two people, multiple people, clone, twin, copy body, duplicate body"
        print((neg_prompt or "") + extra_negative)

        # モデル・アクション選択（PoC準拠）
        use_inpaint = normalized_mask is not None
        model_to_use = self.inpaint_model if use_inpaint else self.model
        action_to_use = self.inpaint_action if use_inpaint else "img2img"
        logger.info(
            f"[Inpaint Debug] use_inpaint={use_inpaint}, model={model_to_use}, action={action_to_use}, strength={strength}"
        )

        # Build SDK CharacterReference objects from request dicts
        sdk_char_refs: Optional[List[CharacterReference]] = None
        if character_references:
            sdk_char_refs = []
            for ref in character_references:
                image_data = ref["image"]
                # Base64 string -> bytes for SDK
                if isinstance(image_data, str):
                    image_data = base64.b64decode(image_data)
                sdk_char_refs.append(
                    CharacterReference(
                        image=image_data,
                        type=ref.get("type", "character&style"),
                        strength=ref.get("strength", 1.0),
                        fidelity=ref.get("fidelity", 1.0),
                    )
                )
            logger.info("Character references: %d items", len(sdk_char_refs))

        # Determine the seed to use
        actual_seed = seed if seed is not None else random.randint(0, 999999999)

        # Build SDK Character objects for V4 prompt splitting
        sdk_characters: Optional[List[Character]] = None
        if characters:
            sdk_characters = [
                Character(
                    prompt=c["prompt"],
                    negative_prompt=c.get("negative_prompt", ""),
                    position=tuple(c.get("position", (0.5, 0.5))),
                    enabled=c.get("enabled", True),
                )
                for c in characters
            ]
            logger.info(
                "V4 character prompt splitting: %d characters", len(sdk_characters)
            )

        # NOTE: GenerateImageParamsのmodelはSDKのリテラル制約に合わせてベースモデルを入れる
        params = GenerateImageParams(
            prompt=self._format_prompt(prompt),
            model=self.model,
            size=self.size,
            steps=self.steps,
            scale=self.scale,
            uc_preset=self.uc_preset,  # uc_presetは文字列リテラルでOK
            negative_prompt=(neg_prompt + extra_negative)
            if neg_prompt
            else extra_negative,
            quality=True,  # 自動でQUALITY_TAGSを付与
            i2i=i2i_params,
            n_samples=1,
            character_references=sdk_char_refs,
            seed=actual_seed,
            characters=sdk_characters,
        )

        try:
            # 高レベルAPIは action=generate 固定のため、明示的に img2img に切り替える
            req = await async_convert_user_params_to_api_request(params, client)
            # ここでモデルとアクションを上書きする（リクエスト直前）
            req.model = model_to_use
            req.action = action_to_use
            if normalized_mask:
                req.parameters.add_original_image = False
                req.parameters.inpaintImg2ImgStrength = strength
                req.parameters.img2img = None
                req.parameters.controlnet_strength = 1
                req.parameters.mask = base64.b64encode(normalized_mask).decode("utf-8")

            async def post_with_model(model_name: str):
                req.model = model_name
                return await client.api_client.image.generate(req)

            images = None
            actual_model_used = model_to_use
            try:
                images = await post_with_model(model_to_use)
            except NovelAIError:
                if use_inpaint and self.inpaint_fallback_model:
                    actual_model_used = self.inpaint_fallback_model
                    images = await post_with_model(self.inpaint_fallback_model)
                else:
                    raise
        except NovelAIError as e:
            logger.error("NovelAI API error: %s", e)
            raise NovelAIImageError(str(e)) from e

        if not images:
            raise NovelAIImageError("No images returned from NovelAI")

        # PIL Image -> bytes
        image_bytes_list: List[bytes] = []
        for img in images:
            buf = BytesIO()
            img.save(buf, format="PNG")
            image_bytes_list.append(buf.getvalue())

        return ImageGenerationResult(
            images=image_bytes_list,
            provider="novelai",
            model=actual_model_used,
            seed=actual_seed,
        )

    async def generate_scenery(
        self,
        prompt: str,
        size: str = "landscape",
        negative_prompt_override: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> ImageGenerationResult:
        """背景・風景画像の txt2img 生成 (US2 用)

        Args:
            prompt: 生成プロンプト
            size: 画像サイズプリセット (デフォルト: landscape = 1216x832)
            negative_prompt_override: ネガティブプロンプト
            seed: 画像生成seed値

        Returns:
            ImageGenerationResult
        """
        client = await self._get_client()

        neg_prompt = negative_prompt_override or self.negative_prompt
        extra_negative = ", 1girl, 1boy, person, people, character, human, face, body"

        actual_seed = seed if seed is not None else random.randint(0, 999999999)

        params = GenerateImageParams(
            prompt=prompt,
            model=self.model,
            size=size,
            steps=self.steps,
            scale=self.scale,
            uc_preset=self.uc_preset,
            negative_prompt=(neg_prompt + extra_negative)
            if neg_prompt
            else extra_negative,
            quality=True,
            n_samples=1,
            seed=actual_seed,
        )

        try:
            req = await async_convert_user_params_to_api_request(params, client)
            # txt2img: action="generate"
            req.action = "generate"
            images = await client.api_client.image.generate(req)
        except NovelAIError as e:
            logger.error("NovelAI scenery generation error: %s", e)
            raise NovelAIImageError(str(e)) from e

        if not images:
            raise NovelAIImageError("No scenery images returned from NovelAI")

        image_bytes_list: List[bytes] = []
        for img in images:
            buf = BytesIO()
            img.save(buf, format="PNG")
            image_bytes_list.append(buf.getvalue())

        return ImageGenerationResult(
            images=image_bytes_list,
            provider="novelai",
            model=self.model,
            seed=actual_seed,
        )


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
        # nsfw_modeごとにNovelAIクライアントをキャッシュ
        self._novelai_clients: Dict[bool, NovelAIImageClient] = {}

    def _resolve_provider(self) -> ProviderType:
        """環境変数からプロバイダーを解決"""
        provider = settings.image_provider.lower()
        if provider in ("selfhost", "openrouter", "novelai"):
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

    def _get_novelai_client(self, nsfw_mode: bool = True) -> NovelAIImageClient:
        """NovelAIクライアントを取得（遅延初期化、nsfw_modeごとにキャッシュ）

        Args:
            nsfw_mode: NSFWモード
                - True: nai-diffusion-4-5-full/inpainting を使用
                - False: nai-diffusion-4-5-curated/inpainting を使用（NSFWプロンプトを自動ブロック）
        """
        if nsfw_mode not in self._novelai_clients:
            self._novelai_clients[nsfw_mode] = NovelAIImageClient(nsfw_mode=nsfw_mode)
        return self._novelai_clients[nsfw_mode]

    async def generate_image(
        self,
        prompt: str,
        image_bytes: Optional[bytes] = None,
        *,
        reference_image_bytes: Optional[bytes] = None,
        mask_bytes: Optional[bytes] = None,
        provider_override: Optional[ProviderType] = None,
        negative_prompt: Optional[str] = None,
        i2i_strength_override: Optional[float] = None,
        i2i_noise_override: Optional[float] = None,
        nsfw_mode: bool = True,
        character_references: Optional[List[Dict[str, Any]]] = None,
        seed: Optional[int] = None,
        characters: Optional[List[Dict[str, Any]]] = None,
        **comfy_kwargs: Any,
    ) -> ImageGenerationResult:
        """画像を生成する

        Args:
            prompt: 画像生成プロンプト
            image_bytes: 編集元画像（オプション）
            reference_image_bytes: 衣装参照画像（オプション）
            provider_override: 一時的にプロバイダーを変更
            nsfw_mode: NSFWモード（NovelAI使用時のモデル選択に影響）
                - True: full モデル使用（デフォルト）
                - False: curated モデル使用（NSFWプロンプト自動ブロック）
            **comfy_kwargs: ComfyUI用の追加パラメータ

        Returns:
            ImageGenerationResult: 生成された画像
        """
        provider = provider_override or self._default_provider

        logger.info(
            f"Image generation with provider: {provider}, nsfw_mode: {nsfw_mode}"
        )

        if provider == "openrouter":
            client = self._get_openrouter_client()
            return await client.generate(
                prompt=prompt,
                image_bytes=image_bytes,
                reference_image_bytes=reference_image_bytes,
            )
        if provider == "novelai":
            client = self._get_novelai_client(nsfw_mode=nsfw_mode)
            return await client.generate(
                prompt=prompt,
                image_bytes=image_bytes,
                reference_image_bytes=reference_image_bytes,
                mask_bytes=mask_bytes,
                negative_prompt_override=negative_prompt,
                inpaint_strength_override=i2i_strength_override,
                noise_override=i2i_noise_override,
                character_references=character_references,
                seed=seed,
                characters=characters,
            )
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
        reference_image_bytes: Optional[bytes] = None,
        mask_bytes: Optional[bytes] = None,
        provider_override: Optional[ProviderType] = None,
        negative_prompt: Optional[str] = None,
        inpaint_strength: Optional[float] = None,
        inpaint_noise: Optional[float] = None,
        nsfw_mode: bool = True,
        character_references: Optional[List[Dict[str, Any]]] = None,
        seed: Optional[int] = None,
        characters: Optional[List[Dict[str, Any]]] = None,
        **comfy_kwargs: Any,
    ) -> ImageGenerationResult:
        """画像を編集する

        Args:
            image_bytes: 編集元画像
            prompt: 編集指示プロンプト
            reference_image_bytes: 衣装参照画像（オプション）
            provider_override: 一時的にプロバイダーを変更
            nsfw_mode: NSFWモード（NovelAI使用時のモデル選択に影響）
            characters: V4キャラクタープロンプト分離用（NovelAI専用）
            **comfy_kwargs: ComfyUI用の追加パラメータ

        Returns:
            ImageGenerationResult: 編集された画像
        """
        return await self.generate_image(
            prompt=prompt,
            image_bytes=image_bytes,
            reference_image_bytes=reference_image_bytes,
            mask_bytes=mask_bytes,
            provider_override=provider_override,
            negative_prompt=negative_prompt,
            i2i_strength_override=inpaint_strength,
            i2i_noise_override=inpaint_noise,
            nsfw_mode=nsfw_mode,
            character_references=character_references,
            seed=seed,
            characters=characters,
            **comfy_kwargs,
        )

    async def generate_scenery(
        self,
        prompt: str,
        size: str = "landscape",
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        nsfw_mode: bool = True,
    ) -> ImageGenerationResult:
        """背景・風景画像を生成 (NovelAI txt2img, US2 用)

        Args:
            prompt: 生成プロンプト
            size: 画像サイズプリセット (デフォルト: landscape = 1216x832)
            negative_prompt: ネガティブプロンプト
            seed: 画像生成seed値
            nsfw_mode: NSFWモード

        Returns:
            ImageGenerationResult

        Raises:
            ValueError: NovelAI以外のプロバイダーでは利用不可
        """
        if self._default_provider != "novelai":
            raise ValueError(
                "Scenery generation is only supported with NovelAI provider"
            )

        client = self._get_novelai_client(nsfw_mode=nsfw_mode)
        return await client.generate_scenery(
            prompt=prompt,
            size=size,
            negative_prompt_override=negative_prompt,
            seed=seed,
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
                        headers={
                            "Authorization": f"Bearer {settings.openrouter_api_key}"
                        },
                    )
                    results["openrouter"] = resp.status_code == 200
            except Exception:
                results["openrouter"] = False
        else:
            results["openrouter"] = False

        # NovelAI チェック（APIキー有無のみ簡易判定）
        results["novelai"] = bool(settings.novelai_api_key)

        return results


# グローバルサービスインスタンス
image_service = ImageGenerationService()
