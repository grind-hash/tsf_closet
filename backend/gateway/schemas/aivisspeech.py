"""AivisSpeech（エンジン・モデル管理、音声合成）の API モデル。"""

from __future__ import annotations

from pydantic import BaseModel, Field


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
