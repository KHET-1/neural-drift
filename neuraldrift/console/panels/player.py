"""Player panel — now playing, progress bar, volume, playlist."""

from rich.panel import Panel
from rich.table import Table
from rich.text import Text


FILL = "\u2501"  # ━
DOT = "\u25CF"   # ●


def _seek_bar(position: float, duration: float, width: int = 30) -> Text:
    """Render a seek bar with position indicator."""
    if duration <= 0:
        return Text.from_markup(f"[dim]{FILL * width}[/]")
    pct = min(position / duration, 1.0)
    pos = int(width * pct)
    pos = max(0, min(pos, width - 1))
    bar = FILL * pos + DOT + FILL * (width - pos - 1)
    return Text.from_markup(f"[cyan]{bar[:pos + 1]}[/][dim]{bar[pos + 1:]}[/]")


def _format_time(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def _vol_bar(vol: int, width: int = 10) -> str:
    filled = int(width * vol / 100)
    return f"[green]{'|' * filled}[/][dim]{'|' * (width - filled)}[/]"


class PlayerPanel:

    def __init__(self):
        self.available = False
        self.playing = False
        self.paused = False
        self.track_title = ""
        self.track_path = ""
        self.position = 0.0
        self.duration = 0.0
        self.volume = 70
        self.playlist: list[str] = []
        self.current_index = -1

    def update(self, **kw):
        for k, v in kw.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def render(self) -> Panel:
        if not self.available:
            return Panel(
                Text.from_markup("[dim]Player not available\nRun with music path to enable[/]"),
                title="[bold]PLAYER[/]",
                border_style="dim",
            )

        content = Table.grid(expand=True)
        content.add_column()

        # Now playing
        title = self.track_title or "[dim]No track loaded[/]"
        state = ""
        if self.playing and not self.paused:
            state = "[green]>> Playing[/]"
        elif self.paused:
            state = "[yellow]|| Paused[/]"
        else:
            state = "[dim]Stopped[/]"

        content.add_row(Text.from_markup(f"[bold]{title}[/]"))

        # Seek bar
        pos_str = _format_time(self.position)
        dur_str = _format_time(self.duration)
        seek = _seek_bar(self.position, self.duration, 28)
        vol_str = _vol_bar(self.volume)
        bar_line = Text()
        bar_line.append_text(Text.from_markup(f"[dim]{pos_str}[/] "))
        bar_line.append_text(seek)
        bar_line.append_text(Text.from_markup(f" [dim]{dur_str}[/]  Vol:{vol_str} {self.volume}%  {state}"))
        content.add_row(bar_line)

        # Separator
        content.add_row(Text.from_markup("[dim]" + "\u2500" * 50 + "[/]"))

        # Playlist
        count = len(self.playlist)
        content.add_row(Text.from_markup(f"[bold]PLAYLIST[/] [dim]({count} tracks)[/]"))

        if self.playlist:
            # Show window around current track
            start = max(0, self.current_index - 2)
            end = min(len(self.playlist), start + 10)
            if end - start < 10:
                start = max(0, end - 10)

            for i in range(start, end):
                name = _track_name(self.playlist[i])
                if i == self.current_index:
                    content.add_row(Text.from_markup(f"[bold green] > {i + 1:2d}. {name}[/]"))
                else:
                    content.add_row(Text.from_markup(f"[dim]   {i + 1:2d}. {name}[/]"))

            if end < len(self.playlist):
                content.add_row(Text.from_markup(f"[dim]   ...+{len(self.playlist) - end} more[/]"))
        else:
            content.add_row(Text.from_markup("[dim]   Empty — use :play <path>[/]"))

        return Panel(content, title="[bold]PLAYER[/]", border_style="green")


def _track_name(path: str) -> str:
    """Extract display name from file path."""
    from pathlib import Path
    p = Path(path)
    return p.stem.replace("_", " ").replace("-", " ")
