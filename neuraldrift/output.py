"""
Colored terminal output utilities.
Usage:
    from neuraldrift import success, error, warning, info, header, table_print
    from neuraldrift.output import CandyCane
"""

import re
import sys
import time
import threading
import unicodedata

# ANSI escape sequence regex — strips ALL SGR codes for visible length calculation
_ANSI_RE = re.compile(r'\033\[[0-9;]*m')

# ANSI color codes
class C:
    RED     = '\033[91m'
    GREEN   = '\033[92m'
    YELLOW  = '\033[93m'
    BLUE    = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN    = '\033[96m'
    WHITE   = '\033[97m'
    GRAY    = '\033[90m'
    BOLD    = '\033[1m'
    DIM     = '\033[2m'
    UNDERLINE = '\033[4m'
    RESET   = '\033[0m'
    BG_RED  = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'

def visible_len(text):
    """Calculate the visible display width of text, stripping ANSI codes
    and accounting for wide characters (emoji, CJK, etc.)."""
    stripped = _ANSI_RE.sub('', str(text))
    width = 0
    for ch in stripped:
        eaw = unicodedata.east_asian_width(ch)
        if eaw in ('W', 'F'):  # Wide or Fullwidth = 2 columns
            width += 2
        else:
            width += 1
    return width


def pad_to_width(text, target_width, fill=' '):
    """Pad text to a target visible width, accounting for ANSI codes and wide chars."""
    current = visible_len(text)
    padding = max(0, target_width - current)
    return text + fill * padding


def _print(color, symbol, msg, **kwargs):
    print(f"{color}{symbol}{C.RESET} {msg}", **kwargs)

def success(msg, **kw):  _print(C.GREEN,   '[+]', msg, **kw)
def error(msg, **kw):    _print(C.RED,     '[-]', msg, **kw)
def warning(msg, **kw):  _print(C.YELLOW,  '[!]', msg, **kw)
def info(msg, **kw):     _print(C.BLUE,    '[*]', msg, **kw)
def debug(msg, **kw):    _print(C.GRAY,    '[~]', msg, **kw)
def critical(msg, **kw): _print(C.BG_RED + C.WHITE, '[!!!]', msg, **kw)

def header(title, width=60, char='═'):
    """Print a formatted section header."""
    title_width = visible_len(title)
    pad = (width - title_width - 2) // 2
    line = char * pad
    right_pad = width - title_width - 2 - pad  # handle odd widths
    print(f"\n{C.CYAN}{C.BOLD}{char * pad} {title} {char * right_pad}{C.RESET}")

def subheader(title):
    """Print a subsection header."""
    print(f"\n{C.MAGENTA}{C.BOLD}── {title} ──{C.RESET}")

def kvprint(key, value, key_color=None):
    """Print a key-value pair, aligned."""
    kc = key_color or C.CYAN
    print(f"  {kc}{key:<20}{C.RESET} {value}")

def table_print(headers, rows, colors=None):
    """Print a formatted terminal table with dynamic column widths."""
    if not rows:
        warning("No data to display")
        return

    col_widths = [visible_len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], visible_len(str(cell)))

    # Header
    hdr_parts = []
    for i, h in enumerate(headers):
        hdr_parts.append(f"{C.BOLD}{C.CYAN}{pad_to_width(h, col_widths[i])}{C.RESET}")
    hdr = " │ ".join(hdr_parts)
    sep = "─┼─".join("─" * w for w in col_widths)
    print(f" {hdr}")
    print(f" {C.GRAY}{sep}{C.RESET}")

    # Rows
    for row in rows:
        cells = []
        for i, cell in enumerate(row):
            w = col_widths[i] if i < len(col_widths) else 20
            color = colors[i] if colors and i < len(colors) else ""
            reset = C.RESET if color else ""
            cells.append(f"{color}{pad_to_width(str(cell), w)}{reset}")
        print(f" {' │ '.join(cells)}")

def progress_bar(current, total, width=40, label=""):
    """Print an inline progress bar."""
    pct = current / total if total else 0
    filled = int(width * pct)
    bar = f"{'█' * filled}{'░' * (width - filled)}"
    color = C.GREEN if pct >= 0.8 else C.YELLOW if pct >= 0.4 else C.RED
    sys.stdout.write(f"\r  {color}{bar}{C.RESET} {pct*100:5.1f}% {label}")
    if current >= total:
        sys.stdout.write('\n')
    sys.stdout.flush()

def severity_color(level):
    """Return color code for severity level."""
    level = str(level).lower()
    return {
        'critical': C.BG_RED + C.WHITE,
        'high': C.RED,
        'medium': C.YELLOW,
        'low': C.BLUE,
        'info': C.GRAY,
    }.get(level, C.WHITE)

def confidence_tag(pct):
    """Return a colored confidence indicator."""
    if pct >= 90:   return f"{C.GREEN}[{pct}% HIGH]{C.RESET}"
    elif pct >= 70: return f"{C.YELLOW}[{pct}% MED]{C.RESET}"
    else:           return f"{C.RED}[{pct}% LOW]{C.RESET}"


# ═══════════════════════════════════════════════════════
# CANDY CANE SPINNER — excitement-driven animated spinner
# ═══════════════════════════════════════════════════════
#
# Spins faster with excitement level.
# Goes UNICORN (full rainbow cycle) when maxed.
#

class CandyCane:
    """
    Animated candy cane spinner with excitement-driven speed.
    Speed increases with excitement level (0.0 to 1.0).
    At max excitement (>=0.95), goes UNICORN mode — full rainbow cycling.

    Usage:
        candy = CandyCane(label="Scanning")
        candy.start()
        # ... do work ...
        candy.set_excitement(0.5)  # speed up
        candy.set_excitement(1.0)  # UNICORN MODE
        candy.stop("Done!")

        # Or as context manager:
        with CandyCane("Processing") as candy:
            for i in range(10):
                candy.set_excitement(i / 10)
                do_work(i)
    """

    # Candy cane frames — the twist pattern
    _CANE_FRAMES = [
        "╱╲╱╲╱╲",
        "╲╱╲╱╲╱",
        "╱╲╱╲╱╲",
        "╲╱╲╱╲╱",
    ]

    # 8 distinct frames for smooth rotation — no off-by-one
    _SPIN_FRAMES = [
        ("🍬", "╱╲╱╲╱╲"),
        ("🍭", "╲╱╲╱╲╱"),
        ("🍬", "│╱╲╱╲│"),
        ("🍭", "╲╱╲╱╲╱"),
        ("🍬", "╱╲╱╲╱╲"),
        ("🍭", "│╲╱╲╱│"),
        ("🍬", "╲╱╲╱╲╱"),
        ("🍭", "╱╲╱╲╱╲"),
    ]

    # Unicorn rainbow color sequence
    _RAINBOW = [
        '\033[91m',  # red
        '\033[93m',  # yellow
        '\033[92m',  # green
        '\033[96m',  # cyan
        '\033[94m',  # blue
        '\033[95m',  # magenta
    ]

    def __init__(self, label="Working", excitement=0.0):
        """
        Args:
            label: Display text
            excitement: Initial excitement 0.0 (calm) to 1.0 (max/unicorn)
        """
        self.label = label
        self.excitement = max(0.0, min(1.0, excitement))
        self._running = threading.Event()
        self._thread = None
        self._frame = 0
        self._message = ""

    def _interval(self):
        """Speed based on excitement: 0.0=400ms, 0.5=200ms, 1.0=50ms"""
        base = 0.4
        fast = 0.05
        return base - (self.excitement * (base - fast))

    def _is_unicorn(self):
        return self.excitement >= 0.95

    def _render_frame(self):
        """Render one spinner frame."""
        icon, pattern = self._SPIN_FRAMES[self._frame % len(self._SPIN_FRAMES)]

        if self._is_unicorn():
            # UNICORN MODE — rainbow each character
            colored = ""
            for i, ch in enumerate(pattern):
                ci = (self._frame + i) % len(self._RAINBOW)
                colored += f"{self._RAINBOW[ci]}{ch}"
            line = f"  {icon} {colored}{C.RESET} {C.MAGENTA}{C.BOLD}✦ UNICORN ✦{C.RESET} {self.label}"
            if self._message:
                line += f" {C.DIM}— {self._message}{C.RESET}"
        else:
            # Normal candy cane — red/white stripes
            colored = ""
            for i, ch in enumerate(pattern):
                color = C.RED if i % 2 == (self._frame % 2) else C.WHITE
                colored += f"{color}{ch}"
            # Excitement bar
            exc_w = 8
            filled = int(exc_w * self.excitement)
            exc_bar = f"{'▓' * filled}{'░' * (exc_w - filled)}"
            exc_color = C.GREEN if self.excitement < 0.5 else C.YELLOW if self.excitement < 0.8 else C.RED
            line = f"  {icon} {colored}{C.RESET} {self.label} {exc_color}[{exc_bar}]{C.RESET}"
            if self._message:
                line += f" {C.DIM}{self._message}{C.RESET}"

        sys.stdout.write(f"\r{line}   ")
        sys.stdout.flush()
        self._frame += 1

    def _spin_loop(self):
        """Background spin thread."""
        while self._running.is_set():
            self._render_frame()
            time.sleep(self._interval())
        # Clear the line on stop
        sys.stdout.write(f"\r{' ' * 80}\r")
        sys.stdout.flush()

    def start(self):
        """Start the spinner in a background thread."""
        self._running.set()
        self._thread = threading.Thread(target=self._spin_loop, daemon=True)
        self._thread.start()
        return self

    def stop(self, final_message=""):
        """Stop the spinner, optionally print a final message."""
        self._running.clear()
        if self._thread:
            self._thread.join(timeout=1)
        if final_message:
            if self._is_unicorn():
                # Unicorn finish
                rainbow_msg = ""
                for i, ch in enumerate(final_message):
                    ci = i % len(self._RAINBOW)
                    rainbow_msg += f"{self._RAINBOW[ci]}{ch}"
                print(f"  🦄 {rainbow_msg}{C.RESET}")
            else:
                print(f"  {C.GREEN}✓{C.RESET} {final_message}")

    def set_excitement(self, level):
        """Update excitement level (0.0 to 1.0). At 0.95+ = UNICORN."""
        self.excitement = max(0.0, min(1.0, level))

    def set_message(self, msg):
        """Update the status message shown next to the spinner."""
        self._message = msg[:40]

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
