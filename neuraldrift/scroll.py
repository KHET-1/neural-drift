#!/usr/bin/env python3
"""
scroll.py — NeuralDrift Opening Scroll
An animated neural boot sequence that introduces the dual-brain system.

5-phase reveal:
  1. Frame materializes from shade characters
  2. NEURAL DRIFT title decrypts (scramble → lock-in)
  3. Neural network art draws itself
  4. Dual brain split reveal
  5. Stats pulse in and ready prompt

Usage:
    python3 -m neuraldrift.scroll           # full animated scroll
    python3 -m neuraldrift.scroll --quick   # fast mode (reduced delays)
    python3 -m neuraldrift.scroll --static  # no animation, just print
"""

import os
import random
import shutil
import string
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ─── Color System ───────────────────────────────────────────

def rgb(r, g, b):
    """Truecolor foreground."""
    return f"\033[38;2;{r};{g};{b}m"

def rgb_bg(r, g, b):
    """Truecolor background."""
    return f"\033[48;2;{r};{g};{b}m"

RST = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

# NeuralDrift palette
NEURAL  = rgb(0, 255, 255)       # Electric cyan
AI_PINK = rgb(255, 80, 180)      # AI magenta-pink
HUMAN   = rgb(255, 191, 0)       # Warm amber
STEEL   = rgb(88, 88, 88)        # Steel gray
NEON    = rgb(57, 255, 20)       # Neon green
WHITE   = rgb(255, 255, 255)     # Bright white
SILVER  = rgb(180, 180, 180)     # Silver
FAINT   = rgb(60, 60, 60)        # Very dim

# Fallback ANSI if no truecolor
ANSI_CYAN    = "\033[96m"
ANSI_MAGENTA = "\033[95m"
ANSI_YELLOW  = "\033[93m"
ANSI_GREEN   = "\033[92m"
ANSI_WHITE   = "\033[97m"
ANSI_GRAY    = "\033[90m"
ANSI_RED     = "\033[91m"

def has_truecolor():
    """Detect truecolor support."""
    ct = os.environ.get("COLORTERM", "")
    return ct in ("truecolor", "24bit")

def gradient_text(text, start_rgb, end_rgb):
    """Apply horizontal color gradient to text."""
    n = max(len(text) - 1, 1)
    result = []
    for i, ch in enumerate(text):
        if ch == ' ':
            result.append(ch)
            continue
        t = i / n
        r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * t)
        g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * t)
        b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * t)
        result.append(f"{rgb(r, g, b)}{ch}")
    return "".join(result) + RST

def gradient_line_vertical(text, color_rgb, line_idx, total_lines):
    """Apply vertical dimming — brighter at top, dimmer at bottom."""
    t = line_idx / max(total_lines - 1, 1)
    r = int(color_rgb[0] * (1 - t * 0.4))
    g = int(color_rgb[1] * (1 - t * 0.4))
    b = int(color_rgb[2] * (1 - t * 0.4))
    return f"{rgb(r, g, b)}{text}{RST}"


# ─── Animation Primitives ──────────────────────────────────

def hide_cursor():
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()

def show_cursor():
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()

def flush():
    sys.stdout.flush()

def typed(text, delay=0.03, color=""):
    """Typewriter effect with optional color."""
    for ch in text:
        sys.stdout.write(f"{color}{ch}{RST}" if color else ch)
        flush()
        time.sleep(delay + random.uniform(-0.01, 0.015))
    print()

def reveal_lines(lines, delay=0.04, prefix=""):
    """Line-by-line reveal."""
    for line in lines:
        print(f"{prefix}{line}")
        flush()
        time.sleep(delay)

def decrypt_text(text, color_locked, color_cycling, iterations=12, delay=0.04):
    """Decrypt/scramble effect — random chars lock in left to right."""
    chars = string.ascii_letters + string.digits + "!@#$%^&*<>{}[]|/\\"
    length = len(text)

    for iteration in range(iterations + 1):
        lock_pos = int(length * (iteration / iterations))
        display = []
        for i, ch in enumerate(text):
            if ch == ' ':
                display.append(' ')
            elif i < lock_pos:
                display.append(f"{color_locked}{ch}")
            else:
                display.append(f"{color_cycling}{random.choice(chars)}")
        line = "".join(display) + RST
        sys.stdout.write(f"\r{line}")
        flush()
        time.sleep(delay)
    print()

def fade_line(text, color, steps=4, delay=0.06):
    """Fade in using shade characters then real text."""
    shades = ['░', '▒', '▓']
    for shade in shades:
        display = "".join(shade if ch != ' ' else ' ' for ch in text)
        sys.stdout.write(f"\r{STEEL}{display}{RST}")
        flush()
        time.sleep(delay)
    sys.stdout.write(f"\r{color}{text}{RST}")
    flush()
    print()

def pulse_flash(text, color, flashes=2, delay=0.08):
    """Brief bright flash effect."""
    for _ in range(flashes):
        sys.stdout.write(f"\r{WHITE}{BOLD}{text}{RST}")
        flush()
        time.sleep(delay)
        sys.stdout.write(f"\r{color}{text}{RST}")
        flush()
        time.sleep(delay)
    print()


# ─── The Scroll ────────────────────────────────────────────

# The brain art — designed for exact alignment, no leading newlines
BRAIN_LEFT = [
    "        ╭───────────╮        ",
    "     ╭──┤  THOUGHTS  ├──╮    ",
    "   ╭─┤  ╰─────┬─────╯  ├─╮  ",
    "   │ ╰────────┤─────────╯ │  ",
    "   │  ┌───────┴────────┐  │  ",
    "   │  │  ◎ Ideas       │  │  ",
    "   │  │  ◎ Stories     │  │  ",
    "   │  │  ◎ Moods       │  │  ",
    "   │  │  ◎ Journal     │  │  ",
    "   │  └────────────────┘  │  ",
    "   ╰──────────────────────╯  ",
    "       H U M A N             ",
]

BRAIN_RIGHT = [
    "        ╭───────────╮        ",
    "     ╭──┤   FACTS    ├──╮    ",
    "   ╭─┤  ╰─────┬─────╯  ├─╮  ",
    "   │ ╰────────┤─────────╯ │  ",
    "   │  ┌───────┴────────┐  │  ",
    "   │  │  ◉ Knowledge   │  │  ",
    "   │  │  ◉ Agents      │  │  ",
    "   │  │  ◉ Scouts      │  │  ",
    "   │  │  ◉ Council     │  │  ",
    "   │  └────────────────┘  │  ",
    "   ╰──────────────────────╯  ",
    "          A . I .            ",
]

TITLE_ART = [
    " ███╗   ██╗███████╗██╗   ██╗██████╗  █████╗ ██╗     ",
    " ████╗  ██║██╔════╝██║   ██║██╔══██╗██╔══██╗██║     ",
    " ██╔██╗ ██║█████╗  ██║   ██║██████╔╝███████║██║     ",
    " ██║╚██╗██║██╔══╝  ██║   ██║██╔══██╗██╔══██║██║     ",
    " ██║ ╚████║███████╗╚██████╔╝██║  ██║██║  ██║███████╗",
    " ╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝",
]

DRIFT_ART = [
    " ██████╗ ██████╗ ██╗███████╗████████╗",
    " ██╔══██╗██╔══██╗██║██╔════╝╚══██╔══╝",
    " ██║  ██║██████╔╝██║█████╗     ██║   ",
    " ██║  ██║██╔══██╗██║██╔══╝     ██║   ",
    " ██████╔╝██║  ██║██║██║        ██║   ",
    " ╚═════╝ ╚═╝  ╚═╝╚═╝╚═╝        ╚═╝   ",
]

SYNAPSE_CONNECTOR = [
    "                ⚡",
    "         ◇─────◆─────◇",
    "        ╱       │       ╲",
    "       ◇        ◆        ◇",
    "        ╲       │       ╱",
    "         ◇─────◆─────◇",
    "                ⚡",
]


def get_brain_stats():
    """Load brain stats if available."""
    try:
        from neuraldrift.brain import Brain
        brain = Brain()
        meta = brain.db.get("meta", {})
        facts = brain.db.get("facts", {})
        total_facts = sum(len(v) for v in facts.values())
        topics = len(facts)
        xp = meta.get("xp", 0)
        level = meta.get("level", 0)
        return {
            "facts": total_facts,
            "topics": topics,
            "xp": xp,
            "level": level,
        }
    except Exception:
        return {"facts": 0, "topics": 0, "xp": 0, "level": 0}


def phase_1_frame(speed=1.0):
    """Phase 1: Frame materializes."""
    width = 62
    top    = f"  ╔{'═' * (width - 2)}╗"
    bottom = f"  ╚{'═' * (width - 2)}╝"
    side_l = f"  ║"
    side_r = f"{'║':>{width - 2}}"

    # Fade in top border
    fade_line(top, NEURAL, delay=0.04 * speed)
    time.sleep(0.05 * speed)

    # Draw sides — quick
    for _ in range(8):
        line = f"  ║{' ' * (width - 2)}║"
        print(f"{NEURAL}{line}{RST}")
        flush()
        time.sleep(0.02 * speed)

    # Fade in bottom border
    fade_line(bottom, NEURAL, delay=0.04 * speed)


def phase_2_title(speed=1.0):
    """Phase 2: NEURAL DRIFT title decrypts into view."""
    # Move cursor up into the frame
    lines_up = 10  # back into the frame
    sys.stdout.write(f"\033[{lines_up}A")

    # Print title art centered in the frame with decrypt effect
    for i, line in enumerate(TITLE_ART):
        sys.stdout.write(f"\033[{3 + i};4H")  # position inside frame
        color = gradient_text(line, (0, 255, 255), (255, 80, 180))
        sys.stdout.write(color)
        flush()
        time.sleep(0.05 * speed)

    # DRIFT underneath
    for i, line in enumerate(DRIFT_ART):
        sys.stdout.write(f"\033[{9 + i};14H")
        color = gradient_text(line, (255, 80, 180), (255, 191, 0))
        sys.stdout.write(color)
        flush()
        time.sleep(0.05 * speed)

    # Move below the frame
    sys.stdout.write(f"\033[{17};1H")
    flush()


def phase_3_subtitle(speed=1.0):
    """Phase 3: Tagline types itself out."""
    print()
    sys.stdout.write("    ")
    typed("Your knowledge has a temperature.",
          delay=0.025 * speed, color=SILVER)
    time.sleep(0.3 * speed)


def phase_4_brains(speed=1.0):
    """Phase 4: Dual brain split reveal."""
    print()

    # Synapse connector
    for line in SYNAPSE_CONNECTOR:
        centered = f"{'':>17}{line}"
        print(f"{NEON}{centered}{RST}")
        flush()
        time.sleep(0.04 * speed)

    print()
    time.sleep(0.2 * speed)

    # Side by side brains
    for i in range(len(BRAIN_LEFT)):
        left = BRAIN_LEFT[i]
        right = BRAIN_RIGHT[i]

        # Human side in amber, AI side in cyan
        left_colored = f"{HUMAN}{left}{RST}"
        right_colored = f"{NEURAL}{right}{RST}"

        print(f"  {left_colored}  {right_colored}")
        flush()
        time.sleep(0.05 * speed)

    time.sleep(0.3 * speed)


def phase_5_stats(speed=1.0):
    """Phase 5: Stats reveal with pulse."""
    stats = get_brain_stats()

    print()
    print(f"  {STEEL}{'─' * 60}{RST}")
    print()

    # Stats lines with staggered reveal
    stat_lines = [
        (f"  {NEURAL}  Facts:{RST}  {WHITE}{stats['facts']}{RST}  "
         f"{STEEL}across{RST}  {WHITE}{stats['topics']}{RST} topics"),
        (f"  {NEON}  Level:{RST}  {WHITE}{stats['level']}{RST}  "
         f"{STEEL}|{RST}  {NEON}XP:{RST}  {WHITE}{stats['xp']}{RST}"),
    ]

    for line in stat_lines:
        sys.stdout.write(f"{DIM}{line}{RST}")
        flush()
        time.sleep(0.15 * speed)
        # Flash to full brightness
        sys.stdout.write(f"\r{line}")
        flush()
        print()
        time.sleep(0.1 * speed)

    print()

    # XP bar
    xp_in_level = stats['xp'] % 100
    bar_width = 30
    filled = int(bar_width * xp_in_level / 100)
    bar = f"{'█' * filled}{'░' * (bar_width - filled)}"
    print(f"  {STEEL}  Progress:{RST} {NEON}{bar}{RST} {DIM}{xp_in_level}/100{RST}")

    print()
    print(f"  {STEEL}{'─' * 60}{RST}")
    print()


def phase_6_ready(speed=1.0):
    """Phase 6: Ready prompt."""
    # Final message
    sys.stdout.write(f"  {NEURAL}")
    typed("Ready.", delay=0.06 * speed)
    print()


def scroll(quick=False, static=False):
    """Run the full opening scroll."""
    speed = 0.4 if quick else 1.0
    term_width = shutil.get_terminal_size((80, 24)).columns

    if static:
        # No animation — just print everything
        print(f"\n{NEURAL}{BOLD}╔{'═' * 60}╗{RST}")
        for line in TITLE_ART:
            print(f"{NEURAL}║{RST} {gradient_text(line, (0,255,255), (255,80,180))} {NEURAL}║{RST}")
        for line in DRIFT_ART:
            print(f"{NEURAL}║{RST}{'':>12}{gradient_text(line, (255,80,180), (255,191,0))}{'':>10}{NEURAL}║{RST}")
        print(f"{NEURAL}{BOLD}╚{'═' * 60}╝{RST}")
        print(f"\n    {SILVER}Your knowledge has a temperature.{RST}")
        stats = get_brain_stats()
        print(f"\n  {NEURAL}Facts:{RST} {stats['facts']}  {NEURAL}Level:{RST} {stats['level']}  {NEON}XP:{RST} {stats['xp']}")
        print()
        return

    # Animated sequence
    try:
        hide_cursor()
        print()  # breathing room

        # Phase 1: Frame
        phase_1_frame(speed)

        # Phase 2: Title decrypt
        phase_2_title(speed)

        # Phase 3: Subtitle
        phase_3_subtitle(speed)

        # Phase 4: Dual brains
        phase_4_brains(speed)

        # Phase 5: Stats
        phase_5_stats(speed)

        # Phase 6: Ready
        phase_6_ready(speed)

    except KeyboardInterrupt:
        print(f"\n{RST}")
    finally:
        show_cursor()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="NeuralDrift Opening Scroll")
    parser.add_argument("--quick", "-q", action="store_true",
                        help="Fast mode (reduced delays)")
    parser.add_argument("--static", "-s", action="store_true",
                        help="No animation, just print")
    args = parser.parse_args()

    # Respect NO_COLOR convention
    if os.environ.get("NO_COLOR"):
        args.static = True

    scroll(quick=args.quick, static=args.static)


if __name__ == "__main__":
    main()
