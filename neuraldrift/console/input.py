"""Input handler — vi-style modal key capture using prompt_toolkit."""

import asyncio
import logging
from collections import deque
from enum import Enum
from typing import Callable, Awaitable

from prompt_toolkit.input import create_input
from prompt_toolkit.keys import Keys

log = logging.getLogger(__name__)


class InputMode(Enum):
    NORMAL = "normal"
    COMMAND = "command"


class InputHandler:
    """Vi-style modal input: NORMAL for hotkeys, COMMAND for typed commands."""

    def __init__(self):
        self.mode = InputMode.NORMAL
        self.buffer = ""
        self.history: deque[str] = deque(maxlen=50)
        self._history_idx = -1
        self.on_hotkey: Callable[[str], None] | None = None
        self.on_command: Callable[[str], Awaitable | None] | None = None
        self._pt_input = None
        self._raw_ctx = None
        self._attach_handle = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self, loop: asyncio.AbstractEventLoop):
        """Enter raw mode and attach to asyncio event loop."""
        self._loop = loop
        self._pt_input = create_input()
        self._raw_ctx = self._pt_input.raw_mode()
        self._raw_ctx.__enter__()
        self._attach_handle = self._pt_input.attach(self._keys_ready)

    def stop(self):
        """Exit raw mode and detach."""
        if self._attach_handle:
            self._attach_handle.detach()
            self._attach_handle = None
        if self._raw_ctx:
            try:
                self._raw_ctx.__exit__(None, None, None)
            except Exception:
                pass
            self._raw_ctx = None
        self._pt_input = None

    @property
    def prompt_text(self) -> str:
        """Current footer display text."""
        if self.mode == InputMode.COMMAND:
            return f"[bold]:[/]{self.buffer}[blink]_[/]"
        return "[dim]Press : for command mode, ? for help[/]"

    @property
    def hint_text(self) -> str:
        """Hotkey hint bar."""
        if self.mode == InputMode.COMMAND:
            return "[Enter] execute  [Esc] cancel  [Tab] complete"
        return "[SPC]pause  [n/p]track  [+/-]vol  [:]cmd  [/]search  [?]help  [q]uit"

    def _keys_ready(self):
        """Called by prompt_toolkit when stdin has keys. Runs on asyncio loop thread."""
        if not self._pt_input:
            return
        for kp in self._pt_input.read_keys():
            self._process_key(kp)

    def _process_key(self, kp):
        key = kp.key

        if self.mode == InputMode.NORMAL:
            if key == ":":
                self.mode = InputMode.COMMAND
                self.buffer = ""
                self._history_idx = -1
            elif key == "/":
                self.mode = InputMode.COMMAND
                self.buffer = "search "
                self._history_idx = -1
            else:
                # Map key data for printable chars
                char = kp.data if hasattr(kp, "data") and kp.data else str(key)
                if self.on_hotkey and self._loop:
                    self._loop.call_soon_threadsafe(self.on_hotkey, char)

        elif self.mode == InputMode.COMMAND:
            if key == Keys.Escape or key == Keys.ControlC:
                self.mode = InputMode.NORMAL
                self.buffer = ""
            elif key == Keys.Enter or key == Keys.ControlJ:
                cmd = self.buffer.strip()
                self.mode = InputMode.NORMAL
                self.buffer = ""
                if cmd:
                    self.history.append(cmd)
                    self._history_idx = -1
                    if self.on_command and self._loop:
                        self._loop.call_soon_threadsafe(
                            lambda c=cmd: asyncio.ensure_future(self.on_command(c))
                        )
            elif key == Keys.Backspace or key == Keys.ControlH:
                self.buffer = self.buffer[:-1]
            elif key == Keys.Up:
                # History navigation
                if self.history:
                    if self._history_idx == -1:
                        self._history_idx = len(self.history) - 1
                    elif self._history_idx > 0:
                        self._history_idx -= 1
                    self.buffer = self.history[self._history_idx]
            elif key == Keys.Down:
                if self._history_idx >= 0:
                    self._history_idx += 1
                    if self._history_idx >= len(self.history):
                        self._history_idx = -1
                        self.buffer = ""
                    else:
                        self.buffer = self.history[self._history_idx]
            else:
                # Printable character
                data = kp.data if hasattr(kp, "data") and kp.data else ""
                if data and data.isprintable():
                    self.buffer += data
