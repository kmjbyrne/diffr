import argparse
import signal
import socket
import webbrowser
from pathlib import Path

import uvicorn

from adapters.git import get_repo_info, get_repo_root

PID_FILE = Path.home() / ".local" / "share" / "diffr" / "diffr.pid"


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


def _write_pid() -> None:
    import os

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))


def _remove_pid() -> None:
    PID_FILE.unlink(missing_ok=True)


def _cmd_reset() -> None:
    import shutil

    from config import CONFIG_PATH

    data_dir = CONFIG_PATH.parent
    if data_dir.exists():
        shutil.rmtree(data_dir)
        print(f"Removed {data_dir}")
    else:
        print("Nothing to reset.")


def _cmd_stop() -> None:
    import os

    if not PID_FILE.exists():
        print("diffr is not running (no PID file).")
        return
    pid = int(PID_FILE.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Stopped diffr (pid {pid}).")
    except ProcessLookupError:
        print(f"Process {pid} not found (stale PID file).")
    _remove_pid()


def _cmd_status() -> None:
    import os

    if not PID_FILE.exists():
        print("diffr is not running.")
        return
    pid = int(PID_FILE.read_text().strip())
    try:
        os.kill(pid, 0)
        print(f"diffr is running (pid {pid}).")
    except ProcessLookupError:
        print(f"diffr is not running (stale PID file, pid {pid}).")
        _remove_pid()


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

    if args.background:
        _daemonize(args)
        return

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

    _write_pid()
    try:
        uvicorn.run(
            "main:create_app",
            factory=True,
            host="127.0.0.1",
            port=args.port,
            log_level="info",
        )
    finally:
        _remove_pid()


def _daemonize(args: argparse.Namespace) -> None:
    import os
    import sys

    pid = os.fork()
    if pid > 0:
        print(f"diffr running in background (pid {pid}) on port {args.port}")
        if not args.no_open:
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
        sys.exit(0)

    os.setsid()
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    os.close(devnull)

    _write_pid()
    try:
        uvicorn.run(
            "main:create_app",
            factory=True,
            host="127.0.0.1",
            port=args.port,
            log_level="error",
        )
    finally:
        _remove_pid()


def main():
    parser = argparse.ArgumentParser(
        prog="diffr",
        description="Local code review tool",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("reset", help="Remove all settings and start fresh")
    sub.add_parser("stop", help="Stop the background diffr server")
    sub.add_parser("status", help="Check if diffr is running")

    parser.add_argument(
        "repo_path", nargs="?", default=".", help="Path to repo or worktree"
    )
    parser.add_argument("branch", nargs="?", help="Branch to review (default: current)")
    parser.add_argument(
        "--base", default=None, help="Base branch (default: auto-detect)"
    )
    parser.add_argument("--port", type=int, default=8787, help="Port (default: 8787)")
    parser.add_argument("--no-open", action="store_true", help="Don't open browser")
    parser.add_argument(
        "-d", "--background", action="store_true", help="Run in background (headless)"
    )

    args = parser.parse_args()

    if args.command == "reset":
        _cmd_reset()
        return
    if args.command == "stop":
        _cmd_stop()
        return
    if args.command == "status":
        _cmd_status()
        return

    _cmd_serve(args)


if __name__ == "__main__":
    main()
