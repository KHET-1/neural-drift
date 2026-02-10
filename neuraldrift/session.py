"""
session.py — Session checkpoint, crash recovery, and resume protocol.
Handles laptop shutdown, internet loss, mid-plan interrupts.

The system maintains a session manifest that tracks:
- Current plan with per-objective status
- Active agents and their last known state
- Checkpoint timestamps for staleness detection
- Integrity hashes for corruption detection
- Dirty flags for incomplete operations

Resume Protocol:
    RESUME   — state is fresh, consistent, and can continue from last checkpoint
    PARTIAL  — some objectives completed, others need restart (e.g. power loss mid-plan)
    RESTART  — state is stale, corrupted, or so old it's meaningless to continue

Usage:
    from neuraldrift.session import Session

    session = Session()
    verdict = session.resume_check()     # → "RESUME" | "PARTIAL" | "RESTART"
    session.plan_start("build auth system", ["design", "implement", "test"])
    session.checkpoint("design", status="completed", data={"schema": ...})
    session.checkpoint("implement", status="in_progress", data={"files": [...]})
    # --- CRASH HAPPENS ---
    # Next startup:
    session = Session()
    verdict = session.resume_check()     # → "PARTIAL"
    plan = session.get_plan()            # shows design=done, implement=in_progress
"""

import hashlib
import json
import os
import signal
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from .output import C, success, error, warning, info, header

# ═══════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════

SESSION_DIR = Path.home() / ".neuraldrift"
SESSION_FILE = SESSION_DIR / "session_state.json"
BRAIN_DB = SESSION_DIR / "brain_db.json"

# Staleness thresholds
FRESH_THRESHOLD = timedelta(hours=2)     # < 2hrs = fresh, safe to resume
WARM_THRESHOLD = timedelta(hours=12)     # < 12hrs = warm, partial resume
# > 12hrs = stale, recommend restart


# ═══════════════════════════════════════
# ATOMIC I/O — the foundation
# ═══════════════════════════════════════

def atomic_save(data, filepath, indent=2):
    """
    Write JSON atomically: temp file → fsync → rename.
    If process dies mid-write, the original file is untouched.
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file in same directory (same filesystem = atomic rename)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(filepath.parent),
        prefix=f".{filepath.stem}_",
        suffix=".tmp"
    )
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=indent, default=str)
            f.flush()
            os.fsync(f.fileno())
        # Atomic rename (POSIX guarantee on same filesystem)
        os.replace(tmp_path, str(filepath))
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def atomic_load(filepath, fallback=None):
    """
    Load JSON with corruption recovery.
    Tries main file, then backup, then returns fallback.
    """
    filepath = Path(filepath)
    backup = filepath.with_suffix(filepath.suffix + ".bak")

    # Try main file
    if filepath.exists():
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            warning(f"Corrupted: {filepath.name} — {e}")
            # Try backup
            if backup.exists():
                try:
                    with open(backup, 'r') as f:
                        data = json.load(f)
                    success(f"Recovered from backup: {backup.name}")
                    # Restore main from backup
                    atomic_save(data, filepath)
                    return data
                except (json.JSONDecodeError, UnicodeDecodeError):
                    error(f"Backup also corrupted: {backup.name}")

    # Try backup alone
    if not filepath.exists() and backup.exists():
        try:
            with open(backup, 'r') as f:
                data = json.load(f)
            success(f"Main file missing, recovered from backup: {backup.name}")
            atomic_save(data, filepath)
            return data
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    return fallback


def rotate_backup(filepath, max_backups=3):
    """
    Create a rolling backup before overwrite.
    Keeps up to max_backups versions: .bak, .bak.1, .bak.2
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return

    # Rotate existing backups
    for i in range(max_backups - 1, 0, -1):
        older = filepath.with_suffix(f"{filepath.suffix}.bak.{i}")
        newer = filepath.with_suffix(f"{filepath.suffix}.bak.{i - 1}") if i > 1 else filepath.with_suffix(f"{filepath.suffix}.bak")
        if newer.exists():
            try:
                os.replace(str(newer), str(older))
            except OSError:
                pass

    # Create new backup from current
    backup = filepath.with_suffix(f"{filepath.suffix}.bak")
    try:
        import shutil
        shutil.copy2(str(filepath), str(backup))
    except OSError:
        pass


def file_hash(filepath):
    """SHA256 of a file's contents, or None if missing/unreadable."""
    try:
        with open(filepath, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()[:16]
    except (OSError, IOError):
        return None


# ═══════════════════════════════════════
# SESSION STATE
# ═══════════════════════════════════════

class Session:
    """
    Persistent session state with checkpoint/resume support.

    Tracks:
      - Active plan (objectives + per-step status)
      - Agent state snapshots
      - Checkpoint timestamps
      - File integrity hashes
      - Dirty operation flags
    """

    def __init__(self):
        self.state = self._load()
        self._register_crash_handler()

    def _load(self):
        """Load session state or create fresh."""
        data = atomic_load(SESSION_FILE)
        if data:
            return data
        return self._fresh_state()

    def _fresh_state(self):
        return {
            "session_id": f"s_{int(time.time())}",
            "created": self._ts(),
            "last_checkpoint": None,
            "plan": None,
            "agents": {},
            "checkpoints": [],
            "integrity": {},
            "dirty_flags": [],
            "crash_log": [],
            "scout_queue": [],
        }

    def _ts(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _save(self):
        """Persist session state atomically."""
        self.state["last_checkpoint"] = self._ts()
        atomic_save(self.state, SESSION_FILE)

    def _register_crash_handler(self):
        """Register signal handlers for graceful crash recovery."""
        def _crash_save(signum, frame):
            self.state["crash_log"].append({
                "signal": signum,
                "time": self._ts(),
                "dirty_flags": list(self.state.get("dirty_flags", [])),
                "plan_status": self._plan_summary() if self.state.get("plan") else None,
            })
            try:
                self._save()
            except Exception:
                pass
            # Re-raise the signal for default handling
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)

        try:
            signal.signal(signal.SIGTERM, _crash_save)
            # SIGINT (Ctrl+C) — save then exit gracefully
            signal.signal(signal.SIGINT, _crash_save)
        except (OSError, ValueError):
            # Can't register signals in non-main thread
            pass

    # ─── Plan Management ────────────────────

    def plan_start(self, name, objectives):
        """
        Begin a new plan with named objectives.

        Args:
            name: Plan description
            objectives: List of objective names (strings)
        """
        self.state["plan"] = {
            "name": name,
            "started": self._ts(),
            "objectives": {
                obj: {"status": "pending", "data": None, "checkpointed": None}
                for obj in objectives
            },
            "completed": False,
        }
        self.state["dirty_flags"] = []
        self._save()
        return self.state["plan"]

    def checkpoint(self, objective, status="in_progress", data=None):
        """
        Save progress on a specific objective.

        Args:
            objective: Name of the objective
            status: "pending" | "in_progress" | "completed" | "failed"
            data: Arbitrary checkpoint data (must be JSON-serializable)
        """
        plan = self.state.get("plan")
        if not plan:
            warning("No active plan — call plan_start() first")
            return

        if objective not in plan["objectives"]:
            plan["objectives"][objective] = {"status": "pending", "data": None, "checkpointed": None}

        plan["objectives"][objective]["status"] = status
        plan["objectives"][objective]["checkpointed"] = self._ts()
        if data is not None:
            plan["objectives"][objective]["data"] = data

        # Track in checkpoint log
        self.state["checkpoints"].append({
            "objective": objective,
            "status": status,
            "time": self._ts(),
        })

        # Update dirty flags
        if status == "in_progress":
            if objective not in self.state["dirty_flags"]:
                self.state["dirty_flags"].append(objective)
        elif status in ("completed", "failed"):
            if objective in self.state["dirty_flags"]:
                self.state["dirty_flags"].remove(objective)

        # Check if plan is fully completed
        statuses = [o["status"] for o in plan["objectives"].values()]
        if all(s in ("completed", "failed") for s in statuses):
            plan["completed"] = True

        self._save()

    def plan_complete(self):
        """Mark entire plan as completed."""
        if self.state.get("plan"):
            self.state["plan"]["completed"] = True
            self.state["dirty_flags"] = []
            self._save()

    def get_plan(self):
        """Return current plan state."""
        return self.state.get("plan")

    def _plan_summary(self):
        """Quick summary of plan status."""
        plan = self.state.get("plan")
        if not plan:
            return None
        return {
            "name": plan["name"],
            "completed": plan["completed"],
            "objectives": {
                name: obj["status"]
                for name, obj in plan["objectives"].items()
            }
        }

    # ─── Agent State Snapshots ──────────────

    def agent_snapshot(self, agent_id, name, task, status="active"):
        """Record agent state for crash recovery."""
        self.state["agents"][str(agent_id)] = {
            "name": name,
            "task": task,
            "status": status,
            "snapshotted": self._ts(),
        }
        self._save()

    def agent_done(self, agent_id, result_summary=None):
        """Mark agent as completed."""
        aid = str(agent_id)
        if aid in self.state["agents"]:
            self.state["agents"][aid]["status"] = "completed"
            self.state["agents"][aid]["result"] = result_summary
            self.state["agents"][aid]["completed_at"] = self._ts()
            self._save()

    def agent_lost(self):
        """Find agents that were active when last session ended (potential crash victims)."""
        return {
            aid: info
            for aid, info in self.state.get("agents", {}).items()
            if info.get("status") == "active"
        }

    # ─── Integrity Checks ──────────────────

    def snapshot_integrity(self):
        """Capture file hashes for later validation."""
        self.state["integrity"] = {
            "brain_db": file_hash(BRAIN_DB),
            "session_state": file_hash(SESSION_FILE),
            "timestamp": self._ts(),
        }
        self._save()

    def verify_integrity(self):
        """
        Check if files match their last known hashes.
        Returns dict of {filename: "ok" | "changed" | "missing" | "no_baseline"}
        """
        results = {}
        saved = self.state.get("integrity", {})

        checks = {
            "brain_db": BRAIN_DB,
        }

        for name, path in checks.items():
            expected = saved.get(name)
            if not expected:
                results[name] = "no_baseline"
            elif not Path(path).exists():
                results[name] = "missing"
            else:
                current = file_hash(path)
                results[name] = "ok" if current == expected else "changed"

        return results

    # ─── Scout Queue (Background Intel) ─────

    def scout_enqueue(self, topic, context, priority="normal"):
        """
        Queue a topic for background intel gathering.

        Args:
            topic: What to research
            context: Why it matters to current work
            priority: "low" | "normal" | "high"
        """
        self.state.setdefault("scout_queue", []).append({
            "topic": topic,
            "context": context,
            "priority": priority,
            "queued": self._ts(),
            "status": "pending",
            "result": None,
        })
        self._save()

    def scout_results(self):
        """Get completed scout findings."""
        return [
            s for s in self.state.get("scout_queue", [])
            if s.get("status") == "completed"
        ]

    def scout_complete(self, index, result, quality="normal"):
        """
        Mark a scout task as complete.

        Args:
            index: Index in scout_queue
            result: The intel gathered
            quality: "meh" | "normal" | "chef_kiss"
        """
        queue = self.state.get("scout_queue", [])
        if 0 <= index < len(queue):
            queue[index]["status"] = "completed"
            queue[index]["result"] = result
            queue[index]["quality"] = quality
            queue[index]["completed"] = self._ts()
            self._save()

    # ─── Resume Protocol ───────────────────

    def resume_check(self, verbose=True):
        """
        Determine whether to RESUME, do PARTIAL recovery, or full RESTART.

        Returns:
            dict with:
                verdict: "RESUME" | "PARTIAL" | "RESTART"
                reason: Human-readable explanation
                plan: Current plan summary (if any)
                lost_agents: Agents that were active at crash time
                integrity: File integrity results
                staleness: How old the last checkpoint is
                recommendations: List of suggested actions
        """
        result = {
            "verdict": "RESTART",
            "reason": "",
            "plan": None,
            "lost_agents": {},
            "integrity": {},
            "staleness": None,
            "crash_log": self.state.get("crash_log", []),
            "recommendations": [],
        }

        last_cp = self.state.get("last_checkpoint")

        # ── Check 1: Do we even have a previous session?
        if not last_cp:
            result["reason"] = "No previous session found"
            result["recommendations"].append("Start fresh — no state to recover")
            if verbose:
                self._print_verdict(result)
            return result

        # ── Check 2: Staleness
        try:
            last_time = datetime.strptime(last_cp, "%Y-%m-%d %H:%M:%S")
            age = datetime.now() - last_time
            result["staleness"] = str(age).split('.')[0]  # HH:MM:SS
        except ValueError:
            age = timedelta(days=999)
            result["staleness"] = "unknown"

        # ── Check 3: File integrity
        result["integrity"] = self.verify_integrity()
        brain_ok = result["integrity"].get("brain_db") in ("ok", "changed", "no_baseline")

        # ── Check 4: Lost agents
        result["lost_agents"] = self.agent_lost()

        # ── Check 5: Plan state
        plan = self._plan_summary()
        result["plan"] = plan

        dirty = self.state.get("dirty_flags", [])

        # ── Decision Logic ──

        if not brain_ok:
            result["verdict"] = "RESTART"
            result["reason"] = f"brain_db integrity: {result['integrity'].get('brain_db', '?')}"
            result["recommendations"].append("Brain DB may be corrupted — check backups (.bak files)")
            result["recommendations"].append("Run: atomic_load() to attempt recovery from backup")

        elif age > WARM_THRESHOLD:
            result["verdict"] = "RESTART"
            result["reason"] = f"Session stale ({result['staleness']} old, threshold: {WARM_THRESHOLD})"
            result["recommendations"].append("Start fresh — too much may have changed")
            if plan and not plan.get("completed"):
                result["recommendations"].append(f"Previous plan '{plan['name']}' was incomplete — review before restarting")

        elif age > FRESH_THRESHOLD:
            # Warm — check if plan has completable parts
            if plan and not plan.get("completed"):
                completed = [k for k, v in plan["objectives"].items() if v == "completed"]
                pending = [k for k, v in plan["objectives"].items() if v != "completed"]
                if completed and pending:
                    result["verdict"] = "PARTIAL"
                    result["reason"] = f"Warm session ({result['staleness']} old) — {len(completed)}/{len(plan['objectives'])} objectives done"
                    result["recommendations"].append(f"Completed: {', '.join(completed)}")
                    result["recommendations"].append(f"Remaining: {', '.join(pending)}")
                    if dirty:
                        result["recommendations"].append(f"DIRTY (interrupted mid-work): {', '.join(dirty)} — restart these")
                else:
                    result["verdict"] = "RESTART"
                    result["reason"] = f"Warm session but no partial progress to salvage"
            else:
                result["verdict"] = "RESTART"
                result["reason"] = f"Warm session ({result['staleness']} old), no active plan"

        else:
            # Fresh — safe to resume
            if plan and not plan.get("completed"):
                completed = [k for k, v in plan["objectives"].items() if v == "completed"]
                in_progress = [k for k, v in plan["objectives"].items() if v == "in_progress"]
                pending = [k for k, v in plan["objectives"].items() if v == "pending"]

                result["verdict"] = "RESUME"
                result["reason"] = f"Fresh session ({result['staleness']} old)"
                if in_progress:
                    result["recommendations"].append(f"In progress (may need re-check): {', '.join(in_progress)}")
                if dirty:
                    result["recommendations"].append(f"DIRTY flags (interrupted): {', '.join(dirty)} — verify before continuing")
                if pending:
                    result["recommendations"].append(f"Next up: {', '.join(pending)}")
            else:
                result["verdict"] = "RESUME"
                result["reason"] = f"Fresh session ({result['staleness']} old), no active plan"

        # Lost agents always warrant a note
        if result["lost_agents"]:
            names = [f"{v['name']} ({v['task']})" for v in result["lost_agents"].values()]
            result["recommendations"].append(f"Lost agents (were active at crash): {', '.join(names)}")

        # Crash log
        if result["crash_log"]:
            last_crash = result["crash_log"][-1]
            result["recommendations"].append(f"Last crash: signal {last_crash.get('signal')} at {last_crash.get('time')}")

        if verbose:
            self._print_verdict(result)

        return result

    def _print_verdict(self, result):
        """Pretty-print the resume verdict."""
        verdict = result["verdict"]
        colors = {"RESUME": C.GREEN, "PARTIAL": C.YELLOW, "RESTART": C.RED}
        icons = {"RESUME": "▶", "PARTIAL": "◐", "RESTART": "↻"}

        header("SESSION RECOVERY CHECK")
        vc = colors.get(verdict, C.WHITE)
        print(f"\n  {vc}{C.BOLD}{icons[verdict]} {verdict}{C.RESET} — {result['reason']}")

        if result.get("plan"):
            plan = result["plan"]
            print(f"\n  {C.CYAN}Plan:{C.RESET} {plan['name']}")
            for obj, status in plan.get("objectives", {}).items():
                sc = C.GREEN if status == "completed" else C.YELLOW if status == "in_progress" else C.GRAY
                icon = "✓" if status == "completed" else "◌" if status == "in_progress" else "·"
                print(f"    {sc}{icon} {obj:<30} [{status}]{C.RESET}")

        if result.get("staleness"):
            print(f"\n  {C.DIM}Last checkpoint: {result['staleness']} ago{C.RESET}")

        integrity = result.get("integrity", {})
        if integrity:
            for name, status in integrity.items():
                ic = C.GREEN if status == "ok" else C.YELLOW if status in ("changed", "no_baseline") else C.RED
                print(f"  {ic}{'✓' if status == 'ok' else '!' if status == 'changed' else '✗'} {name}: {status}{C.RESET}")

        if result.get("recommendations"):
            print(f"\n  {C.WHITE}{C.BOLD}Recommendations:{C.RESET}")
            for rec in result["recommendations"]:
                print(f"    {C.DIM}→ {rec}{C.RESET}")

        print()

    # ─── Utilities ──────────────────────────

    def clear(self):
        """Reset session state."""
        self.state = self._fresh_state()
        self._save()

    def summary(self):
        """Print compact session summary."""
        sid = self.state.get("session_id", "?")
        last = self.state.get("last_checkpoint", "never")
        plan = self._plan_summary()
        agents = len(self.state.get("agents", {}))
        scouts = len(self.state.get("scout_queue", []))
        dirty = self.state.get("dirty_flags", [])
        crashes = len(self.state.get("crash_log", []))

        print(f"  {C.CYAN}Session:{C.RESET} {sid}")
        print(f"  {C.CYAN}Last CP:{C.RESET} {last}")
        if plan:
            done = sum(1 for v in plan["objectives"].values() if v == "completed")
            total = len(plan["objectives"])
            print(f"  {C.CYAN}Plan:{C.RESET} {plan['name']} [{done}/{total}]")
        print(f"  {C.CYAN}Agents:{C.RESET} {agents} | {C.CYAN}Scouts:{C.RESET} {scouts} | {C.CYAN}Crashes:{C.RESET} {crashes}")
        if dirty:
            print(f"  {C.YELLOW}Dirty:{C.RESET} {', '.join(dirty)}")
