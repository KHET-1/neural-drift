"""Brain panel — level/XP/stats + topic heatmap."""

from rich.panel import Panel
from rich.table import Table
from rich.text import Text


FILL = "\u2588"  # █
EMPTY = "\u2591"  # ░


def _bar(value: float, maximum: float, width: int = 24) -> Text:
    """Colored progress bar using block characters."""
    pct = min(value / maximum, 1.0) if maximum > 0 else 0
    filled = int(width * pct)
    if pct >= 0.7:
        color = "green"
    elif pct >= 0.4:
        color = "yellow"
    else:
        color = "red"
    return Text.from_markup(
        f"[{color}]{FILL * filled}[/][dim]{EMPTY * (width - filled)}[/] {pct * 100:.0f}%"
    )


class BrainPanel:

    def __init__(self):
        self.level = 0
        self.title = ""
        self.xp = 0
        self.xp_pct = 0.0
        self.xp_to_next = 0
        self.facts = 0
        self.topics = 0
        self.agents_active = 0
        self.scouts = 0
        self.musings = 0
        self.heatmap: dict[str, float] = {}

    def update(self, **kw):
        for k, v in kw.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def render(self) -> Panel:
        # Left: brain status
        status = Table.grid(padding=(0, 2), expand=True)
        status.add_column(width=10)
        status.add_column(ratio=1)

        status.add_row("[bold]Level[/]", f"[yellow]{self.level}[/] {self.title}")
        status.add_row("[bold]XP[/]", _bar(self.xp_pct, 100.0, 24))
        status.add_row("", f"[dim]{self.xp} XP ({self.xp_to_next} to next)[/]")
        status.add_row("[bold]Facts[/]", f"{self.facts} / {self.topics} topics")
        status.add_row("[bold]Agents[/]", f"{self.agents_active} active")
        status.add_row("[bold]Scouts[/]", f"{self.scouts} pending")
        status.add_row("[bold]Musings[/]", str(self.musings))

        # Right: topic heatmap
        hm = Table.grid(padding=(0, 1), expand=True)
        hm.add_column(width=16)
        hm.add_column(ratio=1)

        sorted_topics = sorted(self.heatmap.items(), key=lambda x: x[1], reverse=True)[:10]
        max_temp = max((v for _, v in sorted_topics), default=1.0)

        if sorted_topics:
            for topic, temp in sorted_topics:
                label = topic[:15]
                bar_w = 14
                filled = int(bar_w * min(temp / max_temp, 1.0))
                if temp / max_temp >= 0.7:
                    color = "green"
                elif temp / max_temp >= 0.4:
                    color = "yellow"
                else:
                    color = "red"
                bar = f"[{color}]{FILL * filled}[/][dim]{EMPTY * (bar_w - filled)}[/]"
                hm.add_row(f"[dim]{label}[/]", Text.from_markup(bar))

            remaining = len(self.heatmap) - 10
            if remaining > 0:
                hm.add_row(f"[dim]...+{remaining}[/]", "")
        else:
            hm.add_row("[dim]No topics yet[/]", "")

        # Combine side by side
        combined = Table.grid(expand=True)
        combined.add_column(ratio=1)
        combined.add_column(ratio=1)
        combined.add_row(status, hm)

        return Panel(combined, title="[bold]BRAIN[/]", border_style="cyan")
