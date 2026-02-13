"""Layout manager — builds and updates the rich.Layout tree."""

from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text

from .panels.header import HeaderPanel
from .panels.brain import BrainPanel
from .panels.player import PlayerPanel
from .panels.events import EventPanel
from .panels.agents import AgentPanel


class LayoutManager:
    """Manages the full-screen rich.Layout tree."""

    def __init__(self, has_player: bool = True):
        self.header = HeaderPanel()
        self.brain = BrainPanel()
        self.player = PlayerPanel()
        self.events = EventPanel()
        self.agents = AgentPanel()
        self._has_player = has_player
        self.layout = self._build()

    def _build(self) -> Layout:
        root = Layout()

        root.split_column(
            Layout(name="header", size=3),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=3),
        )

        # Body: left (brain + events) | right (player + agents)
        root["body"].split_row(
            Layout(name="left_col", ratio=1),
            Layout(name="right_col", ratio=1),
        )

        root["left_col"].split_column(
            Layout(name="brain", ratio=1),
            Layout(name="events", ratio=1),
        )

        root["right_col"].split_column(
            Layout(name="player", ratio=2),
            Layout(name="agents", ratio=1),
        )

        return root

    def refresh_all(self, input_prompt: str = "", input_hints: str = ""):
        """Re-render all panels into the layout."""
        self.layout["header"].update(self.header.render())
        self.layout["brain"].update(self.brain.render())
        self.layout["events"].update(self.events.render())
        self.layout["player"].update(self.player.render())
        self.layout["agents"].update(self.agents.render())

        # Footer: input prompt + hints
        footer = Text.from_markup(
            f" {input_prompt}\n"
            f" [dim]{input_hints}[/]"
        )
        self.layout["footer"].update(
            Panel(footer, border_style="bright_black", padding=(0, 0))
        )
