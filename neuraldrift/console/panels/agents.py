"""Agents panel — roster, council, legends."""

from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class AgentPanel:

    def __init__(self):
        self.roster: list[dict] = []
        self.legends: list[str] = []
        self.total = 0
        self.active = 0

    def update(self, **kw):
        for k, v in kw.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def render(self) -> Panel:
        content = Text()

        if self.roster:
            t = Table.grid(padding=(0, 1))
            t.add_column(width=6)   # id
            t.add_column(width=14)  # name
            t.add_column(width=8)   # status
            t.add_column()          # task/result

            for a in self.roster[-8:]:
                aid = f"#{a.get('id', '?')}"
                name = a.get('name', 'Unknown')[:13]
                status = a.get('status', '?')
                task = a.get('task', '') or a.get('result', '')
                task = task[:30]

                if status == "active":
                    sc = "[green]active[/]"
                else:
                    sc = f"[dim]{status}[/]"

                t.add_row(f"[dim]{aid}[/]", f"[bold]{name}[/]", Text.from_markup(sc), f"[dim]{task}[/]")

            content = t
        else:
            content = Text.from_markup("[dim]No agents yet[/]")

        # Add legends line
        legend_text = ""
        if self.legends:
            legend_text = f"\n[yellow]Legends:[/] {', '.join(self.legends[:5])}"
        elif self.total > 0:
            legend_text = f"\n[dim]{self.total} agents total, {self.active} active[/]"

        final = Text()
        if isinstance(content, Table):
            return Panel(
                content,
                title="[bold]AGENTS[/]",
                border_style="magenta",
                subtitle=Text.from_markup(legend_text.strip()) if legend_text.strip() else None,
            )
        else:
            return Panel(content, title="[bold]AGENTS[/]", border_style="magenta")
