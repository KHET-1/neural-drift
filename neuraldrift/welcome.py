#!/usr/bin/env python3
"""
welcome.py — First-run experience for NeuralDrift.
Walks new users through both brains with examples and hand-holding.
Knows when to let go.

Usage:
    python3 -m neuraldrift.welcome
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from neuraldrift.output import C, success, info, warning, header
from neuraldrift.banners import banner


def pause(msg=""):
    """Wait for user to press Enter."""
    try:
        input(f"\n  {C.DIM}{msg or 'Press Enter to continue...'}{C.RESET}")
    except (EOFError, KeyboardInterrupt):
        print()


def typed(text, delay=0.02):
    """Print text with a typing effect."""
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    print()


def welcome():
    """The full first-run experience."""

    print(f"""
{C.CYAN}{C.BOLD}
    ╔══════════════════════════════════════════════════╗
    ║                                                  ║
    ║          Welcome to NeuralDrift                   ║
    ║                                                  ║
    ║    Two brains. One system. Built for you.        ║
    ║                                                  ║
    ╚══════════════════════════════════════════════════╝
{C.RESET}""")

    time.sleep(1)
    typed(f"  {C.WHITE}You have two brains now.{C.RESET}", delay=0.04)
    time.sleep(0.5)
    typed(f"  {C.WHITE}Let me explain.{C.RESET}", delay=0.04)

    pause()

    # ─── AI Brain ───────────────────────────

    print(f"""
  {C.CYAN}{C.BOLD}BRAIN #1: The AI Brain{C.RESET}
  {C.GRAY}{'─' * 40}{C.RESET}

  This is your AI assistant's memory.
  It stores facts, tracks confidence, and levels up as it learns.

  Think of it like a library that:
    {C.GREEN}+{C.RESET} Remembers everything you teach it
    {C.GREEN}+{C.RESET} Knows how confident it is about each fact
    {C.GREEN}+{C.RESET} Gets smarter over time (XP and levels)
    {C.GREEN}+{C.RESET} Sends out scouts to gather intel
    {C.GREEN}+{C.RESET} Shows you what knowledge is hot vs neglected
""")

    pause("Press Enter to see it in action...")

    from neuraldrift.brain import Brain
    brain = Brain()
    print()
    brain.level()

    pause()

    print(f"""
  {C.WHITE}Here's how you teach it:{C.RESET}

    {C.CYAN}brain.learn("python", "f-strings are faster than .format()",
                 confidence=90, source="PEP 498"){C.RESET}

  {C.WHITE}And how you ask it:{C.RESET}

    {C.CYAN}brain.recall("python")       {C.DIM}# get facts on a topic{C.RESET}
    {C.CYAN}brain.search("faster")       {C.DIM}# find across all topics{C.RESET}
    {C.CYAN}brain.heatmap()              {C.DIM}# see what's hot/cold{C.RESET}

  {C.WHITE}It starts at Level 0 — Blank Slate.{C.RESET}
  {C.WHITE}Every fact you teach it earns XP. Level up to unlock new features.{C.RESET}
""")

    pause()

    # ─── Human Brain ────────────────────────

    print(f"""
  {C.MAGENTA}{C.BOLD}BRAIN #2: The Human Brain{C.RESET}
  {C.GRAY}{'─' * 40}{C.RESET}

  This one is yours. Completely personal.

  No scores. No levels. No decay.
  Just a safe space for your mind.

    {C.CYAN}Thoughts{C.RESET}     — fleeting ideas, shower thoughts
    {C.YELLOW}Ideas{C.RESET}       — things you might build or do
    {C.MAGENTA}Stories{C.RESET}     — memories, experiences, narratives
    {C.WHITE}Moods{C.RESET}       — how you're feeling (no judgment)
    {C.GREEN}Journal{C.RESET}     — daily diary entries
    {C.CYAN}Connections{C.RESET} — links between thoughts
""")

    pause("Press Enter to continue...")

    print(f"""
  {C.YELLOW}{C.BOLD}The Consent Rule{C.RESET}

  Nothing enters your Human Brain without your permission.

  If the AI notices something about you — a pattern, an interest,
  something you said in passing — it {C.BOLD}proposes{C.RESET} it first.
  You review. You approve or reject. Your call.

  {C.DIM}Humans are emotional and irrational sometimes.
  That's not a bug. That means you're working through something.
  The brain just holds space. It doesn't judge.{C.RESET}
""")

    pause()

    # ─── Introduction ───────────────────────

    print(f"""
  {C.WHITE}{C.BOLD}Let's set up your Human Brain.{C.RESET}
""")

    from neuraldrift.human_brain import HumanBrain
    hb = HumanBrain()

    try:
        name = input(f"  {C.CYAN}What should I call you? {C.RESET}").strip()
        if not name:
            name = "friend"
    except (EOFError, KeyboardInterrupt):
        name = "friend"

    try:
        motto = input(f"  {C.CYAN}Got a motto or saying? (or just Enter to skip) {C.RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        motto = ""

    hb.introduce(name, motto=motto or None)

    pause()

    # ─── Quick examples ─────────────────────

    print(f"""
  {C.WHITE}{C.BOLD}Quick examples — try these anytime:{C.RESET}

  {C.CYAN}# AI Brain{C.RESET}
  brain = Brain()
  brain.learn("cooking", "salt the pasta water generously", confidence=95, source="grandma")
  brain.recall("cooking")
  brain.level()

  {C.MAGENTA}# Human Brain{C.RESET}
  hb = HumanBrain()
  hb.think("I wonder what the sky looks like from the ISS")
  hb.idea("Build a weather mood tracker", "Match playlist to weather and mood")
  hb.mood("curious", "exploring a new tool")
  hb.reflect()

  {C.YELLOW}# When the AI notices something about you{C.RESET}
  hb.propose("thought", "You seem to love building tools late at night")
  hb.pending()    {C.DIM}# review what's proposed{C.RESET}
  hb.approve(0)   {C.DIM}# accept it{C.RESET}
  hb.reject(0)    {C.DIM}# or don't{C.RESET}
""")

    pause()

    # ─── Persistence ────────────────────────

    print(f"""
  {C.GREEN}{C.BOLD}One more thing — it's all crash-safe.{C.RESET}

  Laptop dies? Power goes out? Internet drops?

  {C.GREEN}+{C.RESET} Every save is atomic (can't corrupt mid-write)
  {C.GREEN}+{C.RESET} Automatic backups before every save
  {C.GREEN}+{C.RESET} Session checkpoints track where you left off
  {C.GREEN}+{C.RESET} Resume protocol tells you what to do when you come back

  Run this at the start of each session:
    {C.CYAN}from neuraldrift.startup import preflight{C.RESET}
    {C.CYAN}preflight()  {C.DIM}# tells you: RESUME, PARTIAL, or RESTART{C.RESET}
""")

    pause()

    # ─── Send off ───────────────────────────

    print(f"""
{C.WHITE}{C.BOLD}
    ╔══════════════════════════════════════════════════╗
    ║                                                  ║
    ║          You're all set, {name:<20}       ║
    ║                                                  ║
    ║    Your AI Brain starts at Level 0.              ║
    ║    Your Human Brain starts empty.                ║
    ║    Both grow with you.                           ║
    ║                                                  ║
    ║    Go build something amazing.                   ║
    ║                                                  ║
    ╚══════════════════════════════════════════════════╝
{C.RESET}""")


if __name__ == "__main__":
    welcome()
