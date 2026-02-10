"""
Banner generators for tools and scripts.
Usage:
    from neuraldrift import banner, mini_banner
"""

from .output import C, visible_len

def banner(name, version="1.0", author="", tagline=""):
    """Print a styled tool banner."""
    inner_width = 44  # fixed inner width for the ██ box
    tag = tagline or 'NeuralDrift'
    name_ver = f"{name} v{version}"
    name_pad = max(0, inner_width - 4 - len(name) - len(version) - 2)
    tag_pad = max(0, inner_width - 4 - len(tag))
    border = '═' * (inner_width + 4)

    print(f"{C.RED}{C.BOLD}{border}")
    print(f"{C.CYAN}  ██{'▀' * inner_width}██")
    print(f"{C.CYAN}  ██  {C.WHITE}{C.BOLD}{name} {C.GRAY}v{version}{C.CYAN}{' ' * name_pad}██")
    print(f"{C.CYAN}  ██  {C.DIM}{tag}{C.CYAN}{' ' * tag_pad}██")
    print(f"{C.CYAN}  ██{'▄' * inner_width}██")
    print(f"{C.RED}{border}{C.RESET}")
    print(f"{C.GRAY}  {f'by {author} | ' if author else ''}NeuralDrift{C.RESET}")
    print()

def mini_banner(name, desc=""):
    """Print a compact one-line banner."""
    print(f"\n{C.CYAN}{C.BOLD}▶ {name}{C.RESET}{C.GRAY} — {desc}{C.RESET}\n")

def status_line(label, status, ok=True):
    """Print a status check line."""
    icon = f"{C.GREEN}✓{C.RESET}" if ok else f"{C.RED}✗{C.RESET}"
    print(f"  {icon} {label:<30} {C.BOLD}{status}{C.RESET}")

def divider(char='─', width=60):
    """Print a horizontal divider."""
    print(f"{C.GRAY}{char * width}{C.RESET}")
