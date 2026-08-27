from io import BytesIO
from unittest.mock import AsyncMock
import wave

import httpx
import pytest

from gateway.services.aivisspeech_service import (
    AivisSpeechError,
    AivisSpeechService,
)

ENGINE_BASE_URL = "http://127.0.0.1:10101"


def _mock_http_client(monkeypatch, handler):
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: client)


def _make_wav(frames: bytes, sample_rate: int = 24000) -> bytes:
    output = BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(frames)
    return output.getvalue()


@pytest.mark.asyncio
async def test_wait_for_engine_ready_retries_until_version_responds(
    monkeypatch,
) -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            raise httpx.ConnectError("not ready", request=request)
        return httpx.Response(200, request=request)

    _mock_http_client(monkeypatch, handler)
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    service = AivisSpeechService()

    await service._wait_for_engine_ready(ENGINE_BASE_URL, timeout=1.0)

    assert request_count == 2


@pytest.mark.asyncio
async def test_wait_for_engine_ready_reports_process_exit(
    monkeypatch, tmp_path
) -> None:
    class ExitedProcess:
        returncode = 7

        @staticmethod
        def poll() -> int:
            return 7

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request)

    _mock_http_client(monkeypatch, handler)
    log_path = tmp_path / "aivisspeech_engine.log"
    log_path.write_text("engine startup failed", encoding="utf-8")
    service = AivisSpeechService()
    service._engine_process = ExitedProcess()
    service._engine_log_path = log_path

    with pytest.raises(AivisSpeechError, match="engine startup failed"):
        await service._wait_for_engine_ready(ENGINE_BASE_URL, timeout=1.0)

    assert service._engine_process is None


@pytest.mark.asyncio
async def test_wait_for_engine_ready_reports_timeout(monkeypatch, tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _mock_http_client(monkeypatch, handler)
    log_path = tmp_path / "aivisspeech_engine.log"
    log_path.write_text("Loading BERT model", encoding="utf-8")
    service = AivisSpeechService()
    service._engine_log_path = log_path

    with pytest.raises(AivisSpeechError, match="did not become ready") as exc_info:
        await service._wait_for_engine_ready(ENGINE_BASE_URL, timeout=0.01)

    message = str(exc_info.value)
    assert "ConnectError" in message
    assert "Loading BERT model" in message


def test_split_synthesis_text_limits_chunk_size_and_removes_leading_symbol() -> None:
    source = "💭 \n" + "これは音声合成の分割テストです。" * 30

    chunks = AivisSpeechService._split_synthesis_text(source, max_chars=200)

    assert len(chunks) > 1
    assert all(len(chunk) <= 200 for chunk in chunks)
    assert not chunks[0].startswith("💭")
    assert "".join(chunks).replace("\n", "") == source.removeprefix("💭 \n")


def test_merge_wav_chunks_concatenates_pcm_frames() -> None:
    first_frames = b"\x01\x00\x02\x00"
    second_frames = b"\x03\x00\x04\x00"

    merged = AivisSpeechService._merge_wav_chunks(
        [_make_wav(first_frames), _make_wav(second_frames)]
    )

    with wave.open(BytesIO(merged), "rb") as reader:
        assert reader.getnchannels() == 1
        assert reader.getsampwidth() == 2
        assert reader.getframerate() == 24000
        assert reader.readframes(reader.getnframes()) == first_frames + second_frames


@pytest.mark.asyncio
async def test_synthesize_processes_chunks_sequentially_and_returns_single_wav(
    monkeypatch,
) -> None:
    query_texts: list[str] = []
    synthesized_frames: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/audio_query"):
            query_texts.append(request.url.params["text"])
            return httpx.Response(200, json={"accent_phrases": []}, request=request)

        frame = len(synthesized_frames) + 1
        frame_bytes = frame.to_bytes(2, byteorder="little", signed=True)
        synthesized_frames.append(frame_bytes)
        return httpx.Response(
            200,
            content=_make_wav(frame_bytes),
            headers={"content-type": "audio/wav"},
            request=request,
        )

    _mock_http_client(monkeypatch, handler)
    service = AivisSpeechService()
    source = "💭 \n" + "長文音声を安全に分割して合成します。" * 20

    monkeypatch.setattr(
        AivisSpeechService,
        "resolve_base_url",
        AsyncMock(return_value=ENGINE_BASE_URL),
    )

    audio, content_type = await service.synthesize(source, "1234")

    assert len(query_texts) > 1
    assert all(len(chunk) <= service.SYNTHESIS_CHUNK_MAX_CHARS for chunk in query_texts)
    assert content_type == "audio/wav"
    with wave.open(BytesIO(audio), "rb") as reader:
        assert reader.readframes(reader.getnframes()) == b"".join(synthesized_frames)
