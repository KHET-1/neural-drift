"""Console panel base class."""

from rich.panel import Panel
from rich.text import Text


class BasePanel:
    """Base for all dashboard panels."""

    title: str = ""
    border_style: str = "cyan"

    def render(self) -> Panel:
        return Panel(Text("..."), title=self.title, border_style=self.border_style)
