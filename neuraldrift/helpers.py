"""
Common helper functions for tools and scripts.
Usage:
    from neuraldrift import run_cmd, timestamp, save_json, load_json, ensure_dir
"""

import subprocess
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from .output import C, info, warning, error, success, debug


def run_cmd(cmd, timeout=120, shell=True, capture=True):
    """Run a shell command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, shell=shell, capture_output=capture,
            text=True, timeout=timeout
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


def timestamp(fmt="%Y-%m-%d_%H-%M-%S"):
    """Return current timestamp string."""
    return datetime.now().strftime(fmt)


def datestamp():
    """Return current date string YYYY-MM-DD."""
    return datetime.now().strftime("%Y-%m-%d")


def save_json(data, filepath):
    """Save data to JSON file atomically (temp + rename). Safe against crashes."""
    import tempfile
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(filepath.parent),
        prefix=f".{filepath.stem}_",
        suffix=".tmp"
    )
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(filepath))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_json(filepath):
    """Load JSON file with backup recovery on corruption."""
    filepath = Path(filepath)
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        # Try backup
        backup = filepath.with_suffix(filepath.suffix + ".bak")
        if backup.exists():
            warning(f"Corrupted {filepath.name}, recovering from backup")
            with open(backup, 'r') as f:
                data = json.load(f)
            save_json(data, str(filepath))
            return data
        raise


def ensure_dir(path):
    """Create directory if it doesn't exist, return Path object."""
    p = Path(path).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def file_size_human(size_bytes):
    """Convert bytes to human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def memory_path():
    """Return the path to NeuralDrift data directory."""
    return Path.home() / ".neuraldrift"


def save_learning(topic, content):
    """Append a learning to the learnings file."""
    learnings_file = memory_path() / "learnings.md"
    learnings_file.parent.mkdir(parents=True, exist_ok=True)
    with open(learnings_file, 'a') as f:
        f.write(f"\n### {topic} — {datestamp()}\n{content}\n")


# ═══════════════════════════════════════════════════════════
#  SpinGuard — Watchdog with auto-terminate
# ═══════════════════════════════════════════════════════════

class SpinGuard:
    """
    Watchdog that gives a task N spins to produce a result.
    After each spin it checks; if still unanswered after max_spins, auto-terminates.

    Usage:
        def my_check():
            return some_result_or_None  # None = still pending

        guard = SpinGuard(checker=my_check, max_spins=5, interval=2.0)
        result = guard.run()  # blocks, returns result or None if timed out

        # Or non-blocking:
        guard.start()          # launches in background thread
        guard.is_alive()       # check if still spinning
        guard.result            # None until resolved or terminated
        guard.kill()            # force-terminate early

        # With cleanup callback:
        guard = SpinGuard(checker=fn, max_spins=10, on_terminate=cleanup_fn)
    """

    def __init__(self, checker, max_spins=5, interval=2.0,
                 on_terminate=None, on_success=None, label="task", silent=False):
        """
        Args:
            checker:      callable() -> result or None (None = still pending)
            max_spins:    max check cycles before auto-terminate
            interval:     seconds between spins
            on_terminate: callable() run on auto-termination
            on_success:   callable(result) run when checker returns non-None
            label:        display name for status messages
            silent:       suppress terminal output
        """
        self.checker = checker
        self.max_spins = max_spins
        self.interval = interval
        self.on_terminate = on_terminate
        self.on_success = on_success
        self.label = label
        self.silent = silent

        self.result = None
        self.spins_used = 0
        self.terminated = False
        self.succeeded = False
        self._killed = threading.Event()
        self._thread = None

    def _spin_symbol(self, n):
        """Rotating spinner character."""
        frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        return frames[n % len(frames)]

    def _log(self, msg):
        if not self.silent:
            print(msg)

    def _do_spins(self):
        """Core spin loop."""
        for i in range(1, self.max_spins + 1):
            if self._killed.is_set():
                self._log(f"  {C.YELLOW}{self._spin_symbol(i)} [{self.label}] killed at spin {i}/{self.max_spins}{C.RESET}")
                self.terminated = True
                return None

            self.spins_used = i

            # Check
            try:
                result = self.checker()
            except Exception as e:
                self._log(f"  {C.RED}[-] [{self.label}] checker error at spin {i}: {e}{C.RESET}")
                result = None

            if result is not None:
                self.result = result
                self.succeeded = True
                self._log(f"  {C.GREEN}[+] [{self.label}] resolved at spin {i}/{self.max_spins}{C.RESET}")
                if self.on_success:
                    try:
                        self.on_success(result)
                    except Exception:
                        pass
                return result

            # Still pending
            remaining = self.max_spins - i
            self._log(f"  {C.GRAY}{self._spin_symbol(i)} [{self.label}] spin {i}/{self.max_spins} — pending ({remaining} left){C.RESET}")

            if i < self.max_spins:
                self._killed.wait(self.interval)

        # Exhausted all spins — auto-terminate
        self.terminated = True
        self._log(f"  {C.RED}[X] [{self.label}] auto-terminated after {self.max_spins} spins{C.RESET}")
        if self.on_terminate:
            try:
                self.on_terminate()
            except Exception:
                pass
        return None

    def run(self):
        """Blocking: spin until resolved or terminated. Returns result or None."""
        return self._do_spins()

    def start(self):
        """Non-blocking: launch spins in background thread."""
        self._thread = threading.Thread(target=self._do_spins, daemon=True)
        self._thread.start()
        return self

    def is_alive(self):
        """Check if background spin is still running."""
        return self._thread is not None and self._thread.is_alive()

    def kill(self):
        """Force-terminate the spin guard early."""
        self._killed.set()
        if self._thread:
            self._thread.join(timeout=self.interval + 1)

    def status(self):
        """Return a status dict."""
        return {
            'label': self.label,
            'spins_used': self.spins_used,
            'max_spins': self.max_spins,
            'succeeded': self.succeeded,
            'terminated': self.terminated,
            'alive': self.is_alive(),
            'result': self.result,
        }

    def __repr__(self):
        state = "alive" if self.is_alive() else ("done" if self.succeeded else ("killed" if self.terminated else "idle"))
        return f"<SpinGuard '{self.label}' {self.spins_used}/{self.max_spins} [{state}]>"


class SpinSwarm:
    """
    Run multiple SpinGuards in parallel, collect results.

    Usage:
        swarm = SpinSwarm([
            SpinGuard(check_dns, max_spins=5, label="DNS"),
            SpinGuard(check_port, max_spins=3, label="Port 80"),
            SpinGuard(check_api, max_spins=8, label="API"),
        ])
        results = swarm.run()  # blocks until all finish
        swarm.summary()        # print status table
    """

    def __init__(self, guards):
        self.guards = guards

    def run(self):
        """Launch all guards in parallel, wait for all to finish."""
        for g in self.guards:
            g.start()
        for g in self.guards:
            if g._thread:
                g._thread.join()
        return {g.label: g.result for g in self.guards}

    def kill_all(self):
        """Force-kill all guards."""
        for g in self.guards:
            g.kill()

    def summary(self):
        """Print status table of all guards."""
        print(f"\n  {C.CYAN}{C.BOLD}{'Guard':<20} {'Spins':>8} {'Status':>12} {'Result'}{C.RESET}")
        print(f"  {C.GRAY}{'─'*60}{C.RESET}")
        for g in self.guards:
            if g.succeeded:
                status = f"{C.GREEN}resolved{C.RESET}"
            elif g.terminated:
                status = f"{C.RED}terminated{C.RESET}"
            else:
                status = f"{C.YELLOW}pending{C.RESET}"
            result_str = str(g.result)[:30] if g.result else "—"
            print(f"  {g.label:<20} {g.spins_used:>3}/{g.max_spins:<3} {status:>24} {result_str}")

    def alive_count(self):
        return sum(1 for g in self.guards if g.is_alive())

    def results(self):
        return {g.label: g.status() for g in self.guards}
