from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.parse
import webbrowser
from pathlib import Path


if getattr(sys, "frozen", False):
    SCRIPT_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    SCRIPT_DIR = Path(__file__).resolve().parent
SERVER_SCRIPT = SCRIPT_DIR / "server.py"
SELECT_SCRIPT = SCRIPT_DIR / "select_markdown.py"
PYTHON_BIN = Path(os.environ.get("PYTHON_BIN", sys.executable or "python3"))
DEFAULT_DISPLAY_HOST = "localhost" if sys.platform == "win32" else "read-md.localhost"
DISPLAY_HOST = os.environ.get("MD_READER_HOST", DEFAULT_DISPLAY_HOST)
BIND_HOST = os.environ.get("MD_READER_BIND_HOST", "127.0.0.1")
PORT = int(os.environ.get("MD_READER_PORT", "8765"))
LOG_PATH = Path(os.environ.get("MD_READER_LOG", str(Path.cwd() / "md_reader.log")))


def port_is_listening(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.7)
        try:
            sock.connect((host, port))
            return True
        except OSError:
            return False


def pick_document(initial: str | None) -> Path | None:
    if initial:
        candidate = Path(initial).expanduser().resolve()
        if candidate.exists() and candidate.is_file():
            return candidate

    try:
        result = subprocess.run(
            [str(PYTHON_BIN), str(SELECT_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except Exception:
        return None

    selected = result.stdout.strip()
    if not selected:
        return None

    candidate = Path(selected).expanduser().resolve()
    return candidate if candidate.exists() and candidate.is_file() else None


def start_server(document: Path) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("ab") as log_file:
        if getattr(sys, "frozen", False):
            command = [
                str(Path(sys.executable).resolve()),
                "--server",
                "--host",
                BIND_HOST,
                "--port",
                str(PORT),
                "--file",
                str(document),
            ]
            cwd = str(Path(sys.executable).resolve().parent)
        else:
            command = [
                str(PYTHON_BIN),
                str(SERVER_SCRIPT),
                "--host",
                BIND_HOST,
                "--port",
                str(PORT),
                "--file",
                str(document),
            ]
            cwd = str(SCRIPT_DIR.parent)

        subprocess.Popen(command, stdout=log_file, stderr=log_file, cwd=cwd)


def open_reader(document: Path) -> None:
    encoded = urllib.parse.quote(str(document))
    url = f"http://{DISPLAY_HOST}:{PORT}/?path={encoded}"
    webbrowser.open(url)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch Paper Reader")
    parser.add_argument("file", nargs="?", help="Markdown file to open")
    parser.add_argument("--server", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--host", default=BIND_HOST, help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=PORT, help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.server:
        from server import run_server

        run_server(args.file, args.host, args.port)
        return 0

    document = pick_document(args.file)
    if not document:
        return 0

    if not port_is_listening(BIND_HOST, PORT):
        start_server(document)
        time.sleep(1.0)

    open_reader(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
