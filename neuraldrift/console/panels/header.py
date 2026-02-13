"""Header panel — title bar, connection status, brain level, clock."""

import time

from rich.text import Text
from rich.table import Table


class HeaderPanel:

    def __init__(self):
        self.server_connected = False
        self.level = 0
        self.title = ""
        self.xp = 0
        self.facts = 0
        self.player_active = False

    def update(self, **kw):
        for k, v in kw.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def render(self) -> Table:
        t = Table.grid(expand=True)
        t.add_column(ratio=1)
        t.add_column(justify="right")

        conn = "[green]CONNECTED[/]" if self.server_connected else "[red]DISCONNECTED[/]"
        left = Text.from_markup(
            f"[bold cyan]NEURALDRIFT CONSOLE[/] [dim]v1.0[/]    Server: {conn}"
        )

        clock = time.strftime("%H:%M:%S")
        parts = []
        if self.level or self.title:
            parts.append(f"[bold]Lv{self.level}[/] [yellow]{self.title}[/]")
        if self.xp:
            parts.append(f"{self.xp} XP")
        if self.facts:
            parts.append(f"{self.facts} facts")
        if self.player_active:
            parts.append("[green]Player[/]")
        parts.append(f"[dim]{clock}[/]")
        right = Text.from_markup(" | ".join(parts))

        t.add_row(left, right)
        return t
