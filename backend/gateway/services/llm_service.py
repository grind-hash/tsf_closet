"""
LLMサービス

画像説明（Vision）と心境生成（LLM）のプロバイダー切り替えを管理。
- selfhost: LiteLLM Proxy経由でローカルモデル使用
- openrouter: OpenRouter API経由でクラウドモデル使用
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import AsyncGenerator, Dict, List, Any, Optional

import httpx

from ..consts.character_limits import APPEARANCE_NATURAL_SOFT_LIMIT
from ..consts.language import LanguageCode, normalize_language
from ..settings.config import settings

logger = logging.getLogger(__name__)


class LLMServiceError(RuntimeError):
    """LLMサービスエラー"""


@dataclass
class UsageInfo:
    """使用量情報"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResult:
    """LLM呼び出し結果"""

    content: str
    provider: str  # "selfhost" or "openrouter"
    usage: Optional[UsageInfo] = None
    cost_usd: Optional[float] = None
    model: Optional[str] = None


# =============================================================================
# OpenRouter LLMクライアント
# =============================================================================


class OpenRouterLLMClient:
    """OpenRouter LLMクライアント

    OpenRouter APIを使用して画像説明・心境生成を行う。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        vision_model: Optional[str] = None,
        llm_model: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.api_key = api_key or settings.openrouter_api_key
        self.base_url = (base_url or settings.openrouter_base_url).rstrip("/")
        self.vision_model = vision_model or settings.openrouter_vision_model
        self.llm_model = llm_model or settings.openrouter_llm_model
        self.timeout = timeout or settings.openrouter_llm_timeout

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8000",
            "X-Title": "TSF Game",
        }

    async def describe_image(self, image_bytes: bytes, prompt: str) -> LLMResult:
        """画像を説明する（Vision API）"""
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        payload = {
            "model": self.vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                        },
                    ],
                }
            ],
            "max_tokens": 4096,
            "usage": {"include": True},
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._get_headers(),
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

        content = result["choices"][0]["message"]["content"]
        usage, cost = self._extract_usage(result)

        logger.info(
            f"OpenRouter vision: model={self.vision_model}, cost=${cost or 0:.6f}"
        )

        return LLMResult(
            content=content,
            provider="openrouter",
            usage=usage,
            cost_usd=cost,
            model=self.vision_model,
        )

    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> LLMResult:
        """テキストを生成する"""
        payload = {
            "model": self.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 4096,
            "usage": {"include": True},
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._get_headers(),
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

        content = result["choices"][0]["message"]["content"]
        usage, cost = self._extract_usage(result)

        logger.info(f"OpenRouter LLM: model={self.llm_model}, cost=${cost or 0:.6f}")

        return LLMResult(
            content=content,
            provider="openrouter",
            usage=usage,
            cost_usd=cost,
            model=self.llm_model,
        )

    async def generate_text_stream(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> AsyncGenerator[str, None]:
        """テキストをストリーミング生成する"""
        payload = {
            "model": self.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 4096,
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._get_headers(),
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue

    def _extract_usage(
        self, response: Dict[str, Any]
    ) -> tuple[Optional[UsageInfo], Optional[float]]:
        """使用量・料金情報を抽出"""
        usage_data = response.get("usage", {})
        if not usage_data:
            return None, None

        usage = UsageInfo(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )
        cost = usage_data.get("cost")

        return usage, cost


# =============================================================================
# NovelAI LLMクライアント
# =============================================================================


# モデルごとのデフォルトサンプリングパラメータ
_NOVELAI_MODEL_PARAMS: Dict[str, Dict[str, Any]] = {
    "xialong-v1": {
        "top_k": 250,
        "top_p": 0.95,
        "temperature": 0.85,
        # 行頭の "***" のみ停止扱いにする (生成1トークン目が "***" になり空応答化する事象の回避)
        "stop": ["\n***", "\n["],
    },
    "glm-4-6": {"top_k": 40, "top_p": 0.95, "temperature": 1.0},
}


# NovelAI画像プロンプト用タグ置換マップ
# LLMが出力しがちな表現をNovelAI画像生成で有効なタグに変換する
_NOVELAI_PROMPT_TAG_REPLACEMENTS: Dict[str, str] = {
    "shorts": "panties",
}


class NovelAILLMClient:
    """NovelAI LLMクライアント (OpenAI互換エンドポイント)

    NovelAI Text APIを使用して心境生成を行う。
    注意: stream=true が必須 (falseだとtoken_idsが返される)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.api_key = api_key or settings.novelai_api_key
        self.base_url = (base_url or settings.novelai_text_base_url).rstrip("/")
        self.model = model or settings.novelai_text_model
        self.timeout = timeout or settings.novelai_text_timeout

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        model_override: Optional[str] = None,
        max_tokens: int = 4096,
    ) -> LLMResult:
        """テキストを生成する（内部でストリーミングを使用）

        NovelAI APIではstream=falseの場合token_idsが返されるため、
        内部でストリーミングを使用し、全チャンクを結合して返す。
        """
        effective_model = model_override or self.model
        content_parts: List[str] = []
        async for chunk in self.generate_text_stream(
            system_prompt,
            user_prompt,
            model_override=model_override,
            max_tokens=max_tokens,
        ):
            content_parts.append(chunk)

        content = "".join(content_parts)
        logger.info(f"NovelAI LLM: model={effective_model}, length={len(content)}")

        return LLMResult(
            content=content,
            provider="novelai",
            model=effective_model,
        )

    async def generate_text_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        model_override: Optional[str] = None,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """テキストをストリーミング生成する

        SSEフォーマットでレスポンスを受け取り、delta.contentを順次yield。
        """
        effective_model = model_override or self.model
        sampling_params = _NOVELAI_MODEL_PARAMS.get(effective_model, {})
        payload = {
            "model": effective_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "stream": True,  # 必須: falseだとtoken_idsが返される
            **sampling_params,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self._get_headers(),
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                choices = data.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content")
                                    if content:
                                        yield content
                                    # finish_reason=stopで終了
                                    if choices[0].get("finish_reason") == "stop":
                                        break
                            except json.JSONDecodeError:
                                logger.warning(f"NovelAI SSE parse error: {data_str}")
                                continue
        except httpx.TimeoutException as e:
            logger.error(f"NovelAI LLM timeout: {e}")
            raise LLMServiceError(f"NovelAI API timeout: {e}") from e
        except httpx.HTTPStatusError as e:
            logger.error(f"NovelAI LLM HTTP error: {e.response.status_code}")
            raise LLMServiceError(f"NovelAI API error: {e.response.status_code}") from e


# =============================================================================
# LLMサービス（プロバイダー切り替え）
# =============================================================================


class LLMService:
    """LLMサービス

    画像説明・心境生成のプロバイダーを設定に基づいて切り替え。
    """

    def __init__(self) -> None:
        self._openrouter_client: Optional[OpenRouterLLMClient] = None
        self._novelai_client: Optional[NovelAILLMClient] = None
        # LiteLLMクライアントは遅延インポート
        self._litellm_client = None

    def _get_openrouter_client(self) -> OpenRouterLLMClient:
        if self._openrouter_client is None:
            self._openrouter_client = OpenRouterLLMClient()
        return self._openrouter_client

    def _get_novelai_client(self) -> NovelAILLMClient:
        if self._novelai_client is None:
            self._novelai_client = NovelAILLMClient()
        return self._novelai_client

    def _get_litellm_client(self):
        if self._litellm_client is None:
            from .litellm_client import litellm_client

            self._litellm_client = litellm_client
        return self._litellm_client

    async def describe_image(
        self,
        image_bytes: bytes,
        prompt: str,
        provider_override: Optional[str] = None,
    ) -> LLMResult:
        """画像を説明する

        Args:
            image_bytes: 画像バイナリ
            prompt: 説明を求めるプロンプト
            provider_override: プロバイダー指定（省略時は設定値）

        Returns:
            LLMResult
        """
        provider = provider_override or settings.image_description_provider

        if provider == "openrouter":
            return await self._get_openrouter_client().describe_image(
                image_bytes, prompt
            )
        else:
            # セルフホスト (LiteLLM Proxy)
            litellm = self._get_litellm_client()
            content = await litellm.describe_image(image_bytes, prompt)
            return LLMResult(
                content=content,
                provider="selfhost",
                model=settings.litellm_llava_model,
            )

    async def generate_feeling(
        self,
        system_prompt: str,
        user_prompt: str,
        provider_override: Optional[str] = None,
        novelai_model_override: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResult:
        """心境テキストを生成する

        Args:
            system_prompt: システムプロンプト
            user_prompt: ユーザープロンプト
            provider_override: プロバイダー指定（省略時は設定値）

        Returns:
            LLMResult
        """
        provider = provider_override or settings.feeling_provider

        if provider == "openrouter":
            return await self._get_openrouter_client().generate_text(
                system_prompt, user_prompt
            )
        elif provider == "novelai":
            kwargs: dict[str, Any] = {
                "model_override": novelai_model_override,
            }
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            return await self._get_novelai_client().generate_text(
                system_prompt, user_prompt, **kwargs
            )
        else:
            # セルフホスト (LiteLLM Proxy)
            litellm = self._get_litellm_client()
            content = await litellm.generate_feeling(system_prompt, user_prompt)
            return LLMResult(
                content=content,
                provider="selfhost",
                model=settings.litellm_feeling_model,
            )

    async def generate_feeling_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        provider_override: Optional[str] = None,
        novelai_model_override: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """心境テキストをストリーミング生成する

        Args:
            system_prompt: システムプロンプト
            user_prompt: ユーザープロンプト
            provider_override: プロバイダー指定（省略時は設定値）

        Yields:
            テキストチャンク
        """
        provider = provider_override or settings.feeling_provider

        if provider == "openrouter":
            async for chunk in self._get_openrouter_client().generate_text_stream(
                system_prompt, user_prompt
            ):
                yield chunk
        elif provider == "novelai":
            nai_kwargs: dict[str, Any] = {
                "model_override": novelai_model_override,
            }
            if max_tokens is not None:
                nai_kwargs["max_tokens"] = max_tokens
            async for chunk in self._get_novelai_client().generate_text_stream(
                system_prompt, user_prompt, **nai_kwargs
            ):
                yield chunk
        else:
            # セルフホスト (LiteLLM Proxy)
            litellm = self._get_litellm_client()
            async for chunk in litellm.generate_feeling_stream(
                system_prompt, user_prompt
            ):
                yield chunk

    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        provider_override: Optional[str] = None,
        novelai_model_override: Optional[str] = None,
    ) -> LLMResult:
        """テキストを生成する (汎用)

        Args:
            system_prompt: システムプロンプト
            user_prompt: ユーザープロンプト
            provider_override: プロバイダー指定（省略時は設定値）

        Returns:
            LLMResult
        """
        provider = provider_override or settings.feeling_provider

        if provider == "openrouter":
            return await self._get_openrouter_client().generate_text(
                system_prompt, user_prompt
            )
        elif provider == "novelai":
            return await self._get_novelai_client().generate_text(
                system_prompt, user_prompt, model_override=novelai_model_override
            )
        else:
            # セルフホスト (LiteLLM Proxy)
            client = self._get_litellm_client()
            content = await client.generate_text(system_prompt, user_prompt)
            return LLMResult(
                content=content,
                provider="selfhost",
                model=settings.litellm_llm_model,
            )

    async def generate_image_edit_prompt(
        self,
        instruction: str,
        current_description: str,
        preserve_elements: list[str] | None = None,
        change_scope: str = "full",
        custom_preserve_text: str = "",
        provider_override: Optional[str] = None,
        nsfw_mode: bool = False,
        extra_system_suffix: str = "",
    ) -> LLMResult:
        """画像編集プロンプトを生成する

        Args:
            instruction: ユーザーの着せ替え指示
            current_description: 現在の画像の説明
            preserve_elements: 保持する要素のリスト
            change_scope: 変更対象 (full, upper, lower, accessories, shoes)
            custom_preserve_text: カスタム保持指示（自由記述）
            provider_override: プロバイダー指定（省略時は設定値）
            nsfw_mode: NSFWモードかどうか
            extra_system_suffix: システムプロンプト末尾に付与する追加指示（メモリ優先指示等）

        Returns:
            LLMResult
        """
        from .prompts import (
            build_image_edit_prompt,
            get_image_edit_system_prompt,
        )

        provider = provider_override or settings.feeling_provider
        system_prompt = get_image_edit_system_prompt(
            image_provider=provider, nsfw_mode=nsfw_mode
        )
        if extra_system_suffix:
            system_prompt = system_prompt + extra_system_suffix
        user_prompt = build_image_edit_prompt(
            instruction=instruction,
            current_description=current_description,
            preserve_elements=preserve_elements,
            change_scope=change_scope,
            custom_preserve_text=custom_preserve_text,
        )

        if provider == "openrouter":
            return await self._get_openrouter_client().generate_text(
                system_prompt, user_prompt
            )
        else:
            # セルフホスト (LiteLLM Proxy)
            litellm = self._get_litellm_client()
            content = await litellm.generate_image_edit_prompt(
                instruction=instruction,
                current_description=current_description,
                preserve_elements=preserve_elements,
                change_scope=change_scope,
                custom_preserve_text=custom_preserve_text,
                provider=provider,
                extra_system_suffix=extra_system_suffix,
            )
            return LLMResult(
                content=content,
                provider="selfhost",
                model=settings.litellm_llm_model,
            )

    async def generate_novelai_image_prompt(
        self,
        instruction: str,
        previous_prompt: str | None = None,
        character_base_tags: str | None = None,
        nsfw_mode: bool = False,
        language: str = "ja",
        system_prompt_override: str | None = None,
        gender: str = "man",
        clothing_color_consistency: bool = False,
        enable_multiple_people: bool = False,
        novelai_model_override: str | None = None,
        session_characters_section: str | None = None,
        extra_system_suffix: str = "",
    ) -> str:
        """NovelAI画像生成プロンプトを生成する (T006)

        ユーザーの指示をNovelAI用タグプロンプトに変換する。
        NovelAI GLM-4.6を使用。

        Args:
            instruction: ユーザーの指示
            previous_prompt: 前回生成したプロンプト（継続の場合）
            character_base_tags: キャラクターベースタグ（初回の場合）
            nsfw_mode: NSFWモードかどうか
            language: 指示言語
            system_prompt_override: カスタムシステムプロンプト（行動モード等）。
                指定された場合、デフォルトのシステムプロンプトを置き換える。
            gender: キャラクターの元の性別（"man" または "woman"）
            extra_system_suffix: システムプロンプト末尾に付与する追加指示（メモリ優先指示等）

        Returns:
            NovelAI用タグプロンプト（カンマ区切り）
        """
        from .prompts import (
            build_novelai_prompt_generation_user,
            get_novelai_prompt_generation_system,
        )

        if system_prompt_override:
            system_prompt = system_prompt_override
        else:
            system_prompt = get_novelai_prompt_generation_system(
                nsfw_mode=nsfw_mode,
                instruction_language=language,
                clothing_color_consistency=clothing_color_consistency,
                enable_multiple_people=enable_multiple_people,
            )
        if extra_system_suffix:
            system_prompt = system_prompt + extra_system_suffix
        user_prompt = build_novelai_prompt_generation_user(
            instruction=instruction,
            previous_prompt=previous_prompt,
            enable_multiple_people=enable_multiple_people,
            session_characters_section=session_characters_section,
        )

        # NovelAI GLM-4.6を使用
        client = self._get_novelai_client()
        result = await client.generate_text(
            system_prompt, user_prompt, model_override=novelai_model_override
        )

        # 生成されたプロンプトをクリーンアップ（余分な空白・改行を除去）
        generated_prompt = result.content.strip()

        # タグ置換: LLMが出す不適切な表現をNovelAI有効タグに変換
        for old_tag, new_tag in _NOVELAI_PROMPT_TAG_REPLACEMENTS.items():
            generated_prompt = generated_prompt.replace(old_tag, new_tag)

        logger.info(
            f"NovelAI prompt generation: instruction='{instruction[:30]}...', "
            f"prompt_length={len(generated_prompt)}"
        )

        return generated_prompt

    async def generate_character_tags_batch(
        self,
        items: List[Dict[str, str]],
        *,
        provider_override: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """Batch generate NovelAI-compatible tag strings for N characters in one call.

        Args:
            items: list of ``{id, name, natural}`` dicts (1..4 entries).
            provider_override: optional provider override.

        Returns:
            List of ``{id, tags}`` dicts. The ``id`` order matches input. If
            the LLM returns malformed JSON, one retry is attempted; on second
            failure :class:`LLMServiceError` is raised (mapped to HTTP 502
            by the router).

        See research.md R-001.
        """
        if not items:
            return []
        if len(items) > 4:
            raise LLMServiceError("too_many_items")

        system_prompt = (
            "You convert natural-language character descriptions into "
            "NovelAI-compatible Danbooru-style English tag strings. "
            "Always respond with a single JSON object exactly matching "
            'the schema: {"results": [{"id": <input id>, "tags": '
            '"tag1, tag2, ..."}]} . The number of result entries MUST '
            "equal the number of input items, and each id MUST be echoed "
            "verbatim. Use lowercase, comma-separated tags only. Never "
            "include any explanation or extra keys."
        )
        # Compose user prompt as JSON for stable parsing.
        user_prompt = json.dumps({"items": items}, ensure_ascii=False)

        async def _call_once() -> str:
            result = await self.generate_feeling(
                system_prompt,
                user_prompt,
                provider_override=provider_override,
            )
            return result.content

        last_error: Optional[Exception] = None
        for attempt in range(2):
            try:
                raw = await _call_once()
                parsed = _parse_tag_batch_response(raw, items)
                return parsed
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "generate_character_tags_batch parse failure (attempt %d): %s",
                    attempt + 1,
                    exc,
                )
                continue
            except Exception as exc:  # network etc.
                last_error = exc
                logger.warning(
                    "generate_character_tags_batch transport failure (attempt %d): %s",
                    attempt + 1,
                    exc,
                )
                continue

        raise LLMServiceError(f"batch_tag_generation_failed: {last_error!s}")

    async def infer_appearance_updates(
        self,
        characters: List[Dict[str, Any]],
        action_text: str,
        *,
        provider_override: Optional[str] = None,
        language: str = "ja",
    ) -> List[Dict[str, Any]]:
        """Infer appearance diffs for N session characters after an action.

        Args:
            characters: list of dicts ``{id, name, appearance_natural,
                appearance_tags, appearance_lock?, exclude_from_effects?}``
                representing current state. lock/exclude が True のキャラは
                changed=false を強制する。
            action_text: latest player instruction text.
            provider_override: optional provider override.
            language: ``ja`` or ``en``. ``appearance_natural`` の出力言語を制約する。

        Returns:
            List of update dicts conforming to research R-002 schema:
            ``{character_id, changed, appearance_natural?, appearance_tags?}``.
            On any parse/transport failure returns an all-no-op list (per FR-014).
        """
        if not characters:
            return []
        lang: LanguageCode = normalize_language(language)
        if lang == "en":
            language_rule = (
                "Write appearance_natural in natural English only. "
                "Never mix Japanese characters."
            )
        else:
            language_rule = (
                "appearance_natural は必ず自然な日本語のみで記述し、"
                "英単語・英文を混在させないこと。"
            )
        soft_limit = APPEARANCE_NATURAL_SOFT_LIMIT
        system_prompt = (
            "You analyze a player action and decide how each on-screen "
            "character's appearance changed. Return strict JSON: "
            '{"updates": [{"character_id": "<id>", "changed": <bool>, '
            '"appearance_natural": "<full updated natural-language>", '
            '"appearance_tags": "<full updated tag list>"}, ...]}.\n'
            "Rules:\n"
            "- If a character is unaffected, set changed=false and omit the "
            "appearance_* fields.\n"
            "- Always include exactly one entry per input character. "
            "Never explain. Never invent ids.\n"
            "- If an input character has appearance_lock=true or "
            "exclude_from_effects=true, you MUST return changed=false for "
            "that character and omit appearance_* fields (their appearance "
            "must not change).\n"
            "- appearance_natural must be the CURRENT total description "
            "(a full replacement, NOT a diff appended to the previous "
            f"value). Keep it concise: 1-2 sentences, at most {soft_limit} "
            "characters. Do not enumerate every prior detail.\n"
            "- appearance_tags must be a complete comma-separated tag list "
            "for the CURRENT state, not a diff. Keep it tight; drop "
            "redundant tags.\n"
            f"- {language_rule}"
        )
        payload = {
            "language": lang,
            "characters": characters,
            "action": action_text,
        }
        user_prompt = json.dumps(payload, ensure_ascii=False)
        try:
            result = await self.generate_feeling(
                system_prompt,
                user_prompt,
                provider_override=provider_override,
            )
            parsed = _parse_appearance_update_response(result.content, characters)
            return parsed
        except Exception as exc:  # noqa: BLE001 - best-effort fallback
            logger.warning("infer_appearance_updates failure: %s", exc)
            return [{"character_id": c["id"], "changed": False} for c in characters]


def _parse_tag_batch_response(
    raw: str, expected_items: List[Dict[str, str]]
) -> List[Dict[str, str]]:
    """Parse LLM JSON output for batch tag generation.

    Raises ``ValueError`` on schema mismatch; ``json.JSONDecodeError`` on
    non-JSON content. The caller catches both and may retry once.
    """
    cleaned = _strip_code_fence(raw)
    data = json.loads(cleaned)
    if not isinstance(data, dict) or "results" not in data:
        raise ValueError("missing results key")
    results = data["results"]
    if not isinstance(results, list) or len(results) != len(expected_items):
        raise ValueError("results length mismatch")
    expected_ids = {item["id"] for item in expected_items}
    out: List[Dict[str, str]] = []
    for entry in results:
        if not isinstance(entry, dict):
            raise ValueError("non-dict result entry")
        eid = entry.get("id")
        tags = entry.get("tags", "")
        if eid not in expected_ids:
            raise ValueError(f"unknown id {eid}")
        if not isinstance(tags, str):
            raise ValueError("tags not string")
        out.append({"id": str(eid), "tags": tags.strip()})
    return out


def _parse_appearance_update_response(
    raw: str, expected_characters: List[Dict[str, str]]
) -> List[Dict[str, Any]]:
    """Parse LLM JSON output for appearance updates (R-002)."""
    cleaned = _strip_code_fence(raw)
    data = json.loads(cleaned)
    if not isinstance(data, dict) or "updates" not in data:
        raise ValueError("missing updates key")
    updates = data["updates"]
    if not isinstance(updates, list):
        raise ValueError("updates not list")
    valid_ids = {c["id"] for c in expected_characters}
    out: List[Dict[str, Any]] = []
    for entry in updates:
        if not isinstance(entry, dict):
            continue
        cid = entry.get("character_id")
        if cid not in valid_ids:
            continue
        result: Dict[str, Any] = {
            "character_id": cid,
            "changed": bool(entry.get("changed", False)),
        }
        if isinstance(entry.get("appearance_natural"), str):
            result["appearance_natural"] = entry["appearance_natural"]
        if isinstance(entry.get("appearance_tags"), str):
            result["appearance_tags"] = entry["appearance_tags"]
        out.append(result)
    return out


def _strip_code_fence(raw: str) -> str:
    """Strip ```json ... ``` fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        # Remove opening fence (with optional language tag).
        nl = text.find("\n")
        if nl != -1:
            text = text[nl + 1 :]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


# グローバルインスタンス
llm_service = LLMService()
