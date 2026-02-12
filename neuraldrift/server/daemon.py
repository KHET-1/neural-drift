"""BrainServer — asyncio daemon serving Brain over Unix domain socket."""

import asyncio
import io
import logging
import os
import signal
import sys
import time
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from neuraldrift.brain import Brain
from .protocol import encode_response, encode_event, decode_message
from .wrappers import stats_data, level_data, heatmap_data, topics_data

log = logging.getLogger(__name__)

SOCK_DIR = Path.home() / ".neuraldrift"
SOCK_PATH = SOCK_DIR / "brain.sock"
PID_PATH = SOCK_DIR / "braind.pid"
HEARTBEAT_INTERVAL = 30  # seconds


class BrainServer:
    """Asyncio server wrapping a single Brain instance."""

    def __init__(self):
        self._brain: Brain | None = None
        self._server: asyncio.AbstractServer | None = None
        self._clients: set[asyncio.StreamWriter] = set()
        self._heartbeat_task: asyncio.Task | None = None
        self._running = False

    # ── Method whitelist ──────────────────────────────────────────────

    # Maps method name → (handler_callable, is_mutating)
    # Handlers receive (brain, params) and return a result.
    def _build_methods(self) -> dict:
        b = self._brain
        return {
            # Meta
            "ping":    (lambda _b, _p: {"pong": True, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}, False),
            "info":    (lambda _b, _p: {"version": "1.0.0", "pid": os.getpid(), "clients": len(self._clients)}, False),
            "subscribe": (lambda _b, _p: {"subscribed": True}, False),

            # Knowledge
            "learn":   (self._handle_learn, True),
            "recall":  (self._handle_recall, False),
            "search":  (self._handle_search, False),
            "associate": (self._handle_associate, False),
            "verify":  (self._handle_verify, True),
            "forget":  (self._handle_forget, True),
            "muse":    (self._handle_muse, True),

            # Status
            "stats":   (lambda _b, _p: stats_data(_b), False),
            "level":   (lambda _b, _p: level_data(_b), False),
            "heatmap": (lambda _b, _p: heatmap_data(_b), False),
            "topics":  (lambda _b, _p: topics_data(_b), False),

            # Agents
            "agent_checkin":  (self._handle_agent_checkin, True),
            "agent_checkout": (self._handle_agent_checkout, True),
            "agent_roster":   (self._handle_agent_roster, False),
            "agent_stats":    (self._handle_agent_stats, False),

            # Scouts
            "scout_dispatch": (self._handle_scout_dispatch, True),
            "scout_return":   (self._handle_scout_return, True),
            "scout_absorb":   (self._handle_scout_absorb, True),
            "scout_status":   (self._handle_scout_status, False),
            "scout_pending":  (self._handle_scout_pending, False),
        }

    # ── Knowledge handlers ────────────────────────────────────────────

    def _handle_learn(self, brain, params: dict):
        topic = params.get("topic", "")
        fact = params.get("fact", "")
        if not topic or not fact:
            raise ValueError("topic and fact are required")
        confidence = params.get("confidence", 80)
        source = params.get("source", "neuraldrift")
        verified = params.get("verified", False)
        _call_silent(brain.learn, topic, fact, confidence=confidence, source=source, verified=verified)
        return {"learned": True, "topic": topic}

    def _handle_recall(self, brain, params: dict):
        topic = params.get("topic")
        limit = params.get("limit")
        # recall() prints output — capture and extract data from db directly
        facts = brain.db.get("facts", {})
        if topic:
            entries = facts.get(topic, [])
        else:
            entries = [f for fl in facts.values() for f in fl]
        if limit:
            entries = entries[:limit]
        return [_fact_to_dict(f) for f in entries]

    def _handle_search(self, brain, params: dict):
        keyword = params.get("keyword", "")
        limit = params.get("limit")
        if not keyword:
            raise ValueError("keyword is required")
        results = []
        for topic, entries in brain.db.get("facts", {}).items():
            for f in entries:
                if keyword.lower() in f.get("fact", "").lower():
                    d = _fact_to_dict(f)
                    d["topic"] = topic
                    results.append(d)
        if limit:
            results = results[:limit]
        return results

    def _handle_associate(self, brain, params: dict):
        text = params.get("text", "")
        if not text:
            raise ValueError("text is required")
        # Extract keywords and search
        words = set(text.lower().split())
        results = []
        for topic, entries in brain.db.get("facts", {}).items():
            for f in entries:
                fact_words = set(f.get("fact", "").lower().split())
                overlap = words & fact_words
                if len(overlap) >= 2 or topic.lower() in text.lower():
                    d = _fact_to_dict(f)
                    d["topic"] = topic
                    d["relevance"] = len(overlap)
                    results.append(d)
        results.sort(key=lambda x: x.get("relevance", 0), reverse=True)
        return results[:10]

    def _handle_verify(self, brain, params: dict):
        topic = params.get("topic", "")
        fact_sub = params.get("fact_substring", "")
        new_conf = params.get("new_confidence")
        if not topic or not fact_sub:
            raise ValueError("topic and fact_substring are required")
        _call_silent(brain.verify, topic, fact_sub, new_confidence=new_conf)
        return {"verified": True, "topic": topic}

    def _handle_forget(self, brain, params: dict):
        topic = params.get("topic", "")
        fact_sub = params.get("fact_substring", "")
        if not topic or not fact_sub:
            raise ValueError("topic and fact_substring are required")
        _call_silent(brain.forget, topic, fact_sub)
        return {"forgotten": True, "topic": topic}

    def _handle_muse(self, brain, params: dict):
        note = params.get("note", "")
        tags = params.get("tags")
        if not note:
            raise ValueError("note is required")
        _call_silent(brain.muse, note, tags=tags)
        return {"mused": True}

    # ── Agent handlers ────────────────────────────────────────────────

    def _handle_agent_checkin(self, brain, params: dict):
        role = params.get("role", "")
        task = params.get("task", "")
        if not role or not task:
            raise ValueError("role and task are required")
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(io.StringIO()):
            result = brain.agent_checkin(role, task)
        # result is (id, name) or (id, name, speed)
        if isinstance(result, tuple):
            agent_id = result[0]
            agent_name = result[1] if len(result) > 1 else "Unknown"
            return {"agent_id": agent_id, "agent_name": agent_name}
        return {"agent_id": result}

    def _handle_agent_checkout(self, brain, params: dict):
        agent_id = params.get("agent_id")
        status = params.get("status", "done")
        result = params.get("result", "")
        if agent_id is None:
            raise ValueError("agent_id is required")
        _call_silent(brain.agent_checkout, agent_id, status=status, result=result)
        return {"checked_out": True, "agent_id": agent_id}

    def _handle_agent_roster(self, brain, params: dict):
        roster = brain.db.get("agents", {}).get("roster", [])
        show_all = params.get("show_all", False)
        if not show_all:
            roster = [a for a in roster if a.get("status") == "active"]
        return roster

    def _handle_agent_stats(self, brain, params: dict):
        agents = brain.db.get("agents", {})
        roster = agents.get("roster", [])
        return {
            "total": len(roster),
            "active": len([a for a in roster if a.get("status") == "active"]),
            "completed": len([a for a in roster if a.get("status") != "active"]),
            "next_id": agents.get("next_id", 1),
            "legends": list(agents.get("legends", {}).keys()),
        }

    # ── Scout handlers ────────────────────────────────────────────────

    def _handle_scout_dispatch(self, brain, params: dict):
        topic = params.get("topic", "")
        context = params.get("context", "")
        priority = params.get("priority", "normal")
        if not topic:
            raise ValueError("topic is required")
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(io.StringIO()):
            result = brain.scout_dispatch(topic, context, priority=priority)
        return {"dispatched": True, "scout_id": result}

    def _handle_scout_return(self, brain, params: dict):
        scout_id = params.get("scout_id")
        findings = params.get("findings", "")
        quality = params.get("quality", "solid")
        if scout_id is None:
            raise ValueError("scout_id is required")
        _call_silent(brain.scout_return, scout_id, findings, quality=quality)
        return {"returned": True, "scout_id": scout_id}

    def _handle_scout_absorb(self, brain, params: dict):
        scout_id = params.get("scout_id")
        auto_learn = params.get("auto_learn", True)
        if scout_id is None:
            raise ValueError("scout_id is required")
        _call_silent(brain.scout_absorb, scout_id, auto_learn=auto_learn)
        return {"absorbed": True, "scout_id": scout_id}

    def _handle_scout_status(self, brain, params: dict):
        scouts = brain.db.get("scouts", [])
        return {
            "total": len(scouts),
            "pending": len([s for s in scouts if s.get("status") == "dispatched"]),
            "returned": len([s for s in scouts if s.get("status") == "returned"]),
            "absorbed": len([s for s in scouts if s.get("status") == "absorbed"]),
        }

    def _handle_scout_pending(self, brain, params: dict):
        scouts = brain.db.get("scouts", [])
        return [s for s in scouts if s.get("status") in ("dispatched", "returned")]

    # ── Client handler ────────────────────────────────────────────────

    async def _client_handler(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        peer = writer.get_extra_info("peername") or "unknown"
        log.info("Client connected: %s", peer)
        self._clients.add(writer)

        methods = self._build_methods()

        try:
            while self._running:
                line = await reader.readline()
                if not line:
                    break  # client disconnected

                msg = decode_message(line)
                if not msg:
                    continue

                req_id = msg.get("id", "?")
                method = msg.get("method", "")
                params = msg.get("params", {})

                if method not in methods:
                    writer.write(encode_response(req_id, error=f"unknown method: {method}"))
                    await writer.drain()
                    continue

                handler, is_mutating = methods[method]

                # Snapshot XP before call to detect changes
                xp_before = self._brain.db.get("meta", {}).get("xp", 0)
                level_before = self._brain.db.get("meta", {}).get("level", 0)

                try:
                    result = handler(self._brain, params)
                    writer.write(encode_response(req_id, result=result))
                    await writer.drain()
                except Exception as e:
                    log.exception("Handler error: %s", method)
                    writer.write(encode_response(req_id, error=str(e)))
                    await writer.drain()
                    continue

                # Broadcast events for mutating calls
                if is_mutating:
                    xp_after = self._brain.db.get("meta", {}).get("xp", 0)
                    level_after = self._brain.db.get("meta", {}).get("level", 0)

                    if method == "learn":
                        await self._broadcast(encode_event("fact_learned", {
                            "topic": params.get("topic", ""),
                            "fact": params.get("fact", ""),
                        }))

                    if method == "agent_checkin":
                        await self._broadcast(encode_event("agent_spawned", {
                            "agent_id": result.get("agent_id") if isinstance(result, dict) else result,
                            "agent_name": result.get("agent_name", "") if isinstance(result, dict) else "",
                        }))

                    if method == "agent_checkout":
                        await self._broadcast(encode_event("agent_completed", {
                            "agent_id": params.get("agent_id"),
                            "status": params.get("status", "done"),
                        }))

                    if xp_after != xp_before:
                        await self._broadcast(encode_event("xp_changed", {
                            "delta": xp_after - xp_before,
                            "total": xp_after,
                        }))

                    if level_after > level_before:
                        await self._broadcast(encode_event("level_up", {
                            "level": level_after,
                            "title": level_data(self._brain).get("title", ""),
                        }))

        except (ConnectionResetError, BrokenPipeError):
            pass
        except asyncio.CancelledError:
            pass
        finally:
            self._clients.discard(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            log.info("Client disconnected: %s", peer)

    # ── Broadcast ─────────────────────────────────────────────────────

    async def _broadcast(self, data: bytes):
        dead = []
        for writer in self._clients:
            try:
                writer.write(data)
                await writer.drain()
            except (ConnectionResetError, BrokenPipeError, OSError):
                dead.append(writer)
        for w in dead:
            self._clients.discard(w)

    # ── Heartbeat ─────────────────────────────────────────────────────

    async def _heartbeat_loop(self):
        try:
            while self._running:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                if not self._running:
                    break
                data = stats_data(self._brain)
                data["clients"] = len(self._clients)
                await self._broadcast(encode_event("heartbeat", data))
        except asyncio.CancelledError:
            pass

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self):
        """Start the brain server."""
        SOCK_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)

        # Clean stale socket
        if SOCK_PATH.exists():
            SOCK_PATH.unlink()

        # Initialize brain
        log.info("Loading Brain...")
        self._brain = Brain()
        log.info("Brain loaded: %d facts, %d XP, level %d",
                 sum(len(v) for v in self._brain.db.get("facts", {}).values()),
                 self._brain.db.get("meta", {}).get("xp", 0),
                 self._brain.db.get("meta", {}).get("level", 0))

        self._running = True

        # Create unix socket server
        self._server = await asyncio.start_unix_server(
            self._client_handler, path=str(SOCK_PATH)
        )
        os.chmod(SOCK_PATH, 0o600)

        # Write PID file
        PID_PATH.write_text(str(os.getpid()))
        PID_PATH.chmod(0o600)

        # Start heartbeat
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        log.info("NeuralDrift server listening on %s (PID %d)", SOCK_PATH, os.getpid())

    async def stop(self):
        """Graceful shutdown."""
        log.info("Shutting down NeuralDrift server...")
        self._running = False

        # Cancel heartbeat
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # Close all clients
        for writer in list(self._clients):
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
        self._clients.clear()

        # Stop server
        if self._server:
            self._server.close()
            await self._server.wait_closed()

        # Save brain
        if self._brain:
            log.info("Saving brain state...")
            self._brain.save()

        # Cleanup files
        if SOCK_PATH.exists():
            SOCK_PATH.unlink()
        if PID_PATH.exists():
            PID_PATH.unlink()

        log.info("NeuralDrift server stopped.")

    async def run_forever(self):
        """Start and run until signal."""
        await self.start()

        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        def _signal_handler():
            stop_event.set()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _signal_handler)

        print(f"NeuralDrift server running on {SOCK_PATH} (PID {os.getpid()})")
        print("Press Ctrl+C to stop.")

        await stop_event.wait()
        await self.stop()


# ── Helpers ───────────────────────────────────────────────────────────

def _call_silent(func, *args, **kwargs):
    """Call a Brain method while suppressing its stdout/stderr output."""
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(io.StringIO()):
        return func(*args, **kwargs)


def _fact_to_dict(f: dict) -> dict:
    """Convert a raw fact entry to a clean response dict."""
    return {
        "fact": f.get("fact", ""),
        "confidence": f.get("confidence", 0),
        "source": f.get("source", ""),
        "verified": f.get("verified", False),
        "learned": f.get("learned", ""),
        "times_recalled": f.get("times_recalled", 0),
    }
