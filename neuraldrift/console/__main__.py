"""NeuralDrift Console — run with: python3 -m neuraldrift.console [music_path]"""

import argparse
import locale
import logging
import os
import sys

# mpv requires C locale for LC_NUMERIC to avoid segfaults
locale.setlocale(locale.LC_NUMERIC, "C")
os.environ["LC_NUMERIC"] = "C"


def main():
    parser = argparse.ArgumentParser(
        prog="neuraldrift.console",
        description="NeuralDrift Console — TUI dashboard with brain + player",
    )
    parser.add_argument(
        "music", nargs="?", default=None,
        help="Path to music file or directory to load",
    )
    parser.add_argument(
        "--no-player", action="store_true",
        help="Disable the music player",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Verbose logging",
    )
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    from .app import ConsoleApp
    app = ConsoleApp(music_path=args.music, no_player=args.no_player)
    app.start()


if __name__ == "__main__":
    main()
