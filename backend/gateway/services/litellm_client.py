"""
LiteLLM Proxyクライアント

LiteLLM Proxy経由でLLaVA (画像説明) とLLM (心境生成) を呼び出すクライアント。
OpenAI互換APIを使用。
"""

from __future__ import annotations

import base64
import json
import logging
from typing import AsyncGenerator, Optional

import httpx

from ..settings.config import settings

logger = logging.getLogger(__name__)


class LiteLLMClientError(RuntimeError):
    """LiteLLMクライアントエラー"""


class LiteLLMClient:
    """LiteLLM Proxyクライアント

    LiteLLM Proxy経由でマルチモーダルLLM (LLaVA) とテキストLLM を呼び出す。
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        llava_model: Optional[str] = None,
        llm_model: Optional[str] = None,
        feeling_model: Optional[str] = None,
        timeout: Optional[float] = None,
        api_key: Optional[str] = None,
    ) -> None:
        """初期化

        Args:
            base_url: LiteLLM ProxyのベースURL
            llava_model: LLaVAモデル名
            llm_model: テキストLLMモデル名
            feeling_model: 心理状態生成用モデル名 (gpt-oss:20b対応)
            timeout: リクエストタイムアウト (秒)
            api_key: APIキー (必要な場合)
        """
        self.base_url = (base_url or settings.litellm_base_url).rstrip("/")
        self.llava_model = llava_model or settings.litellm_llava_model
        self.llm_model = llm_model or settings.litellm_llm_model
        self.feeling_model = feeling_model or settings.litellm_feeling_model
        self.timeout = timeout or settings.litellm_request_timeout
        self.api_key = api_key or settings.litellm_api_key

    def _get_headers(self) -> dict:
        """リクエストヘッダーを取得"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def describe_image(
        self,
        image_bytes: bytes,
        prompt: str = "この画像に写っている人物の服装・衣装を詳しく説明してください。",
    ) -> str:
        """画像を説明する (LLaVA)

        Args:
            image_bytes: 画像バイナリ
            prompt: 説明を求めるプロンプト

        Returns:
            画像の説明テキスト

        Raises:
            LiteLLMClientError: API呼び出しに失敗した場合
        """
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        payload = {
            "model": self.llava_model,
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
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers=self._get_headers(),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as e:
                raise LiteLLMClientError(
                    f"LLaVA API error: {e.response.status_code} - {e.response.text}"
                ) from e
            except httpx.RequestError as e:
                raise LiteLLMClientError(f"LLaVA request failed: {e}") from e
            except (KeyError, IndexError) as e:
                raise LiteLLMClientError(f"Invalid LLaVA response: {e}") from e

    async def generate_feeling(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """心境テキストを生成する (心理状態用モデル: gpt-oss:20b対応)

        Args:
            system_prompt: システムプロンプト
            user_prompt: ユーザープロンプト

        Returns:
            生成された心境テキスト

        Raises:
            LiteLLMClientError: API呼び出しに失敗した場合
        """
        payload = {
            "model": self.feeling_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 4096,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers=self._get_headers(),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as e:
                raise LiteLLMClientError(
                    f"LLM API error: {e.response.status_code} - {e.response.text}"
                ) from e
            except httpx.RequestError as e:
                raise LiteLLMClientError(f"LLM request failed: {e}") from e
            except (KeyError, IndexError) as e:
                raise LiteLLMClientError(f"Invalid LLM response: {e}") from e

    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """テキストを生成する (汎用LLM)

        Args:
            system_prompt: システムプロンプト
            user_prompt: ユーザープロンプト

        Returns:
            生成されたテキスト

        Raises:
            LiteLLMClientError: API呼び出しに失敗した場合
        """
        payload = {
            "model": self.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 4096,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers=self._get_headers(),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as e:
                raise LiteLLMClientError(
                    f"LLM API error: {e.response.status_code} - {e.response.text}"
                ) from e
            except httpx.RequestError as e:
                raise LiteLLMClientError(f"LLM request failed: {e}") from e
            except (KeyError, IndexError) as e:
                raise LiteLLMClientError(f"Invalid LLM response: {e}") from e

    async def generate_feeling_stream(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> AsyncGenerator[str, None]:
        """心境テキストをストリーミング生成する (心理状態用モデル: gpt-oss:20b対応)

        merge_reasoning_content_in_choices=true設定時、LiteLLM Proxyは
        reasoning_contentを<think>...</think>タグで囲んでcontentにマージする。
        このメソッドは<think>タグ内の思考過程を除去し、実際の回答のみをyieldする。

        Args:
            system_prompt: システムプロンプト
            user_prompt: ユーザープロンプト

        Yields:
            テキストチャンク (トークン単位、思考過程は除外)

        Raises:
            LiteLLMClientError: API呼び出しに失敗した場合
        """
        payload = {
            "model": self.feeling_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 4096,
            "stream": True,
        }

        # <think>タグ内の思考過程をスキップするための状態管理
        in_think_block = False

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/v1/chat/completions",
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
                                logger.debug("Streaming completed: [DONE]")
                                break
                            try:
                                data = json.loads(data_str)
                                choices = data.get("choices", [])
                                if not choices:
                                    continue

                                delta = choices[0].get("delta", {})
                                content = delta.get("content")

                                if content:
                                    # <think>タグの開始/終了を検出
                                    if "<think>" in content:
                                        in_think_block = True
                                        # <think>より前の部分があれば出力
                                        before_think = content.split("<think>")[0]
                                        if before_think:
                                            yield before_think
                                        logger.debug("Entering <think> block")
                                        continue

                                    if "</think>" in content:
                                        in_think_block = False
                                        # </think>より後の部分があれば出力
                                        after_think = content.split("</think>", 1)[-1]
                                        if after_think:
                                            logger.debug(
                                                "Exiting <think> block, yielding: %s",
                                                after_think[:30],
                                            )
                                            yield after_think
                                        else:
                                            logger.debug("Exiting <think> block")
                                        continue

                                    # 思考ブロック内はスキップ
                                    if in_think_block:
                                        logger.debug(
                                            "Skipping think content: %s...",
                                            content[:20]
                                            if len(content) > 20
                                            else content,
                                        )
                                        continue

                                    # 通常のコンテンツはyield
                                    logger.debug(
                                        "Yielding chunk: %s",
                                        content[:50] if len(content) > 50 else content,
                                    )
                                    yield content

                            except json.JSONDecodeError as e:
                                logger.warning(
                                    "JSON decode error: %s, line: %s", e, line[:100]
                                )
                                continue
            except httpx.HTTPStatusError as e:
                raise LiteLLMClientError(
                    f"LLM streaming API error: {e.response.status_code}"
                ) from e
            except httpx.RequestError as e:
                raise LiteLLMClientError(f"LLM streaming request failed: {e}") from e

    async def generate_image_edit_prompt(
        self,
        instruction: str,
        current_description: str = "",
        preserve_elements: list[str] | None = None,
        change_scope: str = "full",
        custom_preserve_text: str = "",
        *,
        provider: str = "selfhost",
        extra_system_suffix: str = "",
        nsfw_mode: bool = False,
        suppress_gender_discomfort_cues: bool = False,
    ) -> str:
        """画像編集用プロンプトを生成する (LLM)

        ユーザーの簡潔な日本語指示を、Qwen Image Edit向けの
        詳細な英語プロンプトに変換する。

        Args:
            instruction: ユーザーの着せ替え指示（日本語）
            current_description: 現在の画像の説明（オプション）
            preserve_elements: 保持する要素のリスト
            change_scope: 変更対象 (full, upper, lower, accessories, shoes)
            custom_preserve_text: カスタム保持指示（自由記述）
            extra_system_suffix: システムプロンプト末尾に付与する追加指示（メモリ優先指示等）

        Returns:
            生成された英語プロンプト

        Raises:
            LiteLLMClientError: API呼び出しに失敗した場合
        """
        from .prompts import (
            build_image_edit_prompt,
            get_image_edit_system_prompt,
        )

        user_prompt = build_image_edit_prompt(
            instruction=instruction,
            current_description=current_description,
            preserve_elements=preserve_elements,
            change_scope=change_scope,
            custom_preserve_text=custom_preserve_text,
        )

        system_prompt = get_image_edit_system_prompt(
            image_provider=provider,
            nsfw_mode=nsfw_mode,
            suppress_gender_discomfort_cues=suppress_gender_discomfort_cues,
        )
        if extra_system_suffix:
            system_prompt = system_prompt + extra_system_suffix

        payload = {
            "model": self.llm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 4096,
            "temperature": 0.7,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers=self._get_headers(),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()
            except httpx.HTTPStatusError as e:
                raise LiteLLMClientError(
                    f"Prompt generation API error: {e.response.status_code} - {e.response.text}"
                ) from e
            except httpx.RequestError as e:
                raise LiteLLMClientError(
                    f"Prompt generation request failed: {e}"
                ) from e
            except (KeyError, IndexError) as e:
                raise LiteLLMClientError(
                    f"Invalid prompt generation response: {e}"
                ) from e

    async def health_check(self) -> dict:
        """ヘルスチェック

        Returns:
            各モデルの接続状態
        """
        result = {
            "llava": False,
            "llm": False,
        }

        async with httpx.AsyncClient(timeout=2.0) as client:
            # LiteLLM Proxyのヘルスチェック (短いタイムアウトで迅速に応答)
            try:
                response = await client.get(
                    f"{self.base_url}/health",
                    headers=self._get_headers(),
                )
                if response.status_code == 200:
                    result["llava"] = True
                    result["llm"] = True
            except httpx.RequestError:
                pass

        return result


# グローバルクライアントインスタンス
litellm_client = LiteLLMClient()
