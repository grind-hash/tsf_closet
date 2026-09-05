"""OpenAI互換 Images API の multipart 処理。

画像・マスク・パラメータの抽出、ネストしたフォーム項目と extra_body の解析、
ComfyUI ワークフローの実行、Base64 での OpenAI 互換レスポンス組み立てを行う。
エンドポイント自体は routes/openai_images_router.py にある。"""

from __future__ import annotations

import base64
import binascii
import json
import re
import time
from collections.abc import Sequence
from typing import Any

import httpx
from fastapi import HTTPException, UploadFile
from fastapi.responses import JSONResponse
from starlette.datastructures import FormData

from ..settings.app_settings import Settings
from .comfy import ComfyUIClient, ComfyUIError

# OpenAI互換レスポンスで返すモデル名
MODEL_NAME = "qwen-image-edit"

# ComfyUIにアップロード可能な画像タイプ (input/output/temp)
_DEF_PLACEHOLDER_TYPES = {"input", "output", "temp"}


def _is_upload(value: object) -> bool:
    """オブジェクトがアップロードファイルかどうかを判定

    Args:
        value: チェック対象のオブジェクト

    Returns:
        bool: UploadFileインスタンスの場合True
    """
    return hasattr(value, "filename") and hasattr(value, "read")


def _decode_image_payload(value: str) -> bytes:
    """Base64エンコードされた画像データをデコード

    Data URL形式 (data:image/png;base64,xxx) と純粋なBase64文字列の両方に対応。

    Args:
        value: Base64エンコードされた画像文字列

    Returns:
        bytes: デコードされた画像バイナリ

    Raises:
        ValueError: Base64デコードに失敗した場合
    """
    # Data URL形式の場合、カンマ以降のBase64部分を抽出
    if value.startswith("data:"):
        try:
            _, encoded = value.split(",", 1)
        except ValueError as exc:
            raise ValueError("Invalid data URL for image placeholder") from exc
    else:
        encoded = value

    # Base64デコード
    try:
        return base64.b64decode(encoded)
    except binascii.Error as exc:
        raise ValueError(f"Invalid base64 image payload: {exc}") from exc


def _find_upload(
    form: FormData, names: Sequence[str], *, fallback_prefix: str
) -> UploadFile | None:
    """multipart/form-dataから画像ファイルアップロードを探索

    フォームデータから指定された名前のファイルアップロードを検索。
    配列形式のフィールドやプレフィックスマッチングにも対応。

    Args:
        form: FastAPIのFormDataオブジェクト
        names: 検索するフィールド名のリスト (例: ["image", "image[]"])
        fallback_prefix: 名前が見つからない場合のプレフィックスマッチング用

    Returns:
        UploadFile | None: 見つかったファイル、または None
    """
    # 1. 通常のフィールド名で検索
    for name in names:
        value = form.get(name)
        if _is_upload(value):
            return value

    # 2. 配列形式のフィールド (getlistメソッド使用)
    getlist = getattr(form, "getlist", None)
    if callable(getlist):
        for name in names:
            items = getlist(name)
            for item in items:
                if _is_upload(item):
                    return item

    # 3. フォールバック: プレフィックスマッチング
    for key, value in form.multi_items():
        if _is_upload(value) and (key in names or key.startswith(fallback_prefix)):
            return value
    return None


def _collect_nested_form_data(form: FormData) -> dict[str, Any]:
    """ネストされたフォームデータを辞書形式に変換

    "replacements[key1]" や "image_placeholders[img1][data]" のような
    ブラケット記法を、ネストした辞書構造に変換します。

    例:
        replacements[__SEED__]=12345 → {"replacements": {"__SEED__": "12345"}}

    Args:
        form: FastAPIのFormDataオブジェクト

    Returns:
        Dict[str, Any]: ネストされた辞書構造
    """
    nested: dict[str, Any] = {}
    for key, value in form.multi_items():
        # ブラケット記法でないフィールドはスキップ
        if "[" not in key:
            continue

        # "replacements[__SEED__]" → ["replacements", "__SEED__"]
        parts = re.findall(r"[^\[\]]+", key)
        if not parts:
            continue

        # ネストした辞書を構築
        current: dict[str, Any] = nested
        for part in parts[:-1]:
            current = current.setdefault(part, {})  # type: ignore[assignment]
        current[parts[-1]] = value
    return nested


async def process_image_form(
    form: FormData,
    *,
    client: ComfyUIClient,
    cfg: Settings,
    force_mask_none: bool = False,
) -> JSONResponse:
    """画像編集リクエストのメイン処理関数

    multipart/form-dataから画像・マスク・パラメータを抽出し、
    ComfyUIでワークフローを実行してOpenAI互換形式で結果を返却。

    処理フロー:
    1. プロンプト・画像・マスク・生成枚数などの基本パラメータを抽出
    2. ネストされたフォームデータ (replacements, image_placeholders) を解析
    3. extra_body (JSON形式の追加パラメータ) を解析
    4. ComfyUIクライアントで画像編集を実行
    5. Base64エンコードしてOpenAI互換レスポンスを返却

    Args:
        form: multipart/form-dataのパース結果
        client: ComfyUIクライアントインスタンス
        cfg: アプリケーション設定
        force_mask_none: Trueの場合、マスクを強制的に無効化 (variations用)

    Returns:
        JSONResponse: OpenAI互換のレスポンス

    Raises:
        HTTPException: パラメータエラーやComfyUI通信エラー時
    """
    # ========================================
    # 1. 基本パラメータの抽出
    # ========================================

    # プロンプト (テキスト)
    prompt_value = form.get("prompt")
    if prompt_value is not None and not isinstance(prompt_value, str):
        raise HTTPException(status_code=400, detail="prompt must be a text field")
    prompt: str | None = prompt_value

    # ネストされたフォームデータを収集 (replacements[xxx], image_placeholders[xxx] など)
    nested_fields = _collect_nested_form_data(form)

    # 画像ファイル (必須)
    image_upload = _find_upload(form, ("image", "image[]"), fallback_prefix="image")
    if image_upload is None:
        available_keys = sorted({key for key, _ in form.multi_items()})
        key_types = {key: type(value).__name__ for key, value in form.multi_items()}
        raise HTTPException(
            status_code=400,
            detail=(
                "Image upload 'image' is required "
                f"(received keys: {available_keys}, types: {key_types})"
            ),
        )

    # マスク画像 (オプション)
    # variations エンドポイントの場合は force_mask_none=True でマスクを強制無視
    raw_mask_upload = _find_upload(form, ("mask", "mask[]"), fallback_prefix="mask")
    mask_upload: UploadFile | None = None
    if raw_mask_upload is not None:
        if force_mask_none:
            await raw_mask_upload.close()
        else:
            mask_upload = raw_mask_upload
    else:
        mask_value = form.get("mask")
        if isinstance(mask_value, UploadFile):
            if force_mask_none:
                await mask_value.close()
            else:
                mask_upload = mask_value
        elif mask_value not in (None, "", b""):
            raise HTTPException(
                status_code=400, detail="mask must be provided as a file upload"
            )

    # 生成枚数 (n) の取得 (デフォルト: 1)
    n_value = form.get("n")
    if isinstance(n_value, UploadFile):
        raise HTTPException(status_code=400, detail="n must be provided as text")
    if n_value in (None, ""):
        n = 1
    else:
        try:
            n = int(str(n_value).strip())
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400, detail="n must be an integer"
            ) from None
    if n < 1:
        raise HTTPException(status_code=400, detail="n must be >= 1")

    # レスポンス形式 (デフォルト: b64_json)
    response_format_value = form.get("response_format")
    if isinstance(response_format_value, UploadFile):
        raise HTTPException(
            status_code=400, detail="response_format must be provided as text"
        )
    if response_format_value in (None, ""):
        response_format = "b64_json"
    else:
        response_format = str(response_format_value).strip()
    if response_format not in {"b64_json", "b64_bytes"}:
        raise HTTPException(
            status_code=400, detail="Only base64 responses are supported"
        )

    # ========================================
    # 2. extra_body (拡張パラメータ) の解析
    # ========================================
    # extra_body: JSON形式の追加パラメータ
    # - workflow: 使用するワークフロー名 ("default", "instruct_game" など)
    # - replacements: ワークフローテンプレート内のプレースホルダー置換用
    # - negative_prompt: ネガティブプロンプト
    # - image_placeholders: 追加画像のBase64データ

    extra_body_value = form.get("extra_body")
    extra_body: str | None
    if isinstance(extra_body_value, UploadFile):
        try:
            extra_body_bytes = await extra_body_value.read()
        except Exception as exc:  # pragma: no cover - defensive
            raise HTTPException(
                status_code=400, detail=f"Could not read extra_body: {exc}"
            ) from exc
        finally:
            await extra_body_value.close()
        extra_body = extra_body_bytes.decode("utf-8")
    elif isinstance(extra_body_value, str):
        extra_body = extra_body_value
    else:
        extra_body = None

    # パラメータを統合するためのリスト
    extra_payloads: list[dict[str, Any]] = []

    # ネストフィールド (replacements[xxx], image_placeholders[xxx]) を処理
    if nested_fields:
        nested_payload: dict[str, Any] = {}

        # replacements の処理
        nested_replacements = nested_fields.get("replacements")
        if isinstance(nested_replacements, dict) and nested_replacements:
            nested_payload["replacements"] = {
                str(key): str(value)
                for key, value in nested_replacements.items()
                if value is not None
            }

        # image_placeholders の処理
        nested_image_placeholders = nested_fields.get("image_placeholders")
        if isinstance(nested_image_placeholders, dict) and nested_image_placeholders:
            placeholder_entries: dict[str, Any] = {}
            for placeholder, raw_value in nested_image_placeholders.items():
                if isinstance(raw_value, dict):
                    data_value = raw_value.get("data")
                    type_value = raw_value.get("type", "input")
                    if data_value is None:
                        continue
                    placeholder_entries[placeholder] = {
                        "data": str(data_value),
                        "type": str(type_value) if type_value is not None else "input",
                    }
                elif raw_value is not None:
                    placeholder_entries[placeholder] = str(raw_value)
            if placeholder_entries:
                nested_payload["image_placeholders"] = placeholder_entries
        nested_negative_prompt = nested_fields.get("negative_prompt")
        if isinstance(nested_negative_prompt, str):
            nested_payload["negative_prompt"] = nested_negative_prompt
        if nested_payload:
            extra_payloads.append(nested_payload)

    if extra_body:
        try:
            extra_payload = json.loads(extra_body)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid extra_body: {exc}"
            ) from exc
        if not isinstance(extra_payload, dict):
            raise HTTPException(
                status_code=400, detail="Invalid extra_body: must be an object"
            )
        extra_payloads.append(extra_payload)

    # ========================================
    # 3. 画像ファイルの読み込み
    # ========================================

    # メイン画像の読み込み
    try:
        image_bytes = await image_upload.read()
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=400, detail=f"Could not read image: {exc}"
        ) from exc
    finally:
        await image_upload.close()

    # マスク画像の読み込み
    mask_bytes: bytes | None = None
    if mask_upload is not None:
        try:
            mask_bytes = await mask_upload.read()
        except Exception as exc:  # pragma: no cover - defensive
            raise HTTPException(
                status_code=400, detail=f"Could not read mask: {exc}"
            ) from exc
        finally:
            await mask_upload.close()

    # ========================================
    # 4. プレースホルダー置換と追加画像の準備
    # ========================================

    replacements: dict[str, Any] = {}  # ワークフロー内の __PROMPT__ などを置換
    extra_images: dict[str, dict[str, Any]] = {}  # 追加画像 (Base64デコード済み)

    # extra_payloads から replacements と image_placeholders を抽出
    for payload in extra_payloads:
        # replacements の処理
        replacements_payload = payload.get("replacements")
        if replacements_payload is not None:
            if not isinstance(replacements_payload, dict):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid extra_body: replacements must be an object",
                )
            for key, value in replacements_payload.items():
                if value is None:
                    continue
                replacements[str(key)] = str(value)

        # negative_prompt の処理
        negative_prompt = payload.get("negative_prompt")
        if negative_prompt is not None:
            if isinstance(negative_prompt, (str, bytes, bytearray)):
                neg_value = (
                    negative_prompt
                    if isinstance(negative_prompt, str)
                    else negative_prompt.decode("utf-8", "ignore")
                )
                replacements["__NEGATIVE_PROMPT__"] = neg_value
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid extra_body: negative_prompt must be a string",
                )

        # image_placeholders の処理
        image_placeholders_payload = payload.get("image_placeholders")
        if image_placeholders_payload is not None:
            if not isinstance(image_placeholders_payload, dict):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid extra_body: image_placeholders must be an object",
                )
            for placeholder, value in image_placeholders_payload.items():
                if isinstance(value, dict):
                    data_value = value.get("data")
                    file_type = value.get("type", "input")
                else:
                    data_value = value
                    file_type = "input"
                if data_value is None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"image placeholder {placeholder} requires data",
                    )
                image_bytes_payload = _decode_image_payload(str(data_value))
                entry = {"bytes": image_bytes_payload}
                file_type_str = str(file_type) if file_type is not None else "input"
                entry["type"] = (
                    file_type_str
                    if file_type_str in _DEF_PLACEHOLDER_TYPES
                    else "input"
                )
                extra_images[placeholder] = entry

    # ネガティブプロンプトのデフォルト値を設定
    replacements.setdefault("__NEGATIVE_PROMPT__", "")

    # ========================================
    # 5. ワークフローの選択
    # ========================================

    workflow_name: str | None = None
    for payload in extra_payloads:
        wf = payload.get("workflow")
        if wf is not None:
            workflow_name = str(wf)
            break

    # workflow パラメータはフォームフィールドからも取得可能
    if workflow_name is None:
        workflow_value = form.get("workflow")
        if isinstance(workflow_value, str) and workflow_value:
            workflow_name = workflow_value.strip()

    # ワークフローパスを取得
    workflow_path = None
    if workflow_name:
        try:
            workflow_path = cfg.get_workflow_path(workflow_name)
            cfg.ensure_workflow_exists(workflow_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # ========================================
    # 6. ComfyUIで画像編集を実行
    # ========================================

    try:
        result = await client.image_edit(
            image_bytes=image_bytes,
            prompt=prompt,
            mask_bytes=mask_bytes,
            replacements=replacements,
            limit=n,
            extra_images=extra_images or None,
            workflow_path=workflow_path,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except ComfyUIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"ComfyUI request failed: {exc}"
        ) from exc

    # ========================================
    # 7. OpenAI互換形式でレスポンスを生成
    # ========================================

    # 指定された枚数分だけ取得
    images = result.images[:n]

    # 画像をBase64エンコード
    data = []
    for image_bytes in images:
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        key = "b64_bytes" if response_format == "b64_bytes" else "b64_json"
        data.append({key: encoded})

    # OpenAI Images API互換レスポンスを構築
    payload = {
        "created": int(time.time()),
        "data": data,
        "model": MODEL_NAME,
        "object": "image.edit",
    }
    return JSONResponse(payload)
