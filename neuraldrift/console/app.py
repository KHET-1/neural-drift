"""ConsoleApp — main TUI application orchestrator."""

import asyncio
import logging
import time

from rich.console import Console
from rich.live import Live

from neuraldrift.server.daemon import SOCK_PATH

from .client import BrainSocketClient
from .commands import CommandRegistry
from .input import InputHandler
from .layout import LayoutManager
from .player_bridge import PlayerBridge

log = logging.getLogger(__name__)


class ConsoleApp:
    """Main TUI application. Coordinates brain, player, input, and rendering."""

    def __init__(self, music_path: str | None = None, no_player: bool = False):
        self._music_path = music_path
        self._no_player = no_player
        self._quit_event = asyncio.Event()
        self._volume = 70
        self._saved_vol = 70

        self.console = Console()
        self.client = BrainSocketClient(str(SOCK_PATH))
        self.player: PlayerBridge | None = None
        self.input_handler = InputHandler()
        self.commands = CommandRegistry(self)
        self.layout = LayoutManager(has_player=not no_player)

    def start(self):
        """Blocking entry point."""
        asyncio.run(self._run())

    async def _run(self):
        loop = asyncio.get_running_loop()

        # Initialize player
        if not self._no_player:
            self.player = PlayerBridge(loop)
            if self.player.available:
                self.player.set_volume(self._volume)
                self.player.on("state_changed", self._on_player_state)
                self.player.on("track_changed", self._on_player_track)
                self.layout.header.update(player_active=True)
                self.layout.player.update(available=True, volume=self._volume)
                if self._music_path:
                    self.player.load(self._music_path)
            else:
                log.info("Player unavailable (phantom_player not installed)")
                self.player = None

        # Wire brain client callbacks
        self.client.on("connected", self._on_brain_connected)
        self.client.on("disconnected", self._on_brain_disconnected)
        self.client.on("event", self._on_brain_event)

        # Wire input
        self.input_handler.on_hotkey = self._handle_hotkey
        self.input_handler.on_command = self._handle_command
        self.input_handler.start(loop)

        self.log_event("info", "NeuralDrift Console starting...")

        # Launch background tasks
        brain_task = asyncio.create_task(self.client.connect_and_read())
        render_task = asyncio.create_task(self._render_loop())
        player_task = asyncio.create_task(self._player_poll())

        try:
            with Live(
                self.layout.layout,
                console=self.console,
                screen=True,
                auto_refresh=False,
                redirect_stderr=False,
            ) as live:
                self._live = live
                await self._quit_event.wait()
        except KeyboardInterrupt:
            pass
        finally:
            # Cleanup
            self.input_handler.stop()
            brain_task.cancel()
            render_task.cancel()
            player_task.cancel()

            await self.client.close()
            if self.player:
                self.player.shutdown()

            try:
                await brain_task
            except (asyncio.CancelledError, Exception):
                pass
            try:
                await render_task
            except (asyncio.CancelledError, Exception):
                pass
            try:
                await player_task
            except (asyncio.CancelledError, Exception):
                pass

    # ── Render loop ───────────────────────────────────────────────────

    async def _render_loop(self):
        """4 FPS refresh of all panels."""
        try:
            while not self._quit_event.is_set():
                await asyncio.sleep(0.25)
                self.layout.refresh_all(
                    input_prompt=self.input_handler.prompt_text,
                    input_hints=self.input_handler.hint_text,
                )
                if hasattr(self, "_live"):
                    self._live.refresh()
        except asyncio.CancelledError:
            pass

    async def _player_poll(self):
        """2 Hz player position polling."""
        try:
            while not self._quit_event.is_set():
                await asyncio.sleep(0.5)
                if self.player and self.player.available:
                    s = self.player.state
                    if s:
                        self.layout.player.update(
                            playing=s.playing,
                            paused=s.paused,
                            position=s.position or 0.0,
                            duration=s.duration or 0.0,
                            volume=s.volume or self._volume,
                            playlist=self.player.playlist,
                            current_index=self.player.current_index,
                            track_title=s.title or _track_name(s.path) if s.path else "",
                        )
        except asyncio.CancelledError:
            pass

    # ── Brain events ──────────────────────────────────────────────────

    def _on_brain_connected(self):
        self.layout.header.update(server_connected=True)
        self.log_event("success", "Connected to brain server")
        asyncio.ensure_future(self._fetch_initial_data())

    def _on_brain_disconnected(self):
        self.layout.header.update(server_connected=False)
        self.log_event("warning", "Disconnected from brain server")

    def _on_brain_event(self, event: str, data: dict):
        if event == "heartbeat":
            self._update_brain_from_stats(data)
        elif event == "fact_learned":
            self.log_event("success", f"Learned: {data.get('topic','')}/{data.get('fact','')[:40]}")
        elif event == "xp_changed":
            delta = data.get("delta", 0)
            total = data.get("total", 0)
            sign = "+" if delta > 0 else ""
            self.log_event("info", f"XP {sign}{delta} (total: {total})")
            self.layout.header.update(xp=total)
        elif event == "level_up":
            lvl = data.get("level", 0)
            title = data.get("title", "")
            self.log_event("warning", f"LEVEL UP! {lvl}: {title}")
            self.layout.header.update(level=lvl, title=title)
            self.layout.brain.update(level=lvl, title=title)
        elif event == "agent_spawned":
            name = data.get("agent_name", "")
            self.log_event("debug", f"Agent spawned: {name}")
        elif event == "agent_completed":
            aid = data.get("agent_id", "")
            self.log_event("debug", f"Agent #{aid} completed")

    async def _fetch_initial_data(self):
        """Fetch brain state on connect."""
        stats = await self.client.call("stats")
        if stats:
            self._update_brain_from_stats(stats)

        level = await self.client.call("level")
        if level:
            self.layout.brain.update(
                xp_pct=level.get("pct", 0),
                xp_to_next=level.get("to_next", 0),
            )

        heatmap = await self.client.call("heatmap")
        if heatmap:
            self.layout.brain.update(heatmap=heatmap)

        roster = await self.client.call("agent_roster", show_all=True)
        if roster and isinstance(roster, list):
            self.layout.agents.update(roster=roster)

        agent_stats = await self.client.call("agent_stats")
        if agent_stats and isinstance(agent_stats, dict):
            self.layout.agents.update(
                total=agent_stats.get("total", 0),
                active=agent_stats.get("active", 0),
                legends=agent_stats.get("legends", []),
            )

    def _update_brain_from_stats(self, data: dict):
        self.layout.header.update(
            level=data.get("level", 0),
            title=data.get("title", ""),
            xp=data.get("xp", 0),
            facts=data.get("facts", 0),
        )
        self.layout.brain.update(
            level=data.get("level", 0),
            title=data.get("title", ""),
            xp=data.get("xp", 0),
            facts=data.get("facts", 0),
            topics=data.get("topics", 0),
            agents_active=data.get("agents_active", 0),
            scouts=data.get("scouts", 0),
            musings=data.get("musings", 0),
        )

    # ── Player events ─────────────────────────────────────────────────

    def _on_player_state(self):
        pass  # handled by poll

    def _on_player_track(self):
        if self.player:
            s = self.player.state
            if s and s.title:
                self.log_event("info", f"Now playing: {s.title}")

    # ── Hotkey dispatch ───────────────────────────────────────────────

    def _handle_hotkey(self, key: str):
        if key == " ":
            if self.player and self.player.available:
                self.player.toggle_pause()
        elif key == "n":
            if self.player and self.player.available:
                self.player.next()
        elif key == "p":
            if self.player and self.player.available:
                self.player.prev()
        elif key in ("+", "="):
            self._volume = min(100, self._volume + 5)
            if self.player and self.player.available:
                self.player.set_volume(self._volume)
        elif key == "-":
            self._volume = max(0, self._volume - 5)
            if self.player and self.player.available:
                self.player.set_volume(self._volume)
        elif key == "m":
            if self.player and self.player.available:
                if self._volume > 0:
                    self._saved_vol = self._volume
                    self._volume = 0
                else:
                    self._volume = self._saved_vol
                self.player.set_volume(self._volume)
        elif key == "s":
            if self.player and self.player.available:
                self.player.stop()
        elif key == "[":
            if self.player and self.player.available:
                self.player.seek(-10)
        elif key == "]":
            if self.player and self.player.available:
                self.player.seek(10)
        elif key == "r":
            asyncio.ensure_future(self._fetch_initial_data())
            self.log_event("info", "Refreshing brain data...")
        elif key == "?":
            asyncio.ensure_future(self.commands.execute("help"))
        elif key == "q":
            asyncio.ensure_future(self.quit())

    async def _handle_command(self, cmd: str):
        self.log_event("cmd", cmd)
        await self.commands.execute(cmd)

    # ── Utility ───────────────────────────────────────────────────────

    def log_event(self, level: str, message: str):
        self.layout.events.add(level, message)

    async def quit(self):
        self.log_event("info", "Shutting down...")
        self._quit_event.set()


def _track_name(path: str | None) -> str:
    if not path:
        return ""
    from pathlib import Path
    return Path(path).stem.replace("_", " ").replace("-", " ")
