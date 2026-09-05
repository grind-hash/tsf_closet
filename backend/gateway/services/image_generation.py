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
from typing import Any, Literal

import httpx
from novelai import AsyncNovelAI
from novelai._utils.converter import async_convert_user_params_to_api_request
from novelai.exceptions import NovelAIError
from novelai.types import Character, CharacterReference, GenerateImageParams, I2iParams
from PIL import Image, ImageFilter

from ..consts.novelai_models import get_image_model_info
from ..consts.prompt_expander import (
    PROMPT_EXPANDER_MASK_GRID_DIVISOR as MASK_GRID_DIVISOR,
)
from ..settings.config import settings
from .comfy import ComfyUIClient, ComfyUIResult
from .model_execution_gate import model_execution_gate

logger = logging.getLogger(__name__)

# プロバイダータイプ
ProviderType = Literal["selfhost", "openrouter", "novelai"]

# ComfyUI txt2img の出力サイズ。NovelAI のプリセット名と揃え、Qwen-Image が
# 扱いやすい 16 の倍数・約 1MP にする
_COMFY_SIZE_PRESETS: dict[str, tuple[int, int]] = {
    "portrait": (832, 1216),
    "landscape": (1216, 832),
    "square": (1024, 1024),
}


def _comfy_size(size: str | None) -> tuple[int, int]:
    """サイズプリセット名を ComfyUI 用の (width, height) に変換する。既定は landscape。"""
    key = (size or "landscape").strip().lower()
    return _COMFY_SIZE_PRESETS.get(key, _COMFY_SIZE_PRESETS["landscape"])


@dataclass
class UsageInfo:
    """API使用量情報"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ImageGenerationResult:
    """画像生成結果"""

    images: list[bytes]
    provider: ProviderType
    # OpenRouter使用時のAPI料金情報
    usage: UsageInfo | None = None
    cost_usd: float | None = None  # USD単位の料金
    model: str | None = None
    seed: int | None = None


class OpenRouterImageError(Exception):
    """OpenRouter画像生成エラー"""


class NovelAIImageError(Exception):
    """NovelAI画像生成エラー"""


class OpenRouterImageClient:
    """OpenRouter経由の画像生成クライアント"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ):
        self.api_key = api_key or settings.openrouter_api_key
        self.base_url = base_url or settings.openrouter_base_url
        self.model = model or settings.openrouter_image_model
        self.timeout = timeout or settings.openrouter_image_timeout

        if not self.api_key:
            raise ValueError("OpenRouter API key is required")

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://interactive-changing-room.local",
            "X-Title": "TSF Game",
        }

    async def generate(
        self,
        prompt: str,
        image_bytes: bytes | None = None,
        reference_image_bytes: bytes | None = None,
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
        messages: list[dict[str, Any]] = []

        # 編集元画像がある場合はマルチモーダル形式
        if image_bytes:
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            content: list[dict[str, Any]] = [
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

    def _extract_images(self, response: dict[str, Any]) -> list[bytes]:
        """レスポンスから画像データを抽出

        OpenRouterのGemini画像生成レスポンスは以下の形式:
        - message.images: 画像データのリスト（Gemini形式）
        - message.content: テキストまたはdata:imageのURL（他モデル）
        """
        images: list[bytes] = []

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
        self, response: dict[str, Any]
    ) -> tuple[UsageInfo | None, float | None]:
        """レスポンスから使用量・料金情報を抽出

        OpenRouterのレスポンスには以下が含まれる:
        - usage: {prompt_tokens, completion_tokens, total_tokens}
        - usage.cost または別途 x-openrouter-cost ヘッダー
        """
        usage_data = response.get("usage", {})
        usage_info: UsageInfo | None = None
        cost_usd: float | None = None

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
        api_key: str | None = None,
        model: str | None = None,
        inpaint_model: str | None = None,
        inpaint_action: str | None = None,
        inpaint_fallback_model: str | None = None,
        size: str | None = None,
        steps: int | None = None,
        scale: float | None = None,
        uc_preset: str | None = None,
        negative_prompt: str | None = None,
        i2i_strength: float | None = None,
        i2i_noise: float | None = None,
        nsfw_mode: bool = True,
    ):
        self.api_key = api_key or settings.novelai_api_key
        self.nsfw_mode = nsfw_mode
        # NSFWモードに応じてモデルを選択
        # NSFWモード: fullモデル（明示的に有効化された場合のみ）
        # 非NSFWモード: curatedモデル（NSFWプロンプトを自動ブロック）
        if nsfw_mode:
            self.model = model or settings.novelai_model
        else:
            self.model = model or settings.novelai_curated_model
        model_info = get_image_model_info(self.model, nsfw_mode=nsfw_mode)
        self.inpaint_model = inpaint_model or model_info.inpaint_model
        # SDKのGenerateImageParams.modelはv4.5までのLiteral制約があるため、
        # V5モデルでは対応するv4.5名を保持し、送信直前にreq.modelを上書きする
        self.sdk_base_model = model_info.sdk_base_model
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
        self._client: AsyncNovelAI | None = None

        if not self.api_key:
            raise ValueError("NOVELAI_API_KEY is required for NovelAI provider")

    async def _get_client(self) -> AsyncNovelAI:
        if self._client is None:
            self._client = AsyncNovelAI(api_key=self.api_key)
        return self._client

    def _format_prompt(self, prompt: str, multiple_people: bool = False) -> str:
        """NovelAI向けに軽く整形

        - 改行や余分な空白を削除
        - 長文指示でもタグ列として扱えるようにカンマ区切りを優先
        """
        compact = " ".join(prompt.strip().split())
        compact = compact.replace("、", ", ").replace("。", ", ")
        if multiple_people:
            # 複数人モード: パネル分割防止のみ付与
            suffix = (
                ", single frame, single shot, "
                "no before/after panels, no split screen, no side-by-side comparison"
            )
        else:
            # 単一キャラモード: 重複キャラ防止を強調
            suffix = (
                ", single frame, one character only, single shot, single pose, "
                "show only the transformed state, solo portrait, one subject, "
                "no before/after panels, no split screen, no side-by-side comparison, "
                "no duplicate characters, no twins, no clones, center composition, "
                "same person, same face, same hairstyle, same hair color, same skin tone"
            )
        return compact + suffix

    async def generate(
        self,
        prompt: str,
        image_bytes: bytes | None = None,
        reference_image_bytes: bytes | None = None,  # 未使用（今後の拡張用）
        mask_bytes: bytes | None = None,
        negative_prompt_override: str | None = None,
        inpaint_strength_override: float | None = None,
        noise_override: float | None = None,
        character_references: list[dict[str, Any]] | None = None,
        seed: int | None = None,
        characters: list[dict[str, Any]] | None = None,
        size_override: str | None = None,
        model_override: str | None = None,
        raw_prompt: bool = False,
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
        # 0.0 は有効な指定値なので None 判定で既定値へ落とす
        noise = noise_override if noise_override is not None else self.i2i_noise
        if raw_prompt:
            # 生プロンプト経路: 指定されたネガティブをそのまま使う（空なら空。
            # サーバー既定のネガティブへは落とさない）
            neg_prompt = negative_prompt_override or ""
        else:
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

                # PoC準拠: マスク解像度(ベースの1/8)へ縮小→ベース解像度へ最近傍拡大
                # →二値化→任意膨張。portrait(832x1216)では従来と同じ104x152になる。
                # 固定値にすると landscape / square でマスクの縦横比が崩れる
                small_size = (
                    max(1, base_img.width // MASK_GRID_DIVISOR),
                    max(1, base_img.height // MASK_GRID_DIVISOR),
                )
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

        i2i_params: I2iParams | None = None
        if image_bytes is not None:
            i2i_params = I2iParams(
                image=image_bytes,
                mask=normalized_mask,
                strength=strength,
                noise=noise,
            )

        multiple_people = bool(characters and len(characters) > 1)

        if raw_prompt:
            # 生プロンプト経路: 分割防止などの自動ネガティブを足さない
            extra_negative = ""
        elif multiple_people:
            extra_negative = ", split screen, before and after, mirrored panels"
        else:
            extra_negative = ", split screen, before and after, side by side, duplicate characters, mirrored panels, two people, multiple people, clone, twin, copy body, duplicate body"

        # モデル・アクション選択（PoC準拠）
        # インペイントモデルも要求モデル（override優先）に追従させる
        wire_model = model_override or self.model
        model_info = get_image_model_info(wire_model, nsfw_mode=self.nsfw_mode)
        use_inpaint = normalized_mask is not None
        model_to_use = model_info.inpaint_model if use_inpaint else wire_model
        if use_inpaint:
            action_to_use = self.inpaint_action
        elif i2i_params is not None:
            action_to_use = "img2img"
        else:
            action_to_use = "generate"
        logger.info(
            f"[Inpaint Debug] use_inpaint={use_inpaint}, model={model_to_use}, action={action_to_use}, strength={strength}"
        )

        # V5系モデルは精密参照（character reference）非対応のため防御的に破棄する
        if character_references and model_info.is_v5:
            logger.warning(
                "Character references are not supported by V5 models; dropping %d references",
                len(character_references),
            )
            character_references = None

        # Build SDK CharacterReference objects from request dicts
        sdk_char_refs: list[CharacterReference] | None = None
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
        sdk_characters: list[Character] | None = None
        if characters:
            logger.info("characters: %s", characters)
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
        # （V5モデル名はLiteral非対応のため、送信直前のreq.model上書きで差し替える）
        if raw_prompt:
            # 生プロンプト経路: 空白の圧縮のみ行い、句読点置換や接尾辞を付けない
            # （日本語の自然文プロンプトを壊さないため）
            formatted_prompt = " ".join(prompt.strip().split())
            formatted_negative = neg_prompt or None
        else:
            formatted_prompt = self._format_prompt(
                prompt, multiple_people=multiple_people
            )
            formatted_negative = (
                (neg_prompt + extra_negative) if neg_prompt else extra_negative
            )
        params = GenerateImageParams(
            prompt=formatted_prompt,
            model=model_info.sdk_base_model,
            size=size_override or self.size,
            steps=self.steps,
            scale=self.scale,
            uc_preset=self.uc_preset,  # uc_presetは文字列リテラルでOK
            negative_prompt=formatted_negative,
            quality=True,  # 自動でQUALITY_TAGSを付与
            i2i=i2i_params,
            n_samples=1,
            character_references=sdk_char_refs,
            seed=actual_seed,
            characters=sdk_characters,
        )

        try:
            # 入力画像とマスクの有無に応じたactionをリクエスト直前に確定する
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
        image_bytes_list: list[bytes] = []
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
        negative_prompt_override: str | None = None,
        seed: int | None = None,
        include_people: bool = False,
        model_override: str | None = None,
    ) -> ImageGenerationResult:
        """Background / scenery txt2img generation (US2)

        Args:
            prompt: Generation prompt
            size: Image size preset (default: landscape = 1216x832)
            negative_prompt_override: Negative prompt override
            seed: Image generation seed
            include_people: If True, allow anonymous bystanders (block protagonist only)
            model_override: Model name override (V5 names allowed)

        Returns:
            ImageGenerationResult
        """
        client = await self._get_client()
        wire_model = model_override or self.model
        model_info = get_image_model_info(wire_model, nsfw_mode=self.nsfw_mode)

        neg_prompt = negative_prompt_override or self.negative_prompt
        if include_people:
            # Allow exactly 2-3 generic bystanders; block protagonist and large groups
            extra_negative = (
                ", solo, solo focus, close-up, portrait, pov"
                ", crowd, many people, large group, 4girls, 5girls"
                ", 4boys, 5boys, 6+others"
            )
        else:
            # Block all people
            extra_negative = (
                ", 1girl, 1boy, person, people, character, human, face, body"
            )

        actual_seed = seed if seed is not None else random.randint(0, 999999999)

        # NOTE: GenerateImageParamsのmodelはSDKのリテラル制約に合わせてベースモデルを入れる
        params = GenerateImageParams(
            prompt=prompt,
            model=model_info.sdk_base_model,
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
            # 実際に送信するモデル名（V5名を含む）をリクエスト直前に確定する
            req.model = wire_model
            images = await client.api_client.image.generate(req)
        except NovelAIError as e:
            logger.error("NovelAI scenery generation error: %s", e)
            raise NovelAIImageError(str(e)) from e

        if not images:
            raise NovelAIImageError("No scenery images returned from NovelAI")

        image_bytes_list: list[bytes] = []
        for img in images:
            buf = BytesIO()
            img.save(buf, format="PNG")
            image_bytes_list.append(buf.getvalue())

        return ImageGenerationResult(
            images=image_bytes_list,
            provider="novelai",
            model=wire_model,
            seed=actual_seed,
        )


class ImageGenerationService:
    """プロバイダー切り替え付き画像生成サービス"""

    def __init__(self, provider: ProviderType | None = None):
        """
        Args:
            provider: 使用するプロバイダー（未指定時は環境変数から取得）
        """
        self._default_provider: ProviderType = provider or self._resolve_provider()
        self._comfy_client: ComfyUIClient | None = None
        self._openrouter_client: OpenRouterImageClient | None = None
        # (nsfw_mode, モデル名)ごとにNovelAIクライアントをキャッシュ
        self._novelai_clients: dict[tuple[bool, str], NovelAIImageClient] = {}

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

    def _get_novelai_client(
        self, nsfw_mode: bool = True, model: str | None = None
    ) -> NovelAIImageClient:
        """NovelAIクライアントを取得（遅延初期化、(nsfw_mode, モデル名)ごとにキャッシュ）

        Args:
            nsfw_mode: NSFWモード
                - True: full 系モデルを使用
                - False: curated 系モデルを使用（NSFWプロンプトを自動ブロック）
            model: モデル名の明示指定（省略時は nsfw_mode に応じた env 既定）
        """
        resolved_model = model or (
            settings.novelai_model if nsfw_mode else settings.novelai_curated_model
        )
        cache_key = (nsfw_mode, resolved_model)
        if cache_key not in self._novelai_clients:
            self._novelai_clients[cache_key] = NovelAIImageClient(
                nsfw_mode=nsfw_mode, model=resolved_model
            )
        return self._novelai_clients[cache_key]

    async def generate_image(
        self,
        prompt: str,
        image_bytes: bytes | None = None,
        *,
        reference_image_bytes: bytes | None = None,
        mask_bytes: bytes | None = None,
        provider_override: ProviderType | None = None,
        negative_prompt: str | None = None,
        i2i_strength_override: float | None = None,
        i2i_noise_override: float | None = None,
        nsfw_mode: bool = True,
        character_references: list[dict[str, Any]] | None = None,
        seed: int | None = None,
        characters: list[dict[str, Any]] | None = None,
        size_override: str | None = None,
        novelai_model_override: str | None = None,
        raw_prompt: bool = False,
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
            async with model_execution_gate.hold(
                "image", provider, settings.openrouter_image_model
            ):
                return await client.generate(
                    prompt=prompt,
                    image_bytes=image_bytes,
                    reference_image_bytes=reference_image_bytes,
                )
        if provider == "novelai":
            effective_nsfw_mode = nsfw_mode
            if novelai_model_override:
                # モデル名の系統（full/curated）から nsfw_mode を再導出する
                override_info = get_image_model_info(
                    novelai_model_override, nsfw_mode=nsfw_mode
                )
                effective_nsfw_mode = override_info.family == "full"
            client = self._get_novelai_client(
                nsfw_mode=effective_nsfw_mode, model=novelai_model_override
            )
            wire_model = novelai_model_override or client.model
            effective_model = (
                get_image_model_info(
                    wire_model, nsfw_mode=effective_nsfw_mode
                ).inpaint_model
                if mask_bytes
                else wire_model
            )
            async with model_execution_gate.hold("image", provider, effective_model):
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
                    size_override=size_override,
                    model_override=novelai_model_override,
                    raw_prompt=raw_prompt,
                )
        else:
            # セルフホスト (ComfyUI)
            client = self._get_comfy_client()

            if image_bytes is None:
                # 編集元画像が無い生成(背景など)は txt2img ワークフローで賄う。
                # 編集用の workflow_path が渡されていれば、その命名規則から
                # 対応する txt2img テンプレートを引く
                edit_workflow_path = comfy_kwargs.pop("workflow_path", None)
                txt2img_workflow_path = settings.get_txt2img_workflow_path(
                    edit_workflow_path
                )
                width, height = _comfy_size(size_override)
                async with model_execution_gate.hold("image", provider, "comfyui"):
                    txt2img_result: ComfyUIResult = await client.text_to_image(
                        prompt=prompt,
                        negative_prompt=negative_prompt or "",
                        width=width,
                        height=height,
                        seed=seed,
                        workflow_path=txt2img_workflow_path,
                        **comfy_kwargs,
                    )
                return ImageGenerationResult(
                    images=txt2img_result.images, provider="selfhost"
                )

            async with model_execution_gate.hold("image", provider, "comfyui"):
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
        reference_image_bytes: bytes | None = None,
        mask_bytes: bytes | None = None,
        provider_override: ProviderType | None = None,
        negative_prompt: str | None = None,
        inpaint_strength: float | None = None,
        inpaint_noise: float | None = None,
        nsfw_mode: bool = True,
        character_references: list[dict[str, Any]] | None = None,
        seed: int | None = None,
        characters: list[dict[str, Any]] | None = None,
        size_override: str | None = None,
        novelai_model_override: str | None = None,
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
            size_override=size_override,
            novelai_model_override=novelai_model_override,
            **comfy_kwargs,
        )

    async def generate_scenery(
        self,
        prompt: str,
        size: str = "landscape",
        negative_prompt: str | None = None,
        seed: int | None = None,
        nsfw_mode: bool = True,
        include_people: bool = False,
        provider_override: ProviderType | None = None,
        novelai_model_override: str | None = None,
    ) -> ImageGenerationResult:
        """Generate background / scenery image (NovelAI txt2img, US2)

        Args:
            prompt: Generation prompt
            size: Image size preset (default: landscape = 1216x832)
            negative_prompt: Negative prompt
            seed: Image generation seed
            nsfw_mode: NSFW mode
            include_people: If True, allow anonymous bystanders
            provider_override: 一時的にプロバイダーを変更（例: Adventureモードの常時NovelAI利用）

        Returns:
            ImageGenerationResult

        Raises:
            ValueError: Not supported on non-NovelAI providers
        """
        effective_provider = provider_override or self._default_provider
        if effective_provider != "novelai":
            raise ValueError(
                "Scenery generation is only supported with NovelAI provider"
            )

        client = self._get_novelai_client(
            nsfw_mode=nsfw_mode, model=novelai_model_override
        )
        wire_model = novelai_model_override or client.model
        async with model_execution_gate.hold("image", "novelai", wire_model):
            return await client.generate_scenery(
                prompt=prompt,
                size=size,
                negative_prompt_override=negative_prompt,
                seed=seed,
                include_people=include_people,
                model_override=novelai_model_override,
            )

    async def health_check(self) -> dict[str, bool]:
        """各プロバイダーの接続状態を確認

        Returns:
            各プロバイダーの接続可否
        """
        results: dict[str, bool] = {}

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
