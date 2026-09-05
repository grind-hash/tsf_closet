from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import socket
import subprocess
import sys
import tempfile
import unicodedata
import wave
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import IO, Any
from urllib.parse import urlparse

import httpx

from ..settings.app_settings import BASE_DIR, settings
from .http_client import async_client

logger = logging.getLogger(__name__)

# brand_name returned by the bundled engine from /engine_manifest. A compatible
# third-party engine reports a different brand, and the management features
# specific to the bundled engine (aivmx model install, bundled run.exe) do not
# apply to it.
AIVIS_ENGINE_BRAND = "AivisSpeech"


class AivisSpeechError(Exception):
    pass


# audio_query のモーラ母音 → VRM の口形状プリセット。N / cl / pau は閉口として
# タイムラインにイベントを出さない
_VOWEL_TO_VISEME = {"a": "aa", "i": "ih", "u": "ou", "e": "ee", "o": "oh"}
# 無声化母音(大文字 A/I/U/E/O)は口を小さめに開く
_DEVOICED_VISEME_WEIGHT = 0.4


@dataclass(frozen=True)
class VisemeEvent:
    """口パク用の口形状イベント。時刻は合成音声の先頭からの秒"""

    t0: float
    t1: float
    viseme: str
    w: float


@dataclass(frozen=True)
class TimedSynthesis:
    """合成音声と viseme タイムラインの対"""

    audio: bytes
    content_type: str
    duration_sec: float
    timeline: list[VisemeEvent]


class AivisSpeechService:
    SYNTHESIS_CHUNK_MAX_CHARS = 200

    def __init__(self) -> None:
        self._engine_process: subprocess.Popen | None = None
        self._engine_log_file: IO[str] | None = None
        self._engine_log_path: Path | None = None

    @staticmethod
    def _ensure_windows() -> None:
        if sys.platform != "win32":
            raise AivisSpeechError(
                "This setup step is supported only on Windows. On Linux, start the "
                "engine with `docker compose up -d aivis` instead and use the "
                "health check to confirm it is reachable."
            )

    @staticmethod
    def _default_engine_port() -> int:
        """Return the port declared by AIVIS_ENGINE_BASE_URL."""
        parsed = urlparse(settings.aivis_engine_base_url)
        if parsed.port is not None:
            return parsed.port
        return 443 if parsed.scheme == "https" else 80

    @staticmethod
    def _build_base_url(port: int) -> str:
        """Rebuild the engine base URL with the given port.

        Only the port is user-configurable. Scheme and host stay under
        AIVIS_ENGINE_BASE_URL so container deployments keep working.
        """
        parsed = urlparse(settings.aivis_engine_base_url)
        host = parsed.hostname or "127.0.0.1"
        if ":" in host:
            host = f"[{host}]"
        return f"{parsed.scheme or 'http'}://{host}:{port}"

    async def resolve_engine_port(self) -> int:
        """Return the user-configured engine port, or the default when unset."""
        from .settings_service import settings_service

        try:
            user_settings = await settings_service.get_user_settings()
        except Exception:
            logger.warning(
                "Failed to read tts_engine_port; using the default engine port",
                exc_info=True,
            )
            return self._default_engine_port()

        port = user_settings.get("tts_engine_port")
        if isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535:
            return port
        return self._default_engine_port()

    async def resolve_base_url(self) -> str:
        """Return the base URL of the engine this app should talk to."""
        return self._build_base_url(await self.resolve_engine_port())

    @staticmethod
    async def _fetch_engine_brand(
        client: httpx.AsyncClient, base_url: str
    ) -> str | None:
        """Return brand_name from /engine_manifest, identifying the engine."""
        try:
            response = await client.get(f"{base_url}/engine_manifest")
            if response.status_code >= 400:
                return None
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return None

        if not isinstance(payload, dict):
            return None
        brand = payload.get("brand_name") or payload.get("name")
        return str(brand) if brand else None

    @staticmethod
    def _expand_path(path_value: str) -> Path:
        expanded = os.path.expandvars(os.path.expanduser(path_value.strip()))
        candidate = Path(expanded)
        if not candidate.is_absolute():
            candidate = BASE_DIR.parent / candidate
        return candidate.resolve()

    @staticmethod
    def _default_model_dir() -> Path:
        # Per AivisSpeech-Engine docs, the PyInstaller-built run.exe on Windows
        # stores its data under %APPDATA%\AivisSpeech-Engine. On Linux the engine
        # runs via the `aivis` service in compose.yaml, which mounts its model
        # directory from ~/.local/share/AivisSpeech-Engine on the host.
        if sys.platform == "win32":
            base = os.getenv("APPDATA")
            if base:
                return Path(base) / "AivisSpeech-Engine" / "Models"
            return Path.home() / "AppData" / "Roaming" / "AivisSpeech-Engine" / "Models"
        return Path.home() / ".local" / "share" / "AivisSpeech-Engine" / "Models"

    @staticmethod
    def _validate_download_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise AivisSpeechError("Only https download URLs are allowed")

        hostname = (parsed.hostname or "").lower()
        allowed = {
            host.strip().lower()
            for host in settings.aivis_allowed_download_hosts.split(",")
            if host.strip()
        }
        if hostname not in allowed:
            raise AivisSpeechError(f"Download host is not allowed: {hostname}")

    async def download_file(self, url: str, target_dir: str) -> dict[str, str]:
        self._ensure_windows()
        self._validate_download_url(url)

        target = self._expand_path(target_dir)
        target.mkdir(parents=True, exist_ok=True)

        parsed = urlparse(url)
        filename = Path(parsed.path).name or "download.bin"
        destination = target / filename

        timeout = httpx.Timeout(settings.aivis_download_timeout)
        max_size = settings.aivis_max_download_bytes
        total = 0

        async with (
            async_client(timeout=timeout, follow_redirects=True) as client,
            client.stream("GET", url) as response,
        ):
            response.raise_for_status()
            with destination.open("wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_size:
                        raise AivisSpeechError(
                            "Downloaded file exceeded maximum allowed size"
                        )
                    f.write(chunk)

        return {
            "path": str(destination),
            "size": str(total),
        }

    async def extract_zip(self, zip_path: str, destination_dir: str) -> dict[str, str]:
        self._ensure_windows()
        zip_file = self._expand_path(zip_path)
        if not zip_file.exists() or not zip_file.is_file():
            raise AivisSpeechError(f"Zip file not found: {zip_file}")

        destination = self._expand_path(destination_dir)
        destination.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_file, "r") as archive:
            for member in archive.infolist():
                member_path = (destination / member.filename).resolve()
                if not str(member_path).startswith(str(destination.resolve())):
                    raise AivisSpeechError("Unsafe zip entry detected")
            archive.extractall(destination)

        run_exe = self.find_run_exe(destination)
        return {
            "destination": str(destination),
            "run_exe": str(run_exe),
        }

    @staticmethod
    def find_run_exe(engine_root: Path) -> Path:
        direct = engine_root / "AivisSpeech" / "AivisSpeech-Engine" / "run.exe"
        if direct.exists():
            return direct

        for path in engine_root.rglob("run.exe"):
            if "AivisSpeech-Engine" in str(path.parent):
                return path

        raise AivisSpeechError("run.exe not found under engine directory")

    @staticmethod
    def _is_running(process: subprocess.Popen | None) -> bool:
        return process is not None and process.poll() is None

    @staticmethod
    def _is_port_open(host: str, port: int, timeout: float = 1.5) -> bool:
        """Cross-platform TCP health check, used on Linux where the engine runs
        in a Docker container (no local PID to inspect via netstat)."""
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    @staticmethod
    def _find_pid_on_port(port: int) -> int | None:
        try:
            result = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception:
            return None

        needle = f":{port}"
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line or needle not in line:
                continue

            parts = line.split()
            if len(parts) < 5:
                continue

            local_address = parts[1]
            state = parts[3].upper()
            pid_text = parts[4]
            if not local_address.endswith(needle):
                continue
            if state != "LISTENING":
                continue

            try:
                return int(pid_text)
            except ValueError:
                continue

        return None

    async def start_engine(
        self, engine_dir: str, use_gpu: bool = False
    ) -> dict[str, Any]:
        self._ensure_windows()

        port = await self.resolve_engine_port()
        base_url = self._build_base_url(port)

        if self._is_running(self._engine_process):
            await self._wait_for_engine_ready(base_url)
            assert self._engine_process is not None
            return {
                "status": "already_running",
                "pid": self._engine_process.pid,
            }

        if self._engine_process is not None:
            self._engine_process = None
            self._close_engine_log()

        pid_on_port = self._find_pid_on_port(port)
        if pid_on_port is not None:
            # Something already serves the configured port. It may be the bundled
            # engine from a previous run, or a separately started compatible
            # engine; either way the app just connects to it.
            await self._wait_for_engine_ready(base_url)
            return {
                "status": "already_running_external",
                "pid": pid_on_port,
            }

        root = self._expand_path(engine_dir)
        run_exe = self.find_run_exe(root)

        # run.exe does not always create its model directory on first launch,
        # so ensure it exists before starting the engine.
        self._default_model_dir().mkdir(parents=True, exist_ok=True)

        # Bind the bundled engine to the configured port so it matches where the
        # app looks for it (the default 10101 may be taken by another program).
        args = [str(run_exe), "--host", "127.0.0.1", "--port", str(port)]
        if use_gpu:
            args.append("--use_gpu")

        log_path = Path(tempfile.gettempdir()) / "aivisspeech_engine.log"
        try:
            log_file = log_path.open("w", encoding="utf-8", errors="replace")
        except OSError as exc:
            raise AivisSpeechError(f"Failed to open engine log file: {exc}") from exc

        try:
            self._engine_process = subprocess.Popen(
                args,
                cwd=str(run_exe.parent),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                shell=False,
            )
        except OSError as exc:
            log_file.close()
            raise AivisSpeechError(f"Failed to start run.exe: {exc}") from exc

        self._engine_log_file = log_file
        self._engine_log_path = log_path

        process = self._engine_process
        await self._wait_for_engine_ready(base_url)

        return {
            "status": "started",
            "pid": process.pid,
            "port": port,
            "run_exe": str(run_exe),
            "log_path": str(log_path),
        }

    def _close_engine_log(self) -> None:
        if self._engine_log_file is not None:
            with contextlib.suppress(OSError):
                self._engine_log_file.close()
            self._engine_log_file = None

    @staticmethod
    def _read_log_tail(log_path: Path, max_chars: int = 800) -> str:
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return "(no log available)"
        text = text.strip()
        if len(text) > max_chars:
            return text[-max_chars:]
        return text or "(empty log)"

    async def _wait_for_engine_ready(
        self, base_url: str, timeout: float | None = None
    ) -> None:
        startup_timeout = (
            settings.aivis_engine_startup_timeout if timeout is None else timeout
        )
        if startup_timeout <= 0:
            raise AivisSpeechError("Engine startup timeout must be greater than zero")

        loop = asyncio.get_running_loop()
        deadline = loop.time() + startup_timeout
        endpoint = f"{base_url}/version"
        last_error = "health check not completed"

        async with async_client(timeout=httpx.Timeout(2.5)) as client:
            while True:
                process = self._engine_process
                if process is not None and process.poll() is not None:
                    exit_code = process.returncode
                    self._engine_process = None
                    self._close_engine_log()
                    log_path = self._engine_log_path
                    tail = (
                        self._read_log_tail(log_path)
                        if log_path is not None
                        else "(no log available)"
                    )
                    raise AivisSpeechError(
                        f"run.exe exited before the engine became ready "
                        f"(code {exit_code}). Log tail: {tail}"
                    )

                try:
                    response = await client.get(endpoint)
                    if response.status_code < 400:
                        return
                    last_error = f"HTTP {response.status_code}"
                except httpx.HTTPError as exc:
                    last_error = f"{type(exc).__name__}: {exc}"

                remaining = deadline - loop.time()
                if remaining <= 0:
                    log_path = self._engine_log_path
                    tail = (
                        self._read_log_tail(log_path)
                        if log_path is not None
                        else "(no log available)"
                    )
                    raise AivisSpeechError(
                        f"AivisSpeech Engine did not become ready within "
                        f"{startup_timeout:g} seconds. Last health check: "
                        f"{last_error}. Log tail: {tail}"
                    )

                await asyncio.sleep(min(0.5, remaining))

    async def stop_engine(self) -> dict[str, Any]:
        self._ensure_windows()

        if not self._is_running(self._engine_process):
            self._engine_process = None
            self._close_engine_log()
            pid_on_port = self._find_pid_on_port(await self.resolve_engine_port())
            if pid_on_port is None:
                return {"status": "not_running"}

            try:
                subprocess.run(
                    ["taskkill", "/PID", str(pid_on_port), "/T", "/F"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except subprocess.CalledProcessError as exc:
                raise AivisSpeechError(
                    f"Failed to stop engine process by port: {exc.stderr.strip()}"
                ) from exc
            return {"status": "stopped_external", "pid": pid_on_port}

        assert self._engine_process is not None
        self._engine_process.terminate()
        try:
            self._engine_process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self._engine_process.kill()
            self._engine_process.wait(timeout=5)

        pid = self._engine_process.pid
        self._engine_process = None
        self._close_engine_log()
        return {"status": "stopped", "pid": pid}

    async def restart_engine(
        self, engine_dir: str, use_gpu: bool = False
    ) -> dict[str, Any]:
        await self.stop_engine()
        await asyncio.sleep(0.4)
        return await self.start_engine(engine_dir=engine_dir, use_gpu=use_gpu)

    async def download_model(
        self, url: str, target_dir: str | None = None
    ) -> dict[str, str]:
        model_dir = target_dir or str(self._default_model_dir())
        return await self.download_file(url=url, target_dir=model_dir)

    @staticmethod
    def _pick_latest_model_file(directory: Path) -> Path | None:
        candidates = [
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in {".aivmx", ".aivm"}
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda p: (p.stat().st_mtime, p.name))

    def _resolve_install_model_file(self, model_path: str) -> Path:
        target = self._expand_path(model_path)

        if target.exists() and target.is_file():
            return target

        if target.exists() and target.is_dir():
            latest = self._pick_latest_model_file(target)
            if latest:
                return latest

        # Search nearby directories to absorb common manual placement mismatches.
        candidates: list[Path] = []
        for directory in [
            target,
            target.parent,
            target.parent.parent,
            self._default_model_dir(),
            self._default_model_dir().parent,
        ]:
            resolved = directory.resolve()
            if resolved.exists() and resolved.is_dir() and resolved not in candidates:
                candidates.append(resolved)

        for directory in candidates:
            latest = self._pick_latest_model_file(directory)
            if latest:
                return latest

        searched = ", ".join(str(path) for path in candidates) or str(target)
        raise AivisSpeechError(
            f"No .aivmx/.aivm model file found. Checked: {searched}."
        )

    async def install_model(self, model_path: str) -> dict[str, Any]:
        self._ensure_windows()

        file_path = self._resolve_install_model_file(model_path)

        timeout = httpx.Timeout(120.0)
        endpoint = f"{await self.resolve_base_url()}/aivm_models/install"

        try:
            async with async_client(timeout=timeout) as client:
                with file_path.open("rb") as f:
                    response = await client.post(
                        endpoint, files={"file": (file_path.name, f)}
                    )
                if response.status_code >= 400:
                    raise AivisSpeechError(
                        f"Model install failed ({response.status_code}): "
                        f"{response.text}"
                    )
        except httpx.TimeoutException as exc:
            raise AivisSpeechError("Model install request timed out") from exc
        except httpx.HTTPError as exc:
            raise AivisSpeechError(
                f"Failed to reach AivisSpeech Engine during model install: {exc}"
            ) from exc

        payload: Any
        try:
            payload = response.json()
        except ValueError:
            payload = {"status_code": response.status_code, "text": response.text}

        return {
            "status": "installed",
            "installed_model_path": str(file_path),
            "result": payload,
        }

    async def get_speakers(self) -> list[dict[str, Any]]:
        timeout = httpx.Timeout(20.0)
        endpoint = f"{await self.resolve_base_url()}/speakers"
        async with async_client(timeout=timeout) as client:
            response = await client.get(endpoint)
            response.raise_for_status()
            data = response.json()

        if not isinstance(data, list):
            raise AivisSpeechError("Unexpected speakers response format")
        return data

    @staticmethod
    def _normalize_synthesis_text(text: str) -> str:
        normalized = text.strip()
        while normalized:
            category = unicodedata.category(normalized[0])
            if not (category.startswith("S") or category in {"Cf", "Mn"}):
                break
            normalized = normalized[1:].lstrip()
        return normalized

    @staticmethod
    def _split_long_synthesis_segment(segment: str, max_chars: int) -> list[str]:
        pieces: list[str] = []
        remaining = segment.strip()
        separators = ("、", "，", ",", "；", ";", "：", ":", " ")

        while len(remaining) > max_chars:
            window = remaining[: max_chars + 1]
            split_at = max(
                (window.rfind(separator) + len(separator) for separator in separators),
                default=0,
            )
            if split_at < max_chars // 2:
                split_at = max_chars

            piece = remaining[:split_at].strip()
            if piece:
                pieces.append(piece)
            remaining = remaining[split_at:].strip()

        if remaining:
            pieces.append(remaining)
        return pieces

    @classmethod
    def _split_synthesis_text(
        cls, text: str, max_chars: int | None = None
    ) -> list[str]:
        chunk_limit = max_chars or cls.SYNTHESIS_CHUNK_MAX_CHARS
        if chunk_limit <= 0:
            raise AivisSpeechError("Synthesis chunk size must be greater than zero")

        normalized = cls._normalize_synthesis_text(text)
        if not normalized:
            return []

        segments = [
            segment.strip()
            for segment in re.split(r"(?<=[。！？!?])|\r?\n+", normalized)
            if segment.strip()
        ]
        fragments = [
            fragment
            for segment in segments
            for fragment in cls._split_long_synthesis_segment(segment, chunk_limit)
        ]

        chunks: list[str] = []
        current = ""
        for fragment in fragments:
            candidate = f"{current}\n{fragment}" if current else fragment
            if len(candidate) <= chunk_limit:
                current = candidate
                continue

            if current:
                chunks.append(current)
            current = fragment

        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def _merge_wav_chunks(chunks: list[bytes]) -> bytes:
        if not chunks:
            raise AivisSpeechError("No synthesized audio chunks were returned")

        wav_format: tuple[int, int, int, str, str] | None = None
        frames: list[bytes] = []

        for index, chunk in enumerate(chunks, start=1):
            try:
                with wave.open(BytesIO(chunk), "rb") as reader:
                    current_format = (
                        reader.getnchannels(),
                        reader.getsampwidth(),
                        reader.getframerate(),
                        reader.getcomptype(),
                        reader.getcompname(),
                    )
                    if wav_format is None:
                        wav_format = current_format
                    elif current_format[:4] != wav_format[:4]:
                        raise AivisSpeechError(
                            f"Synthesized WAV format mismatch at chunk {index}"
                        )
                    frames.append(reader.readframes(reader.getnframes()))
            except (EOFError, wave.Error) as exc:
                raise AivisSpeechError(
                    f"Invalid WAV data returned for chunk {index}: {exc}"
                ) from exc

        assert wav_format is not None
        output = BytesIO()
        with wave.open(output, "wb") as writer:
            writer.setnchannels(wav_format[0])
            writer.setsampwidth(wav_format[1])
            writer.setframerate(wav_format[2])
            writer.setcomptype(wav_format[3], wav_format[4])
            writer.writeframes(b"".join(frames))
        return output.getvalue()

    async def _synthesize_chunks(
        self, text: str, speaker: str
    ) -> list[tuple[bytes, dict[str, Any]]]:
        """テキストをチャンク合成し、(WAV, audio_query) の組を順に返す"""
        chunks = self._split_synthesis_text(text)
        if not chunks:
            raise AivisSpeechError("Text is required")
        if not speaker.strip():
            raise AivisSpeechError("Speaker is required")

        # audio_query と synthesis は CPU モードやモデル初期化時に数分かかる
        # ケースがあるため、共通の長いタイムアウトを設定する。
        # 値は AIVIS_SYNTHESIS_TIMEOUT で調整可能。
        connect_timeout = 10.0
        operation_timeout = httpx.Timeout(
            settings.aivis_synthesis_timeout, connect=connect_timeout
        )
        base = await self.resolve_base_url()
        results: list[tuple[bytes, dict[str, Any]]] = []
        total_chunks = len(chunks)

        async with async_client(timeout=operation_timeout) as client:
            for index, chunk in enumerate(chunks, start=1):
                try:
                    query_resp = await client.post(
                        f"{base}/audio_query",
                        params={"speaker": speaker, "text": chunk},
                    )
                    query_resp.raise_for_status()
                    audio_query = query_resp.json()

                    synth_resp = await client.post(
                        f"{base}/synthesis",
                        params={"speaker": speaker},
                        json=audio_query,
                    )
                    synth_resp.raise_for_status()
                    content_type = synth_resp.headers.get(
                        "content-type", "audio/wav"
                    ).split(";", maxsplit=1)[0]
                    if content_type.lower() not in {
                        "audio/wav",
                        "audio/wave",
                        "audio/x-wav",
                        "audio/vnd.wave",
                    }:
                        raise AivisSpeechError(
                            f"Unexpected audio format for chunk {index}: {content_type}"
                        )
                    results.append((synth_resp.content, audio_query))
                except httpx.TimeoutException as exc:
                    raise AivisSpeechError(
                        f"Speech synthesis chunk {index}/{total_chunks} timed out. "
                        "On CPU mode, synthesis can take several minutes; increase "
                        "AIVIS_SYNTHESIS_TIMEOUT if needed."
                    ) from exc
                except httpx.HTTPStatusError as exc:
                    raise AivisSpeechError(
                        f"AivisSpeech engine returned an error for chunk "
                        f"{index}/{total_chunks}: {exc.response.status_code}"
                    ) from exc
                except httpx.HTTPError as exc:
                    raise AivisSpeechError(
                        f"Failed to reach AivisSpeech engine for chunk "
                        f"{index}/{total_chunks}: {exc}"
                    ) from exc

        return results

    async def synthesize(self, text: str, speaker: str) -> tuple[bytes, str]:
        results = await self._synthesize_chunks(text, speaker)
        return self._merge_wav_chunks([wav for wav, _ in results]), "audio/wav"

    @staticmethod
    def _wav_duration_sec(wav_bytes: bytes) -> float:
        try:
            with wave.open(BytesIO(wav_bytes), "rb") as reader:
                framerate = reader.getframerate()
                if framerate <= 0:
                    return 0.0
                return reader.getnframes() / framerate
        except (EOFError, wave.Error) as exc:
            raise AivisSpeechError(f"Invalid WAV data: {exc}") from exc

    @staticmethod
    def _chunk_viseme_events(
        audio_query: dict[str, Any],
    ) -> tuple[list[VisemeEvent], float]:
        """audio_query のモーラ長から viseme イベント列と予測総時間を求める。

        時刻はチャンク先頭からの秒(speedScale 反映済み)。イベントの t0 は
        モーラ開始(子音込み)、t1 は母音終了で、立ち上がりの補間は
        クライアント側に任せる。N / cl / pau と pause_mora は時間だけ進める。
        """
        speed = float(audio_query.get("speedScale") or 1.0)
        if speed <= 0:
            speed = 1.0
        cursor = float(audio_query.get("prePhonemeLength") or 0.0) / speed
        events: list[VisemeEvent] = []
        for phrase in audio_query.get("accent_phrases") or []:
            moras = list(phrase.get("moras") or [])
            pause_mora = phrase.get("pause_mora")
            if pause_mora:
                moras.append(pause_mora)
            for mora in moras:
                consonant = float(mora.get("consonant_length") or 0.0) / speed
                vowel_length = float(mora.get("vowel_length") or 0.0) / speed
                start = cursor
                cursor += consonant + vowel_length
                vowel = str(mora.get("vowel") or "")
                viseme = _VOWEL_TO_VISEME.get(vowel.lower())
                if viseme is None or cursor <= start:
                    continue
                weight = _DEVOICED_VISEME_WEIGHT if vowel.isupper() else 1.0
                events.append(VisemeEvent(t0=start, t1=cursor, viseme=viseme, w=weight))
        cursor += float(audio_query.get("postPhonemeLength") or 0.0) / speed
        return events, cursor

    async def synthesize_timed(self, text: str, speaker: str) -> TimedSynthesis:
        """合成音声と口パク用 viseme タイムラインを返す。

        チャンク境界のオフセットは実 WAV 長の累積で取り、チャンク内の時刻は
        実 WAV 長と予測長の比で補正する(_merge_wav_chunks はフレームを
        単純連結するだけなので、これで結合後の音声と時刻が一致する)。
        """
        results = await self._synthesize_chunks(text, speaker)
        timeline: list[VisemeEvent] = []
        offset = 0.0
        for wav, audio_query in results:
            actual = self._wav_duration_sec(wav)
            events, predicted = self._chunk_viseme_events(audio_query)
            ratio = actual / predicted if predicted > 0 else 1.0
            timeline.extend(
                VisemeEvent(
                    t0=round(event.t0 * ratio + offset, 3),
                    t1=round(event.t1 * ratio + offset, 3),
                    viseme=event.viseme,
                    w=event.w,
                )
                for event in events
            )
            offset += actual
        audio = self._merge_wav_chunks([wav for wav, _ in results])
        return TimedSynthesis(
            audio=audio,
            content_type="audio/wav",
            duration_sec=round(offset, 3),
            timeline=timeline,
        )

    async def get_status(self) -> dict[str, Any]:
        tracked_running = self._is_running(self._engine_process)

        port = await self.resolve_engine_port()
        base_url = self._build_base_url(port)
        host = urlparse(base_url).hostname or "127.0.0.1"

        # netstat-based PID lookup only works on Windows. On Linux the engine
        # runs inside the `aivis` Docker container, so fall back to a plain
        # TCP health check against the published port instead.
        if sys.platform == "win32":
            pid_on_port = self._find_pid_on_port(port)
            port_open = pid_on_port is not None
        else:
            pid_on_port = None
            port_open = self._is_port_open(host, port)

        process_status = "running" if tracked_running or port_open else "stopped"
        endpoint = f"{base_url}/version"

        engine_http = "unreachable"
        engine_version: str | None = None
        engine_brand: str | None = None
        try:
            async with async_client(timeout=httpx.Timeout(2.5)) as client:
                response = await client.get(endpoint)
                if response.status_code < 400:
                    engine_http = "ok"
                    try:
                        engine_version = str(response.json())
                    except ValueError:
                        engine_version = None
                    engine_brand = await self._fetch_engine_brand(client, base_url)
                else:
                    engine_http = f"error:{response.status_code}"
        except Exception:
            engine_http = "unreachable"

        if sys.platform == "win32":
            platform_name = "windows"
        elif sys.platform.startswith("linux"):
            platform_name = "linux"
        else:
            platform_name = "other"

        return {
            "process": process_status,
            "pid": self._engine_process.pid if tracked_running else pid_on_port,
            "managed": tracked_running,
            "engine_http": engine_http,
            "engine_base_url": base_url,
            "engine_port": port,
            "default_engine_port": self._default_engine_port(),
            "engine_version": engine_version,
            # brand_name from /engine_manifest. "AivisSpeech" means the bundled
            # engine; anything else is a compatible third-party engine for which
            # the bundled engine's setup steps do not apply.
            "engine_brand": engine_brand,
            "aivis_engine_brand": AIVIS_ENGINE_BRAND,
            "default_engine_download_url": settings.aivis_engine_download_url,
            "default_model_url": settings.aivis_default_model_url,
            "default_model_dir": str(self._default_model_dir()),
            "platform": platform_name,
            "docker_hint": "docker compose up -d aivis",
        }


aivisspeech_service = AivisSpeechService()
