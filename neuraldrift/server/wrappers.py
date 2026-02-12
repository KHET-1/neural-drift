"""Brain method wrappers — return structured data instead of printing."""

from datetime import datetime, timedelta
import math


def stats_data(brain) -> dict:
    """Extract stats as a dict from brain.db directly."""
    db = brain.db
    meta = db.get("meta", {})
    facts = db.get("facts", {})
    total_facts = sum(len(v) for v in facts.values())
    topics = list(facts.keys())
    agents = db.get("agents", {})
    roster = agents.get("roster", [])
    active = [a for a in roster if a.get("status") == "active"]

    return {
        "topics": len(topics),
        "topic_list": topics,
        "facts": total_facts,
        "xp": meta.get("xp", 0),
        "level": meta.get("level", 0),
        "title": _level_title(meta.get("level", 0)),
        "max_recall": meta.get("max_recall", 8),
        "agents_total": len(roster),
        "agents_active": len(active),
        "musings": len(db.get("musings", [])),
        "scouts": len(db.get("scouts", [])),
        "last_saved": meta.get("last_saved", ""),
    }


def level_data(brain) -> dict:
    """Extract level/XP info as a dict."""
    meta = brain.db.get("meta", {})
    xp = meta.get("xp", 0)
    level = meta.get("level", 0)
    next_level = level + 1
    xp_for_next = next_level * 100
    xp_for_current = level * 100
    progress = xp - xp_for_current
    to_next = xp_for_next - xp

    return {
        "level": level,
        "title": _level_title(level),
        "xp": xp,
        "progress": progress,
        "to_next": to_next,
        "pct": round(progress / (xp_for_next - xp_for_current) * 100, 1) if xp_for_next > xp_for_current else 100.0,
    }


def heatmap_data(brain) -> dict:
    """Extract topic temperatures as a dict."""
    facts = brain.db.get("facts", {})
    now = datetime.now()
    temps = {}

    for topic, entries in facts.items():
        if not entries:
            continue
        total = 0.0
        for f in entries:
            learned = f.get("updated") or f.get("learned", "")
            try:
                dt = datetime.strptime(learned, "%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                dt = now - timedelta(days=30)
            age_hours = max(0.01, (now - dt).total_seconds() / 3600)
            recency = math.exp(-0.01 * age_hours)
            frequency = math.log1p(f.get("times_recalled", 0))
            total += recency + frequency * 0.5
        temps[topic] = round(total, 2)

    return temps


def topics_data(brain) -> list[str]:
    """List all topic names."""
    return list(brain.db.get("facts", {}).keys())


# ── Helpers ───────────────────────────────────────────────────────────

_LEVEL_TITLES = {
    0: "Blank Slate", 1: "Awakened", 2: "Observer", 3: "Student",
    5: "Apprentice", 8: "Practitioner", 10: "Specialist", 15: "Expert",
    20: "Master", 30: "Sage", 50: "Oracle", 75: "Transcendent", 100: "Omniscient",
}


def _level_title(level: int) -> str:
    title = "Blank Slate"
    for threshold, name in sorted(_LEVEL_TITLES.items()):
        if level >= threshold:
            title = name
    return title
