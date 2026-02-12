"""NeuralDrift server CLI — run with: python3 -m neuraldrift.server [--daemon|--stop|--status]"""

import argparse
import logging
import os
import signal
import sys

from .daemon import BrainServer, PID_PATH, SOCK_PATH


def _read_pid() -> int | None:
    """Read PID from pidfile. Returns None if missing or stale."""
    if not PID_PATH.exists():
        return None
    try:
        pid = int(PID_PATH.read_text().strip())
        # Check if process is alive
        os.kill(pid, 0)
        return pid
    except (ValueError, ProcessLookupError, PermissionError):
        # Stale pidfile — clean up
        PID_PATH.unlink(missing_ok=True)
        return None


def cmd_status():
    """Print server status and exit."""
    pid = _read_pid()
    if pid:
        print(f"NeuralDrift server is running (PID {pid})")
        print(f"  Socket: {SOCK_PATH}")
        print(f"  PID file: {PID_PATH}")
        sys.exit(0)
    else:
        print("NeuralDrift server is not running.")
        sys.exit(1)


def cmd_stop():
    """Send SIGTERM to running daemon."""
    pid = _read_pid()
    if not pid:
        print("NeuralDrift server is not running.")
        sys.exit(1)
    print(f"Stopping NeuralDrift server (PID {pid})...")
    os.kill(pid, signal.SIGTERM)
    print("Stop signal sent.")


def cmd_run(daemon: bool):
    """Run the server (foreground or background)."""
    pid = _read_pid()
    if pid:
        print(f"NeuralDrift server already running (PID {pid}).")
        sys.exit(1)

    if daemon:
        # Fork to background
        child_pid = os.fork()
        if child_pid > 0:
            # Parent
            print(f"NeuralDrift server started in background (PID {child_pid})")
            sys.exit(0)
        # Child — detach
        os.setsid()
        # Redirect stdio to /dev/null
        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, 0)
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        os.close(devnull)

    import asyncio
    server = BrainServer()
    asyncio.run(server.run_forever())


def main():
    parser = argparse.ArgumentParser(
        prog="neuraldrift.server",
        description="NeuralDrift — Brain streaming service",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--daemon", "-d", action="store_true", help="Run as background daemon")
    group.add_argument("--stop", action="store_true", help="Stop running daemon")
    group.add_argument("--status", action="store_true", help="Check daemon status")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.status:
        cmd_status()
    elif args.stop:
        cmd_stop()
    else:
        cmd_run(daemon=args.daemon)


if __name__ == "__main__":
    main()
