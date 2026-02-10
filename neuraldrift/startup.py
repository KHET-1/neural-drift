"""
startup.py — Session startup protocol.
Run at the beginning of every Claude Code session to:
  1. Check session state (resume vs restart)
  2. Validate brain_db integrity
  3. Report lost agents / dirty flags
  4. Queue background intel scouts if applicable

Usage:
    from neuraldrift.startup import preflight
    verdict = preflight()  # Returns "RESUME" | "PARTIAL" | "RESTART"

    # Or from CLI:
    python3 -m neuraldrift.startup
"""

from .output import C, success, error, warning, info, header
from .session import Session, file_hash, BRAIN_DB, rotate_backup
from pathlib import Path


def preflight(verbose=True):
    """
    Run the full startup health check.

    Returns:
        dict with verdict, plan status, integrity, recommendations
    """
    if verbose:
        header("PREFLIGHT CHECK")

    session = Session()
    result = session.resume_check(verbose=verbose)
    verdict = result["verdict"]

    # Extra: check brain_db file size (sanity)
    if BRAIN_DB.exists():
        size = BRAIN_DB.stat().st_size
        if size < 10:
            error(f"brain_db.json is suspiciously small ({size} bytes) — may be corrupted")
            result["recommendations"].append("Check brain_db.json — file may be truncated")
        elif verbose:
            success(f"brain_db.json: {size:,} bytes, hash={file_hash(BRAIN_DB)}")

    # Check for orphaned temp files (sign of past crash during atomic write)
    brain_dir = BRAIN_DB.parent
    temps = list(brain_dir.glob(".brain_db_*.tmp")) + list(brain_dir.glob(".session_state_*.tmp"))
    if temps:
        warning(f"Found {len(temps)} orphaned temp files (previous crash during save)")
        for t in temps:
            if verbose:
                print(f"    {C.DIM}Cleaning: {t.name}{C.RESET}")
            try:
                t.unlink()
            except OSError:
                pass

    # Snapshot integrity for next session
    session.snapshot_integrity()

    if verbose:
        session.summary()
        print()

    return result


def quick_status():
    """One-line status — for embedding in prompts or banners."""
    session = Session()
    state = session.state
    last = state.get("last_checkpoint", "never")
    plan = state.get("plan")
    dirty = state.get("dirty_flags", [])

    parts = []
    if plan and not plan.get("completed"):
        done = sum(1 for o in plan["objectives"].values() if o["status"] == "completed")
        total = len(plan["objectives"])
        parts.append(f"Plan: {done}/{total}")
    if dirty:
        parts.append(f"DIRTY:{len(dirty)}")
    parts.append(f"CP:{last}")

    return " | ".join(parts) if parts else "Clean session"


if __name__ == "__main__":
    preflight()
