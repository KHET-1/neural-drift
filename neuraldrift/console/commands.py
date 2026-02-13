"""Command registry — parse and dispatch typed commands."""

import logging

log = logging.getLogger(__name__)

# Help text
HELP_TEXT = [
    "[bold cyan]Brain Commands[/]",
    "  search <keyword>          Search facts by keyword",
    "  recall <topic> [limit]    Recall facts from a topic",
    "  learn <topic> | <fact>    Learn a new fact",
    "  topics                    List all topics",
    "  stats                     Show full brain stats",
    "  heatmap                   Show full topic heatmap",
    "  muse <note>               Record a musing",
    "  agents                    Show full agent roster",
    "  scouts                    Show scout status",
    "  associate <text>          Find associated facts",
    "",
    "[bold green]Player Commands[/]",
    "  play <path>               Load file or directory",
    "  add <path>                Add to playlist",
    "  playlist                  Show full playlist",
    "  clear                     Clear playlist and stop",
    "  goto <N>                  Jump to track number",
    "  vol <N>                   Set volume (0-100)",
    "  seek <+/-seconds>         Seek relative",
    "",
    "[bold]System Commands[/]",
    "  help                      This help",
    "  reconnect                 Reconnect to brain server",
    "  quit / q                  Exit console",
]


class CommandRegistry:
    """Parses and dispatches typed commands."""

    def __init__(self, app):
        self._app = app

    async def execute(self, raw_cmd: str):
        """Parse and dispatch a command string."""
        parts = raw_cmd.strip().split(None, 1)
        if not parts:
            return
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        handler = getattr(self, f"_cmd_{cmd}", None)
        if handler:
            try:
                await handler(args)
            except Exception as e:
                self._app.log_event("error", f"Command error: {e}")
        else:
            self._app.log_event("error", f"Unknown command: {cmd}")

    # ── Brain commands ────────────────────────────────────────────────

    async def _cmd_search(self, args: str):
        if not args:
            self._app.log_event("error", "Usage: search <keyword>")
            return
        result = await self._app.client.call("search", keyword=args, limit=10)
        if result is None:
            self._app.log_event("error", "Server not connected")
            return
        if isinstance(result, dict) and "error" in result:
            self._app.log_event("error", result["error"])
            return
        if not result:
            self._app.log_event("info", f"No results for '{args}'")
            return
        self._app.log_event("cmd", f"search {args} -> {len(result)} results")
        for i, f in enumerate(result[:8], 1):
            conf = f.get("confidence", 0)
            topic = f.get("topic", "")
            fact = f.get("fact", "")[:60]
            self._app.log_event("info", f"  [{i}] {topic}: {fact} ({conf}%)")

    async def _cmd_recall(self, args: str):
        parts = args.split(None, 1)
        if not parts:
            self._app.log_event("error", "Usage: recall <topic> [limit]")
            return
        topic = parts[0]
        limit = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 5
        result = await self._app.client.call("recall", topic=topic, limit=limit)
        if result is None:
            self._app.log_event("error", "Server not connected")
            return
        if isinstance(result, dict) and "error" in result:
            self._app.log_event("error", result["error"])
            return
        if not result:
            self._app.log_event("info", f"No facts for '{topic}'")
            return
        self._app.log_event("cmd", f"recall {topic} -> {len(result)} facts")
        for f in result:
            conf = f.get("confidence", 0)
            fact = f.get("fact", "")[:65]
            self._app.log_event("info", f"  {fact} ({conf}%)")

    async def _cmd_learn(self, args: str):
        if "|" not in args:
            self._app.log_event("error", "Usage: learn <topic> | <fact>")
            return
        topic, fact = args.split("|", 1)
        topic = topic.strip()
        fact = fact.strip()
        if not topic or not fact:
            self._app.log_event("error", "Both topic and fact are required")
            return
        result = await self._app.client.call("learn", topic=topic, fact=fact, source="console")
        if result is None:
            self._app.log_event("error", "Server not connected")
            return
        if isinstance(result, dict) and result.get("learned"):
            self._app.log_event("success", f"Learned: {topic}/{fact[:40]}")
        else:
            self._app.log_event("error", f"Learn failed: {result}")

    async def _cmd_topics(self, args: str):
        result = await self._app.client.call("topics")
        if result is None:
            self._app.log_event("error", "Server not connected")
            return
        if not result:
            self._app.log_event("info", "No topics yet")
            return
        self._app.log_event("cmd", f"Topics ({len(result)}): {', '.join(result)}")

    async def _cmd_stats(self, args: str):
        result = await self._app.client.call("stats")
        if result is None:
            self._app.log_event("error", "Server not connected")
            return
        self._app.log_event("cmd", f"Stats: {result.get('facts',0)} facts, {result.get('xp',0)} XP, "
                           f"Lv{result.get('level',0)} {result.get('title','')}, "
                           f"{result.get('topics',0)} topics, {result.get('agents_total',0)} agents")

    async def _cmd_heatmap(self, args: str):
        result = await self._app.client.call("heatmap")
        if result is None:
            self._app.log_event("error", "Server not connected")
            return
        if not result:
            self._app.log_event("info", "No heatmap data")
            return
        self._app.log_event("cmd", f"Heatmap ({len(result)} topics)")
        for topic, temp in sorted(result.items(), key=lambda x: x[1], reverse=True)[:12]:
            self._app.log_event("info", f"  {topic}: {temp:.1f}")

    async def _cmd_muse(self, args: str):
        if not args:
            self._app.log_event("error", "Usage: muse <note>")
            return
        result = await self._app.client.call("muse", note=args)
        if result is None:
            self._app.log_event("error", "Server not connected")
            return
        self._app.log_event("success", "Musing recorded")

    async def _cmd_agents(self, args: str):
        result = await self._app.client.call("agent_roster", show_all=True)
        if result is None:
            self._app.log_event("error", "Server not connected")
            return
        if not result:
            self._app.log_event("info", "No agents")
            return
        self._app.log_event("cmd", f"Agent roster ({len(result)})")
        for a in result[-10:]:
            self._app.log_event("info", f"  #{a.get('id','?')} {a.get('name','?')} "
                               f"[{a.get('status','?')}] {a.get('task','')[:40]}")

    async def _cmd_scouts(self, args: str):
        result = await self._app.client.call("scout_status")
        if result is None:
            self._app.log_event("error", "Server not connected")
            return
        self._app.log_event("cmd", f"Scouts: {result.get('total',0)} total, "
                           f"{result.get('pending',0)} pending, "
                           f"{result.get('returned',0)} returned, "
                           f"{result.get('absorbed',0)} absorbed")

    async def _cmd_associate(self, args: str):
        if not args:
            self._app.log_event("error", "Usage: associate <text>")
            return
        result = await self._app.client.call("associate", text=args)
        if result is None:
            self._app.log_event("error", "Server not connected")
            return
        if not result:
            self._app.log_event("info", "No associations found")
            return
        self._app.log_event("cmd", f"Associations for '{args[:20]}' -> {len(result)} matches")
        for f in result[:6]:
            self._app.log_event("info", f"  [{f.get('topic','')}] {f.get('fact','')[:50]}")

    # ── Player commands ───────────────────────────────────────────────

    async def _cmd_play(self, args: str):
        if not self._app.player or not self._app.player.available:
            self._app.log_event("error", "Player not available")
            return
        if not args:
            self._app.player.toggle_pause()
            return
        self._app.player.load(args)
        self._app.log_event("success", f"Loading: {args}")

    async def _cmd_add(self, args: str):
        if not self._app.player or not self._app.player.available:
            self._app.log_event("error", "Player not available")
            return
        if not args:
            self._app.log_event("error", "Usage: add <path>")
            return
        self._app.player.add(args)
        self._app.log_event("success", f"Added: {args}")

    async def _cmd_playlist(self, args: str):
        if not self._app.player or not self._app.player.available:
            self._app.log_event("error", "Player not available")
            return
        pl = self._app.player.playlist
        if not pl:
            self._app.log_event("info", "Playlist empty")
            return
        self._app.log_event("cmd", f"Playlist ({len(pl)} tracks)")
        for i, p in enumerate(pl):
            from pathlib import Path
            name = Path(p).stem
            marker = ">" if i == self._app.player.current_index else " "
            self._app.log_event("info", f"  {marker} {i + 1:3d}. {name}")

    async def _cmd_clear(self, args: str):
        if not self._app.player or not self._app.player.available:
            self._app.log_event("error", "Player not available")
            return
        self._app.player.clear()
        self._app.log_event("success", "Playlist cleared")

    async def _cmd_goto(self, args: str):
        if not self._app.player or not self._app.player.available:
            self._app.log_event("error", "Player not available")
            return
        try:
            idx = int(args) - 1
            self._app.player.goto(idx)
            self._app.log_event("success", f"Jumping to track {idx + 1}")
        except ValueError:
            self._app.log_event("error", "Usage: goto <track_number>")

    async def _cmd_vol(self, args: str):
        if not self._app.player or not self._app.player.available:
            self._app.log_event("error", "Player not available")
            return
        try:
            vol = int(args)
            self._app.player.set_volume(vol)
            self._app.log_event("info", f"Volume: {vol}%")
        except ValueError:
            self._app.log_event("error", "Usage: vol <0-100>")

    async def _cmd_seek(self, args: str):
        if not self._app.player or not self._app.player.available:
            self._app.log_event("error", "Player not available")
            return
        try:
            secs = float(args)
            self._app.player.seek(secs)
            self._app.log_event("info", f"Seek: {'+' if secs > 0 else ''}{secs}s")
        except ValueError:
            self._app.log_event("error", "Usage: seek <+/-seconds>")

    # ── System commands ───────────────────────────────────────────────

    async def _cmd_help(self, args: str):
        for line in HELP_TEXT:
            self._app.log_event("info", line)

    async def _cmd_quit(self, args: str):
        await self._app.quit()

    async def _cmd_q(self, args: str):
        await self._app.quit()

    async def _cmd_reconnect(self, args: str):
        self._app.log_event("info", "Reconnecting to brain server...")
        await self._app.client.close()
        asyncio.ensure_future(self._app.client.connect_and_read())
