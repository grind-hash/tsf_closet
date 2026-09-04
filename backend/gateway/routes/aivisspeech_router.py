from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..services.aivisspeech_service import AivisSpeechError, aivisspeech_service
from ..settings.app_settings import settings

router = APIRouter(prefix="/aivisspeech", tags=["aivisspeech"])


class DownloadRequest(BaseModel):
    url: str
    target_dir: str


class ExtractRequest(BaseModel):
    zip_path: str
    destination_dir: str


class StartEngineRequest(BaseModel):
    engine_dir: str
    use_gpu: bool = False


class InstallModelRequest(BaseModel):
    model_path: str


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1)
    speaker_id: str = Field(..., min_length=1)


class VisemeEventModel(BaseModel):
    """口パク用の口形状イベント。時刻は合成音声の先頭からの秒"""

    t0: float
    t1: float
    viseme: str
    w: float


class SynthesizeTimedResponse(BaseModel):
    audio_base64: str
    content_type: str
    duration_sec: float
    timeline: list[VisemeEventModel]


@router.get("/status")
async def get_status() -> dict[str, Any]:
    try:
        return await aivisspeech_service.get_status()
    except AivisSpeechError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/download-engine")
async def download_engine(request: DownloadRequest) -> dict[str, str]:
    try:
        return await aivisspeech_service.download_file(
            url=request.url,
            target_dir=request.target_dir,
        )
    except AivisSpeechError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/extract-engine")
async def extract_engine(request: ExtractRequest) -> dict[str, str]:
    try:
        return await aivisspeech_service.extract_zip(
            zip_path=request.zip_path,
            destination_dir=request.destination_dir,
        )
    except AivisSpeechError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/start-engine")
async def start_engine(request: StartEngineRequest) -> dict[str, Any]:
    try:
        return await aivisspeech_service.start_engine(
            engine_dir=request.engine_dir,
            use_gpu=request.use_gpu,
        )
    except AivisSpeechError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/stop-engine")
async def stop_engine() -> dict[str, Any]:
    try:
        return await aivisspeech_service.stop_engine()
    except AivisSpeechError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/restart-engine")
async def restart_engine(request: StartEngineRequest) -> dict[str, Any]:
    try:
        return await aivisspeech_service.restart_engine(
            engine_dir=request.engine_dir,
            use_gpu=request.use_gpu,
        )
    except AivisSpeechError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/download-model")
async def download_model(request: DownloadRequest) -> dict[str, str]:
    try:
        return await aivisspeech_service.download_model(
            url=request.url,
            target_dir=request.target_dir,
        )
    except AivisSpeechError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/install-model")
async def install_model(request: InstallModelRequest) -> dict[str, Any]:
    try:
        return await aivisspeech_service.install_model(model_path=request.model_path)
    except AivisSpeechError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/speakers")
async def speakers() -> list[dict[str, Any]]:
    try:
        return await aivisspeech_service.get_speakers()
    except AivisSpeechError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/synthesize")
async def synthesize(request: SynthesizeRequest) -> Response:
    try:
        audio, content_type = await aivisspeech_service.synthesize(
            text=request.text,
            speaker=request.speaker_id,
        )
        return Response(content=audio, media_type=content_type)
    except AivisSpeechError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/synthesize-timed")
async def synthesize_timed(request: SynthesizeRequest) -> SynthesizeTimedResponse:
    """音声と viseme タイムラインを1レスポンスで返す(3D モデルの口パク用)"""
    try:
        result = await aivisspeech_service.synthesize_timed(
            text=request.text,
            speaker=request.speaker_id,
        )
    except AivisSpeechError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SynthesizeTimedResponse(
        audio_base64=base64.b64encode(result.audio).decode("ascii"),
        content_type=result.content_type,
        duration_sec=result.duration_sec,
        timeline=[
            VisemeEventModel(t0=event.t0, t1=event.t1, viseme=event.viseme, w=event.w)
            for event in result.timeline
        ],
    )


@router.get("/defaults")
async def defaults() -> dict[str, str]:
    return {
        "engine_download_url": settings.aivis_engine_download_url,
        "model_download_url": settings.aivis_default_model_url,
    }
