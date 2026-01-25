import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_WORKFLOW = BASE_DIR / "workflows" / "qwen_image_edit_template.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch ComfyUI gateway with specific workflow")
    parser.add_argument(
        "--workflow",
        type=Path,
        default=None,
        help="Path to the workflow JSON (defaults to qwen_image_edit_template.json)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port for uvicorn (defaults to GATEWAY_PORT env or 8000)",
    )
    return parser.parse_args()


def start_uvicorn(port: int, env: dict) -> subprocess.Popen:
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "gateway.app:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(port),
    ]
    return subprocess.Popen(cmd, cwd=str(BASE_DIR), env=env)


def main() -> None:
    load_dotenv()
    args = parse_args()

    workflow_path = args.workflow or os.environ.get("COMFYUI_WORKFLOW_PATH")
    if not workflow_path:
        workflow_path = DEFAULT_WORKFLOW
    else:
        workflow_path = (BASE_DIR / workflow_path).resolve() if not Path(workflow_path).is_absolute() else Path(workflow_path)

    port = args.port or int(os.environ.get("GATEWAY_PORT", "8000"))

    env = os.environ.copy()
    env["COMFYUI_WORKFLOW_PATH"] = str(workflow_path)
    env["GATEWAY_PORT"] = str(port)

    process = start_uvicorn(port, env)
    try:
        process.wait()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()