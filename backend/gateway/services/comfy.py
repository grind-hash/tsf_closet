from __future__ import annotations

import asyncio
import copy
import json
import random
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from ..settings.config import settings


class ComfyUIError(RuntimeError):
    """Raised when the ComfyUI backend reports an error."""


@dataclass(slots=True)
class ComfyUIResult:
    images: List[bytes]


class ComfyUIClient:
    """Thin async client around ComfyUI's HTTP API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        workflow_path: Optional[Path] = None,
        client_id: Optional[str] = None,
        request_timeout: Optional[float] = None,
        poll_interval: Optional[float] = None,
    ) -> None:
        settings.ensure_workflow_exists(workflow_path)
        self.base_url = (base_url or settings.comfyui_base_url).rstrip("/")
        self.workflow_path = workflow_path or settings.comfyui_workflow_path
        self.client_id = client_id or settings.comfyui_client_id
        self.request_timeout = request_timeout or settings.comfyui_request_timeout
        self.poll_interval = poll_interval or settings.comfyui_poll_interval
        self._template_cache: Dict[str, Any] = {}

    async def image_edit(
        self,
        *,
        image_bytes: bytes,
        prompt: Optional[str] = None,
        mask_bytes: Optional[bytes] = None,
        replacements: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        extra_images: Optional[Dict[str, Dict[str, Any]]] = None,
        workflow_path: Optional[Path] = None,
    ) -> ComfyUIResult:
        # 使用するワークフローパスを決定
        target_workflow_path = workflow_path or self.workflow_path
        template = self._load_template(target_workflow_path)
        replacements = dict(replacements or {})
        extra_images = extra_images or {}

        if prompt is not None:
            replacements.setdefault("__PROMPT__", prompt)
        else:
            replacements.setdefault("__PROMPT__", "")

        replacements.setdefault("__NEGATIVE_PROMPT__", "")
        replacements.setdefault("__SEED__", random.randint(0, 2**63 - 1))

        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self.request_timeout
        ) as client:
            init_image_name = await self._upload_image(
                client, image_bytes, file_type="input"
            )
            replacements.setdefault("__INIT_IMAGE__", init_image_name)

            if mask_bytes:
                mask_name = await self._upload_image(
                    client, mask_bytes, file_type="mask"
                )
                replacements.setdefault("__MASK_IMAGE__", mask_name)

            for placeholder, info in extra_images.items():
                image_data = info.get("bytes")
                if image_data is None:
                    continue
                upload_type = info.get("type") or "input"
                uploaded_name = await self._upload_image(
                    client, image_data, file_type=str(upload_type)
                )
                replacements.setdefault(placeholder, uploaded_name)

            print("REPLACEMENTS", replacements)
            prompt_payload = self._apply_replacements(template, replacements)
            print(
                "PROMPT PAYLOAD node 111 (positive)",
                prompt_payload.get("111", {}).get("inputs", {}).get("prompt", "")[:100]
                if prompt_payload.get("111")
                else "N/A",
            )
            payload = self._build_prompt_payload(prompt_payload)

            response = await client.post("/prompt", json=payload)
            if response.status_code >= 400:
                error_text = response.text
                print(f"ComfyUI error response ({response.status_code}): {error_text}")
                raise ComfyUIError(
                    f"ComfyUI prompt failed ({response.status_code}): {error_text}"
                )
            prompt_id = response.json().get("prompt_id")
            print(prompt_id)
            if not prompt_id:
                raise ComfyUIError("ComfyUI did not return a prompt_id")

            images = await self._wait_for_images(client, prompt_id, limit=limit)

        if not images:
            raise ComfyUIError("ComfyUI completed without producing images")

        return ComfyUIResult(images=images)

    def _load_template(self, workflow_path: Optional[Path] = None) -> Dict[str, Any]:
        target_path = workflow_path or self.workflow_path
        cache_key = str(target_path)
        if cache_key not in self._template_cache:
            with target_path.open("r", encoding="utf-8") as f:
                self._template_cache[cache_key] = json.load(f)
        return copy.deepcopy(self._template_cache[cache_key])

    @staticmethod
    async def _upload_image(
        client: httpx.AsyncClient,
        image_bytes: bytes,
        *,
        file_type: str = "input",
    ) -> str:
        """Upload raw image bytes to ComfyUI and return its storage path."""

        import imghdr

        kind = imghdr.what(None, h=image_bytes) or "png"
        if kind == "jpeg":
            ext = "jpg"
            mime = "image/jpeg"
        elif kind == "png":
            ext = "png"
            mime = "image/png"
        elif kind == "gif":
            ext = "gif"
            mime = "image/gif"
        elif kind == "webp":
            ext = "webp"
            mime = "image/webp"
        else:
            ext = "png"
            mime = "image/png"

        filename = f"{uuid.uuid4().hex}.{ext}"

        upload_type = file_type if file_type in {"input", "temp", "output"} else "input"
        data = {
            "type": upload_type,
            "overwrite": "true",
        }
        files = {
            "image": (filename, image_bytes, mime),
        }

        response = await client.post("/upload/image", data=data, files=files)
        response.raise_for_status()
        data = response.json()
        # API may return either "name" or "filename" depending on version.
        return data.get("name") or data.get("filename") or filename

    def _apply_replacements(self, value: Any, replacements: Dict[str, Any]) -> Any:
        if isinstance(value, dict):
            return {
                key: self._apply_replacements(item, replacements)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._apply_replacements(item, replacements) for item in value]
        if isinstance(value, str):
            if value in replacements:
                return replacements[value]
            updated = value
            for placeholder, actual in replacements.items():
                if isinstance(actual, (dict, list)):
                    continue
                actual_str = str(actual)
                if placeholder in updated:
                    updated = updated.replace(placeholder, actual_str)
            return updated
        return value

    def _build_prompt_payload(self, prompt_payload: Dict[str, Any]) -> Dict[str, Any]:
        if "prompt" in prompt_payload:
            graph = prompt_payload["prompt"]
            extra_data = prompt_payload.get("extra_data")
        else:
            graph = prompt_payload
            extra_data = None

        payload: Dict[str, Any] = {
            "prompt": graph,
            "client_id": self.client_id,
        }
        if extra_data:
            payload["extra_data"] = extra_data
        return payload

    async def _wait_for_images(
        self,
        client: httpx.AsyncClient,
        prompt_id: str,
        *,
        limit: Optional[int] = None,
    ) -> List[bytes]:
        deadline = time.monotonic() + self.request_timeout
        while time.monotonic() < deadline:
            response = await client.get(f"/history/{prompt_id}")
            status_code = response.status_code
            if status_code == 404:
                await asyncio.sleep(self.poll_interval)
                continue
            if 500 <= status_code < 600:
                print(f"COMFYUI history fetch returned {status_code}, retrying")
                await asyncio.sleep(self.poll_interval)
                continue
            if status_code >= 400:
                raise ComfyUIError(
                    f"ComfyUI history fetch failed (status {status_code}): {response.text}"
                )

            try:
                payload = response.json() or {}
            except ValueError:
                print("COMFYUI history returned invalid JSON; retrying")
                await asyncio.sleep(self.poll_interval)
                continue
            if not isinstance(payload, dict):
                await asyncio.sleep(self.poll_interval)
                continue

            history: Dict[str, Any] = {}
            history_data = payload.get("history")
            if isinstance(history_data, dict):
                history = history_data
            elif prompt_id in payload and isinstance(payload[prompt_id], dict):
                history = {prompt_id: payload[prompt_id]}

            entry = history.get(prompt_id)
            print(entry)
            if not entry:
                await asyncio.sleep(self.poll_interval)
                continue
            status_block = entry.get("status") or {}
            status_str = status_block.get("status_str") or status_block.get("status")
            completed_flag = status_block.get("completed")

            if status_str in {"failed", "error"}:
                message = status_block.get("message") or "unknown"
                raise ComfyUIError(f"ComfyUI workflow failed: {message}")

            if status_str == "success" and completed_flag is True:
                outputs = entry.get("outputs", {})
                print(
                    f"COMFYUI history success prompt={prompt_id} output_nodes={list(outputs.keys())}"
                )
                images = await self._collect_images(client, outputs, limit=limit)
                if images:
                    return images
                extra_data = entry.get("extra_data") or {}
                if extra_data:
                    print(f"COMFYUI extra_data keys={list(extra_data.keys())}")
                print(
                    "COMFYUI reported success but no images yet; waiting for next poll"
                )
            await asyncio.sleep(self.poll_interval)
        raise TimeoutError("Timed out waiting for ComfyUI to finish rendering")

    async def _collect_images(
        self,
        client: httpx.AsyncClient,
        outputs: Dict[str, Any],
        *,
        limit: Optional[int] = None,
    ) -> List[bytes]:
        images: List[bytes] = []
        for node_id, node in outputs.items():
            image_list = node.get("images", [])
            if not image_list:
                continue
            print(
                f"COMFYUI downloading images from node {node_id} count={len(image_list)}"
            )
            for image_info in image_list:
                image_bytes = await self._download_image(client, image_info)
                images.append(image_bytes)
                if limit and len(images) >= limit:
                    return images
        if not images:
            print(
                f"COMFYUI no downloadable images found in outputs: {list(outputs.keys())}"
            )
        return images

    @staticmethod
    async def _download_image(
        client: httpx.AsyncClient, image_info: Dict[str, Any]
    ) -> bytes:
        params = {
            "filename": image_info.get("filename"),
            "subfolder": image_info.get("subfolder", ""),
            "type": image_info.get("type", "output"),
        }
        response = await client.get("/view", params=params)
        response.raise_for_status()
        return response.content
