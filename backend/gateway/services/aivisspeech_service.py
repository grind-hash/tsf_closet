from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import IO, Any
from urllib.parse import urlparse

import httpx

from ..settings.app_settings import BASE_DIR, settings


class AivisSpeechError(Exception):
    pass


class AivisSpeechService:
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

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream("GET", url) as response:
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

    def start_engine(self, engine_dir: str, use_gpu: bool = False) -> dict[str, Any]:
        self._ensure_windows()

        if self._is_running(self._engine_process):
            return {
                "status": "already_running",
                "pid": self._engine_process.pid,
            }

        pid_on_port = self._find_pid_on_port(10101)
        if pid_on_port is not None:
            return {
                "status": "already_running_external",
                "pid": pid_on_port,
            }

        root = self._expand_path(engine_dir)
        run_exe = self.find_run_exe(root)

        # run.exe does not always create its model directory on first launch,
        # so ensure it exists before starting the engine.
        self._default_model_dir().mkdir(parents=True, exist_ok=True)

        args = [str(run_exe), "--host", "127.0.0.1"]
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

        # Detect immediate failures (e.g. port in use, missing runtime).
        try:
            self._engine_process.wait(timeout=4.0)
            exit_code = self._engine_process.returncode
            self._engine_process = None
            self._close_engine_log()
            tail = self._read_log_tail(log_path)
            raise AivisSpeechError(
                f"run.exe exited immediately (code {exit_code}). Log tail: {tail}"
            )
        except subprocess.TimeoutExpired:
            pass

        return {
            "status": "started",
            "pid": self._engine_process.pid,
            "run_exe": str(run_exe),
            "log_path": str(log_path),
        }

    def _close_engine_log(self) -> None:
        if self._engine_log_file is not None:
            try:
                self._engine_log_file.close()
            except OSError:
                pass
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

    async def stop_engine(self) -> dict[str, Any]:
        self._ensure_windows()

        if not self._is_running(self._engine_process):
            self._engine_process = None
            self._close_engine_log()
            pid_on_port = self._find_pid_on_port(10101)
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
        return self.start_engine(engine_dir=engine_dir, use_gpu=use_gpu)

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
        endpoint = f"{settings.aivis_engine_base_url}/aivm_models/install"

        async with httpx.AsyncClient(timeout=timeout) as client:
            with file_path.open("rb") as f:
                response = await client.post(
                    endpoint, files={"file": (file_path.name, f)}
                )
            if response.status_code >= 400:
                raise AivisSpeechError(
                    f"Model install failed ({response.status_code}): {response.text}"
                )

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
        endpoint = f"{settings.aivis_engine_base_url}/speakers"
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(endpoint)
            response.raise_for_status()
            data = response.json()

        if not isinstance(data, list):
            raise AivisSpeechError("Unexpected speakers response format")
        return data

    async def synthesize(self, text: str, speaker: str) -> tuple[bytes, str]:
        if not text.strip():
            raise AivisSpeechError("Text is required")
        if not speaker.strip():
            raise AivisSpeechError("Speaker is required")

        # audio_query はテキスト解析のみで軽量なため接続確認程度の短いタイムアウトに
        # とどめ、synthesis は CPU モードで数分かかるケースがあるため長めの
        # タイムアウトを設定する。値は AIVIS_SYNTHESIS_TIMEOUT で調整可能。
        connect_timeout = 10.0
        query_timeout = httpx.Timeout(30.0, connect=connect_timeout)
        synth_timeout = httpx.Timeout(
            settings.aivis_synthesis_timeout, connect=connect_timeout
        )
        base = settings.aivis_engine_base_url

        try:
            async with httpx.AsyncClient(timeout=query_timeout) as client:
                query_resp = await client.post(
                    f"{base}/audio_query",
                    params={"speaker": speaker, "text": text},
                )
                query_resp.raise_for_status()
                audio_query = query_resp.json()

            async with httpx.AsyncClient(timeout=synth_timeout) as client:
                synth_resp = await client.post(
                    f"{base}/synthesis",
                    params={"speaker": speaker},
                    json=audio_query,
                )
                synth_resp.raise_for_status()
        except httpx.TimeoutException as exc:
            raise AivisSpeechError(
                "Speech synthesis timed out. On CPU mode, longer text can take "
                "several minutes; try shorter text or increase "
                "AIVIS_SYNTHESIS_TIMEOUT."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise AivisSpeechError(
                f"AivisSpeech engine returned an error: {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise AivisSpeechError(
                f"Failed to reach AivisSpeech engine: {exc}"
            ) from exc

        content_type = synth_resp.headers.get("content-type", "audio/wav")
        return synth_resp.content, content_type

    async def get_status(self) -> dict[str, Any]:
        tracked_running = self._is_running(self._engine_process)

        # netstat-based PID lookup only works on Windows. On Linux the engine
        # runs inside the `aivis` Docker container, so fall back to a plain
        # TCP health check against the published port instead.
        if sys.platform == "win32":
            pid_on_port = self._find_pid_on_port(10101)
            port_open = pid_on_port is not None
        else:
            pid_on_port = None
            port_open = self._is_port_open("127.0.0.1", 10101)

        process_status = "running" if tracked_running or port_open else "stopped"
        endpoint = f"{settings.aivis_engine_base_url}/version"

        engine_http = "unreachable"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(2.5)) as client:
                response = await client.get(endpoint)
                if response.status_code < 400:
                    engine_http = "ok"
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
            "engine_base_url": settings.aivis_engine_base_url,
            "default_engine_download_url": settings.aivis_engine_download_url,
            "default_model_url": settings.aivis_default_model_url,
            "default_model_dir": str(self._default_model_dir()),
            "platform": platform_name,
            "docker_hint": "docker compose up -d aivis",
        }


aivisspeech_service = AivisSpeechService()
