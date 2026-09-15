import argparse
import signal
import socket
import webbrowser
from pathlib import Path

import uvicorn

from adapters.git import get_repo_info, get_repo_root


def _kill_existing(port: int) -> None:
    import os
    import subprocess

    result = subprocess.run(
        ["/usr/sbin/lsof", "-ti", f":{port}"],
        capture_output=True,
        text=True,
        check=False,
    )
    pids = result.stdout.strip().split()
    for pid in pids:
        if not pid:
            continue
        try:
            os.kill(int(pid), signal.SIGTERM)
        except (ProcessLookupError, ValueError):
            pass
    if pids:
        import time

        time.sleep(0.5)


def _cmd_reset() -> None:
    import shutil

    from config import CONFIG_PATH

    data_dir = CONFIG_PATH.parent
    if data_dir.exists():
        shutil.rmtree(data_dir)
        print(f"Removed {data_dir}")
    else:
        print("Nothing to reset.")


def _cmd_serve(args: argparse.Namespace) -> None:
    import os

    repo_path = str(Path(args.repo_path).resolve())
    root = get_repo_root(repo_path)

    if root:
        info = get_repo_info(repo_path)
        branch = args.branch or info.current_branch
        base = args.base or info.default_branch
        os.environ["DIFFR_REPO_PATH"] = repo_path
        os.environ["DIFFR_BRANCH"] = branch
        os.environ["DIFFR_BASE"] = base
    else:
        for key in ("DIFFR_REPO_PATH", "DIFFR_BRANCH", "DIFFR_BASE"):
            os.environ.pop(key, None)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", args.port))
        sock.close()
    except OSError:
        _kill_existing(args.port)

    if not args.no_open:
        import threading

        def _open_when_ready():
            import time
            import urllib.request

            url = f"http://127.0.0.1:{args.port}"
            for _ in range(30):
                try:
                    urllib.request.urlopen(url, timeout=1)
                    break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.2)
            webbrowser.open(url)

        threading.Thread(target=_open_when_ready, daemon=True).start()

    uvicorn.run(
        "main:create_app",
        factory=True,
        host="127.0.0.1",
        port=args.port,
        log_level="info",
    )


def main():
    parser = argparse.ArgumentParser(
        prog="diffr",
        description="Local code review tool",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("reset", help="Remove all settings and start fresh")

    parser.add_argument(
        "repo_path", nargs="?", default=".", help="Path to repo or worktree"
    )
    parser.add_argument("branch", nargs="?", help="Branch to review (default: current)")
    parser.add_argument(
        "--base", default=None, help="Base branch (default: auto-detect)"
    )
    parser.add_argument("--port", type=int, default=8787, help="Port (default: 8787)")
    parser.add_argument("--no-open", action="store_true", help="Don't open browser")

    args = parser.parse_args()

    if args.command == "reset":
        _cmd_reset()
        return

    _cmd_serve(args)


if __name__ == "__main__":
    main()
