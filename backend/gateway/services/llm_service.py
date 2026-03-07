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
    ) -> LLMResult:
        """テキストを生成する（内部でストリーミングを使用）

        NovelAI APIではstream=falseの場合token_idsが返されるため、
        内部でストリーミングを使用し、全チャンクを結合して返す。
        """
        content_parts: List[str] = []
        async for chunk in self.generate_text_stream(system_prompt, user_prompt):
            content_parts.append(chunk)

        content = "".join(content_parts)
        logger.info(f"NovelAI LLM: model={self.model}, length={len(content)}")

        return LLMResult(
            content=content,
            provider="novelai",
            model=self.model,
        )

    async def generate_text_stream(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> AsyncGenerator[str, None]:
        """テキストをストリーミング生成する

        SSEフォーマットでレスポンスを受け取り、delta.contentを順次yield。
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 4096,
            "stream": True,  # 必須: falseだとtoken_idsが返される
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
            return await self._get_novelai_client().generate_text(
                system_prompt, user_prompt
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
            async for chunk in self._get_novelai_client().generate_text_stream(
                system_prompt, user_prompt
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
                system_prompt, user_prompt
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
            )
        user_prompt = build_novelai_prompt_generation_user(
            instruction=instruction,
            previous_prompt=previous_prompt,
        )

        # NovelAI GLM-4.6を使用
        client = self._get_novelai_client()
        result = await client.generate_text(system_prompt, user_prompt)

        # 生成されたプロンプトをクリーンアップ（余分な空白・改行を除去）
        generated_prompt = result.content.strip()
        logger.info(
            f"NovelAI prompt generation: instruction='{instruction[:30]}...', "
            f"prompt_length={len(generated_prompt)}"
        )

        return generated_prompt


# グローバルインスタンス
llm_service = LLMService()
