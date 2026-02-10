#!/usr/bin/env python3
"""
brain_dashboard.py — Terminal dashboard for the Brain knowledge system.
Renders XP, topics, agents, council, legends, and vaults as a live TUI.
Designed as the blueprint for a future cloud-streamed web dashboard.

Usage:
    python3 brain_dashboard.py
    python3 brain_dashboard.py --live        # auto-refresh every 5s
    python3 brain_dashboard.py --json        # dump dashboard data as JSON
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from neuraldrift.output import C, success, warning, info, visible_len, pad_to_width
from neuraldrift.banners import banner, divider
from neuraldrift.brain import Brain


# ═══════════════════════════════════════
# RENDERING HELPERS
# ═══════════════════════════════════════

def bar(value, maximum, width=30, fill_char="█", empty_char="░",
        color_low=C.RED, color_mid=C.YELLOW, color_high=C.GREEN):
    """Render a colored progress bar."""
    pct = min(value / maximum, 1.0) if maximum > 0 else 0
    filled = int(width * pct)
    color = color_high if pct >= 0.7 else color_mid if pct >= 0.4 else color_low
    return f"{color}{fill_char * filled}{C.GRAY}{empty_char * (width - filled)}{C.RESET}"


def spark(values, width=20):
    """Render a sparkline from a list of numbers."""
    if not values:
        return f"{C.GRAY}(no data){C.RESET}"
    blocks = " ▁▂▃▄▅▆▇█"
    mn, mx = min(values), max(values)
    rng = mx - mn if mx != mn else 1
    # Sample down to width if needed
    if len(values) > width:
        step = len(values) / width
        sampled = [values[int(i * step)] for i in range(width)]
    else:
        sampled = values
    line = ""
    for v in sampled:
        idx = int((v - mn) / rng * (len(blocks) - 1))
        line += blocks[idx]
    return f"{C.CYAN}{line}{C.RESET}"


def box(title, lines, width=58, border_color=C.CYAN):
    """Render a bordered box with title."""
    bc = border_color
    inner = width - 2
    print(f"  {bc}╔{'═' * inner}╗{C.RESET}")
    print(f"  {bc}║{C.RESET} {pad_to_width(f'{C.BOLD}{C.WHITE}{title}{C.RESET}', width - 4 + len(C.BOLD) + len(C.WHITE) + len(C.RESET))} {bc}║{C.RESET}")
    print(f"  {bc}╠{'═' * inner}╣{C.RESET}")
    for line in lines:
        vlen = visible_len(line)
        padding = max(0, width - 4 - vlen)
        print(f"  {bc}║{C.RESET} {line}{' ' * padding} {bc}║{C.RESET}")
    print(f"  {bc}╚{'═' * inner}╝{C.RESET}")


def heatmap_row(label, count, max_count, width=20):
    """Render a single heatmap row for topic density."""
    pct = count / max_count if max_count > 0 else 0
    blocks = int(width * pct)
    if pct >= 0.7:
        color = C.GREEN
    elif pct >= 0.4:
        color = C.YELLOW
    else:
        color = C.BLUE
    heat = f"{color}{'█' * blocks}{C.GRAY}{'░' * (width - blocks)}{C.RESET}"
    return f"{C.WHITE}{label:<20}{C.RESET} {heat} {C.DIM}{count}{C.RESET}"


# ═══════════════════════════════════════
# DASHBOARD PANELS
# ═══════════════════════════════════════

def panel_brain_status(brain):
    """XP, level, and health overview."""
    meta = brain.db.get("meta", {})
    xp = meta.get("xp", 0)
    level = meta.get("level", 0)
    xp_in_level = xp % 100
    facts = brain.db.get("facts", {})
    total_facts = sum(len(v) for v in facts.values())
    topics = len(facts)
    soft = len(brain.db.get("soft", []))
    prompts = len(brain.db.get("prompts", []))

    # Level title
    titles = {
        0: "Blank Slate", 1: "Awakened", 2: "Observer", 3: "Student",
        5: "Apprentice", 8: "Practitioner", 10: "Specialist", 15: "Expert",
        20: "Master", 30: "Sage", 50: "Oracle", 75: "Transcendent", 100: "Omniscient",
    }
    title = "Sage"
    for threshold in sorted(titles.keys(), reverse=True):
        if level >= threshold:
            title = titles[threshold]
            break

    xp_bar = bar(xp_in_level, 100, width=24)

    lines = [
        f"{C.BOLD}Level {level}{C.RESET} {C.DIM}\"{title}\"{C.RESET}",
        f"XP: {C.GREEN}{xp}{C.RESET} {xp_bar} {C.DIM}{xp_in_level}/100{C.RESET}",
        f"",
        f"{C.CYAN}{total_facts}{C.RESET} facts across {C.CYAN}{topics}{C.RESET} topics",
        f"{C.MAGENTA}{soft}{C.RESET} soft notes | {C.YELLOW}{prompts}{C.RESET} prompts",
    ]
    box("BRAIN STATUS", lines, border_color=C.GREEN)


def panel_topic_heatmap(brain):
    """Topic density heatmap."""
    facts = brain.db.get("facts", {})
    if not facts:
        box("TOPIC HEATMAP", [f"{C.GRAY}(no topics){C.RESET}"])
        return

    sorted_topics = sorted(facts.items(), key=lambda x: len(x[1]), reverse=True)
    max_count = len(sorted_topics[0][1]) if sorted_topics else 1

    lines = []
    for topic, topic_facts in sorted_topics[:12]:
        lines.append(heatmap_row(topic, len(topic_facts), max_count))

    if len(sorted_topics) > 12:
        lines.append(f"{C.DIM}  ... +{len(sorted_topics) - 12} more topics{C.RESET}")

    box("TOPIC HEATMAP", lines, border_color=C.CYAN)


def panel_confidence_distribution(brain):
    """Confidence distribution histogram."""
    facts = brain.db.get("facts", {})
    buckets = {"90-100%": 0, "80-89%": 0, "70-79%": 0, "60-69%": 0, "<60%": 0}

    for topic_facts in facts.values():
        for f in topic_facts:
            c = f.get("confidence", 50)
            if c >= 90:
                buckets["90-100%"] += 1
            elif c >= 80:
                buckets["80-89%"] += 1
            elif c >= 70:
                buckets["70-79%"] += 1
            elif c >= 60:
                buckets["60-69%"] += 1
            else:
                buckets["<60%"] += 1

    total = sum(buckets.values()) or 1
    max_b = max(buckets.values()) or 1

    lines = []
    colors = [C.GREEN, C.GREEN, C.YELLOW, C.YELLOW, C.RED]
    for (label, count), color in zip(buckets.items(), colors):
        w = int(20 * count / max_b)
        pct = count / total * 100
        lines.append(f"{C.WHITE}{label:<10}{C.RESET} {color}{'█' * w}{C.GRAY}{'░' * (20 - w)}{C.RESET} {C.DIM}{count} ({pct:.0f}%){C.RESET}")

    box("CONFIDENCE DISTRIBUTION", lines, border_color=C.YELLOW)


def panel_agents(brain):
    """Agent roster and hierarchy."""
    agents = brain.db.get("agents", {})
    council = brain.db.get("council", [])
    legends = brain.db.get("legendary", {})

    if not agents:
        box("AGENT HIERARCHY", [
            f"{C.GRAY}No agents deployed yet{C.RESET}",
            f"",
            f"{C.DIM}Use brain.agent_checkin() to deploy{C.RESET}",
        ], border_color=C.MAGENTA)
        return

    lines = []

    # Council
    hoods = ["Architect", "Oracle", "Phantom", "Warden", "Forgekeeper", "Harbinger"]
    if council:
        lines.append(f"{C.YELLOW}{C.BOLD}Council of 6{C.RESET}")
        for i, name in enumerate(council[:6]):
            hood = hoods[i] if i < len(hoods) else "?"
            sigil = ""
            if name in legends:
                leg = legends[name]
                sigil = f" {leg.get('sigil', '?')}"
            lines.append(f"  {C.YELLOW}{hood:<14}{C.RESET} {C.WHITE}{name}{C.RESET}{sigil}")
        lines.append("")

    # Legends
    if legends:
        lines.append(f"{C.MAGENTA}{C.BOLD}Legendary{C.RESET}")
        for name, data in legends.items():
            lvl_name = data.get("level_name", "Aspirant")
            sigil = data.get("sigil", "?")
            exp = data.get("exp", 0)
            lines.append(f"  {sigil} {C.WHITE}{name}{C.RESET} {C.DIM}{lvl_name} ({exp} EXP){C.RESET}")
        lines.append("")

    # Regular agents
    ranked = sorted(agents.items(), key=lambda x: x[1].get("score", 0) if isinstance(x[1], dict) else 0, reverse=True)
    lines.append(f"{C.CYAN}{C.BOLD}Agents ({len(agents)} total){C.RESET}")
    for name, data in ranked[:6]:
        if not isinstance(data, dict):
            continue
        missions = data.get("missions", 0)
        score = data.get("score", 0)
        traits = data.get("traits", [])
        trait_str = f" {C.DIM}[{', '.join(traits[:2])}]{C.RESET}" if traits else ""
        lines.append(f"  {C.WHITE}{name:<18}{C.RESET} {C.GREEN}{missions}m{C.RESET} {C.CYAN}{score:.0f}pts{C.RESET}{trait_str}")
    if len(agents) > 6:
        lines.append(f"  {C.DIM}... +{len(agents) - 6} more{C.RESET}")

    box("AGENT HIERARCHY", lines, border_color=C.MAGENTA)


def panel_vaults(brain):
    """Compartmentalized vault status."""
    vaults = brain.db.get("vaults", {})
    vault_names = {
        "council": ("Council Vault", "⚜️", C.YELLOW),
        "shiny": ("Shiny Archive", "✨", C.GREEN),
        "dark_mask": ("Dark Codex", "🎭", C.RED),
        "legendary": ("Eternal Grimoire", "♚", C.MAGENTA),
    }

    lines = []
    any_data = False
    for key, (name, icon, color) in vault_names.items():
        entries = vaults.get(key, [])
        count = len(entries)
        if count > 0:
            any_data = True
        status_bar = bar(count, 20, width=15, color_low=C.BLUE, color_mid=C.CYAN, color_high=color)
        lines.append(f"{icon} {color}{name:<20}{C.RESET} {status_bar} {C.DIM}{count} entries{C.RESET}")

    if not any_data:
        lines.append("")
        lines.append(f"{C.DIM}Vaults empty — deploy agents to populate{C.RESET}")

    box("KNOWLEDGE VAULTS", lines, border_color=C.RED)


def panel_xp_timeline(brain):
    """XP gain timeline (sparkline)."""
    xp_log = brain.db.get("meta", {}).get("xp_log", [])

    lines = []
    if xp_log:
        # Get last 40 XP events
        recent = xp_log[-40:]
        amounts = [e.get("amount", 0) for e in recent if e.get("amount", 0) > 0]
        if amounts:
            lines.append(f"Last {len(amounts)} gains: {spark(amounts, width=30)}")
        # Show net gain in last 10
        last_10 = [e.get("amount", 0) for e in xp_log[-10:]]
        net = sum(last_10)
        color = C.GREEN if net > 0 else C.RED
        lines.append(f"Recent trend: {color}{'+' if net > 0 else ''}{net} XP{C.RESET} (last {len(last_10)} events)")
    else:
        lines.append(f"{C.GRAY}No XP history yet{C.RESET}")

    # Projections
    meta = brain.db.get("meta", {})
    xp = meta.get("xp", 0)
    level = meta.get("level", 0)
    next_level_xp = (level + 1) * 100
    remaining = next_level_xp - xp

    lines.append("")
    lines.append(f"Next level: {C.BOLD}{level + 1}{C.RESET} in {C.YELLOW}{remaining} XP{C.RESET}")

    # Milestone targets
    milestones = [(50, "Oracle"), (75, "Transcendent"), (100, "Omniscient")]
    for mlvl, mname in milestones:
        if level < mlvl:
            needed = (mlvl * 100) - xp
            lines.append(f"  {C.DIM}{mname} (lvl {mlvl}): {needed} XP away{C.RESET}")
            break

    box("XP TIMELINE", lines, border_color=C.GREEN)


def panel_prompt_vault(brain):
    """Prompt collection stats."""
    prompts = brain.db.get("prompts", {})

    if not prompts:
        box("PROMPT VAULT", [f"{C.GRAY}No prompts stored{C.RESET}"])
        return

    lines = []
    if isinstance(prompts, dict):
        for cat, cat_prompts in sorted(prompts.items()):
            if not isinstance(cat_prompts, list):
                continue
            count = len(cat_prompts)
            top_score = 0
            for p in cat_prompts:
                if isinstance(p, dict):
                    top_score = max(top_score, p.get("score", 0))
            score_color = C.GREEN if top_score >= 70 else C.YELLOW if top_score >= 40 else C.RED
            lines.append(f"{C.WHITE}{cat:<20}{C.RESET} {C.DIM}x{count}{C.RESET}  best: {score_color}{top_score:.0f}{C.RESET}")
    else:
        lines.append(f"{C.DIM}{len(prompts)} prompts (legacy format){C.RESET}")

    box("PROMPT VAULT", lines, border_color=C.YELLOW)


# ═══════════════════════════════════════
# MAIN DASHBOARD RENDER
# ═══════════════════════════════════════

def render_dashboard(brain):
    """Render the full terminal dashboard."""
    os.system("clear")

    # Title
    print(f"{C.RED}{C.BOLD}  ╔══════════════════════════════════════════════════════════╗")
    print(f"  ║{C.CYAN}          ██████  ██████   █████  ██ ██   ██              {C.RED}║")
    print(f"  ║{C.CYAN}          ██   ██ ██   ██ ██   ██ ██ ███  ██              {C.RED}║")
    print(f"  ║{C.CYAN}          ██████  ██████  ███████ ██ ██ █ ██              {C.RED}║")
    print(f"  ║{C.CYAN}          ██   ██ ██   ██ ██   ██ ██ ██  ███              {C.RED}║")
    print(f"  ║{C.CYAN}          ██████  ██   ██ ██   ██ ██ ██   ██              {C.RED}║")
    print(f"  ║{C.WHITE}              D A S H B O A R D   v 1 . 0                  {C.RED}║")
    print(f"  ╚══════════════════════════════════════════════════════════╝{C.RESET}")
    print(f"  {C.GRAY}NeuralDrift | {time.strftime('%Y-%m-%d %H:%M:%S')}{C.RESET}")
    print()

    # Row 1: Brain Status + XP Timeline
    panel_brain_status(brain)
    print()
    panel_xp_timeline(brain)
    print()

    # Row 2: Topic Heatmap + Confidence
    panel_topic_heatmap(brain)
    print()
    panel_confidence_distribution(brain)
    print()

    # Row 3: Agents + Vaults
    panel_agents(brain)
    print()
    panel_vaults(brain)
    print()

    # Row 4: Prompts
    panel_prompt_vault(brain)
    print()

    # Footer
    print(f"  {C.GRAY}{'─' * 58}{C.RESET}")
    print(f"  {C.DIM}Press Ctrl+C to exit | --live for auto-refresh{C.RESET}")


def dashboard_json(brain):
    """Export dashboard data as JSON for cloud streaming."""
    facts = brain.db.get("facts", {})
    meta = brain.db.get("meta", {})
    agents = brain.db.get("agents", {})

    data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "brain": {
            "xp": meta.get("xp", 0),
            "level": meta.get("level", 0),
            "total_facts": sum(len(v) for v in facts.values()),
            "topics": len(facts),
            "topic_counts": {t: len(f) for t, f in facts.items()},
        },
        "agents": {
            "total": len(agents),
            "council": brain.db.get("council", []),
            "legends": list(brain.db.get("legendary", {}).keys()),
        },
        "vaults": {k: len(v) for k, v in brain.db.get("vaults", {}).items()},
        "prompts": len(brain.db.get("prompts", [])),
    }
    print(json.dumps(data, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Brain Dashboard — Knowledge System Visualizer")
    parser.add_argument("--live", action="store_true", help="Auto-refresh every 5 seconds")
    parser.add_argument("--json", action="store_true", help="Export as JSON (for cloud streaming)")
    parser.add_argument("--interval", type=int, default=5, help="Refresh interval in seconds (with --live)")
    args = parser.parse_args()

    if args.json:
        brain = Brain()
        dashboard_json(brain)
        return

    try:
        while True:
            brain = Brain()  # Reload each cycle to pick up changes
            render_dashboard(brain)
            if not args.live:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print(f"\n  {C.GREEN}Dashboard closed.{C.RESET}")


if __name__ == "__main__":
    main()
