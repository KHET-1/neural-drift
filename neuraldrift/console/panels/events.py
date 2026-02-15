"""Events panel — activity log from server events + command output."""

from collections import deque

from rich.panel import Panel
from rich.text import Text


EVENT_ICONS = {
    "info": "[blue][*][/]",
    "success": "[green][+][/]",
    "warning": "[yellow][!][/]",
    "error": "[red][-][/]",
    "debug": "[dim][~][/]",
    "cmd": "[magenta]>[/]",
}


class EventPanel:

    def __init__(self, maxlen: int = 200):
        self.entries: deque[tuple[str, str, str]] = deque(maxlen=maxlen)  # (time, level, msg)

    def add(self, level: str, message: str, timestamp: str = ""):
        import time
        ts = timestamp or time.strftime("%H:%M:%S")
        self.entries.append((ts, level, message))

    def render(self) -> Panel:
        lines = Text()
        # Show last N entries that fit
        visible = list(self.entries)[-30:]
        for ts, level, msg in visible:
            icon = EVENT_ICONS.get(level, "[dim][ ][/]")
            lines.append_text(Text.from_markup(f"[dim]{ts}[/] {icon} {msg}\n"))

        if not visible:
            lines = Text.from_markup("[dim]No events yet...[/]")

        return Panel(lines, title="[bold]EVENTS[/]", border_style="blue")
