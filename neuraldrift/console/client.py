"""BrainSocketClient — async Unix socket client for NeuralDrift server."""

import asyncio
import json
import logging
import uuid

log = logging.getLogger(__name__)


class BrainSocketClient:
    """Async client for NeuralDrift brain server over Unix domain socket."""

    def __init__(self, sock_path: str, reconnect_interval: float = 5.0):
        self._sock_path = sock_path
        self._reconnect_interval = reconnect_interval
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._running = False
        self._connected = False
        self._pending: dict[str, asyncio.Future] = {}
        self._callbacks: dict[str, list] = {
            "connected": [],
            "disconnected": [],
            "event": [],
        }

    @property
    def is_connected(self) -> bool:
        return self._connected

    def on(self, event_name: str, callback):
        """Register a callback: 'connected', 'disconnected', 'event'."""
        if event_name in self._callbacks:
            self._callbacks[event_name].append(callback)

    async def connect_and_read(self):
        """Connect, subscribe, read events. Auto-reconnects on disconnect."""
        self._running = True
        while self._running:
            try:
                await self._connect()
                await self._read_loop()
            except (ConnectionRefusedError, FileNotFoundError, OSError) as e:
                if self._connected:
                    self._connected = False
                    self._fire("disconnected")
                log.debug("Connection failed: %s", e)
            except asyncio.CancelledError:
                break

            if not self._running:
                break

            # Wait before reconnect
            await asyncio.sleep(self._reconnect_interval)

        self._cleanup()

    async def _connect(self):
        self._reader, self._writer = await asyncio.open_unix_connection(self._sock_path)
        self._connected = True
        log.info("Connected to brain server at %s", self._sock_path)
        self._fire("connected")

        # Subscribe to all events
        await self.send("subscribe")

    async def _read_loop(self):
        while self._running and self._reader:
            line = await self._reader.readline()
            if not line:
                break
            self._dispatch(line)

        # Disconnected
        if self._connected:
            self._connected = False
            self._fire("disconnected")

    def _dispatch(self, line: bytes):
        try:
            msg = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

        msg_type = msg.get("type", "")

        if msg_type == "response":
            req_id = msg.get("id", "")
            if req_id in self._pending:
                fut = self._pending.pop(req_id)
                if msg.get("ok"):
                    fut.set_result(msg.get("result"))
                else:
                    fut.set_result({"error": msg.get("error", "unknown")})
        elif msg_type == "event":
            self._fire("event", msg.get("event", ""), msg.get("data", {}))

    async def call(self, method: str, timeout: float = 5.0, **params) -> dict | list | None:
        """Send request and wait for response."""
        if not self._connected or not self._writer:
            return None
        req_id = f"req-{uuid.uuid4().hex[:8]}"
        msg = {"id": req_id, "method": method, "params": params}

        fut = asyncio.get_running_loop().create_future()
        self._pending[req_id] = fut

        self._writer.write(json.dumps(msg, separators=(",", ":")).encode() + b"\n")
        await self._writer.drain()

        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            log.warning("Timeout: %s (%s)", method, req_id)
            return None

    async def send(self, method: str, **params):
        """Fire-and-forget send."""
        if not self._connected or not self._writer:
            return
        req_id = f"req-{uuid.uuid4().hex[:8]}"
        msg = {"id": req_id, "method": method, "params": params}
        self._writer.write(json.dumps(msg, separators=(",", ":")).encode() + b"\n")
        await self._writer.drain()

    async def close(self):
        """Graceful disconnect."""
        self._running = False
        self._cleanup()

    def _cleanup(self):
        if self._writer:
            try:
                self._writer.close()
            except Exception:
                pass
            self._writer = None
        self._reader = None
        self._connected = False
        # Cancel pending futures
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()

    def _fire(self, event_name: str, *args):
        for cb in self._callbacks.get(event_name, []):
            try:
                cb(*args)
            except Exception:
                log.debug("Callback error for %s", event_name, exc_info=True)
