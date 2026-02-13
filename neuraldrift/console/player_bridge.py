"""PlayerBridge — wraps phantom_player's AudioPlayer for asyncio integration."""

import asyncio
import logging
from pathlib import Path

log = logging.getLogger(__name__)

try:
    from phantom_player.core.player import AudioPlayer, PlayerState
    from phantom_player.constants import SUPPORTED_EXTENSIONS
    PLAYER_AVAILABLE = True
except ImportError:
    PLAYER_AVAILABLE = False
    AudioPlayer = None
    PlayerState = None
    SUPPORTED_EXTENSIONS = set()


class PlayerBridge:
    """Bridges AudioPlayer to asyncio event loop. Graceful no-op if unavailable."""

    def __init__(self, loop: asyncio.AbstractEventLoop | None = None):
        self._loop = loop
        self._player: AudioPlayer | None = None
        self._callbacks: dict[str, list] = {}

        if PLAYER_AVAILABLE and loop:
            try:
                self._player = AudioPlayer()
                self._player.on("state_changed", self._on_state_changed)
                self._player.on("track_changed", self._on_track_changed)
                log.info("Player bridge initialized (mpv)")
            except Exception:
                log.warning("AudioPlayer init failed", exc_info=True)
                self._player = None

    @property
    def available(self) -> bool:
        return self._player is not None

    @property
    def state(self):
        if self._player:
            return self._player.state
        return None

    @property
    def playlist(self) -> list[str]:
        if self._player:
            return self._player.playlist
        return []

    @property
    def current_index(self) -> int:
        if self._player:
            return self._player.current_index
        return -1

    def on(self, event: str, callback):
        self._callbacks.setdefault(event, []).append(callback)

    # ── Playback commands ─────────────────────────────────────────────

    def toggle_pause(self):
        if self._player:
            s = self._player.state
            if not s.playing:
                if self._player.playlist:
                    self._player.play_index(max(0, self._player.current_index))
            else:
                self._player.toggle_pause()

    def next(self):
        if self._player:
            self._player.next()

    def prev(self):
        if self._player:
            self._player.prev()

    def stop(self):
        if self._player:
            self._player.stop()

    def seek(self, seconds: float, absolute: bool = False):
        if self._player:
            self._player.seek(seconds, absolute=absolute)

    def set_volume(self, vol: int):
        if self._player:
            self._player.set_volume(max(0, min(100, vol)))

    def load(self, path: str):
        """Load a file or directory into the playlist."""
        if not self._player:
            return
        p = Path(path).expanduser().resolve()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
            self._player.load_files([str(p)])
        elif p.is_dir():
            files = sorted(
                str(f) for f in p.rglob("*")
                if f.suffix.lower() in SUPPORTED_EXTENSIONS
            )
            if files:
                self._player.load_files(files)

    def add(self, path: str):
        """Add file or directory to current playlist."""
        if not self._player:
            return
        p = Path(path).expanduser().resolve()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
            self._player.add_files([str(p)])
        elif p.is_dir():
            files = sorted(
                str(f) for f in p.rglob("*")
                if f.suffix.lower() in SUPPORTED_EXTENSIONS
            )
            if files:
                self._player.add_files(files)

    def clear(self):
        if self._player:
            self._player.clear_playlist()

    def goto(self, index: int):
        if self._player:
            self._player.play_index(index)

    def shutdown(self):
        if self._player:
            self._player.shutdown()
            self._player = None

    # ── Event bridging (mpv thread → asyncio) ─────────────────────────

    def _on_state_changed(self):
        self._fire("state_changed")

    def _on_track_changed(self):
        self._fire("track_changed")

    def _fire(self, event: str):
        if not self._loop:
            return
        for cb in self._callbacks.get(event, []):
            self._loop.call_soon_threadsafe(cb)
