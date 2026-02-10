"""
human_brain.py — The Human Brain: personal thoughts, ideas, stories, and creative sparks.
The companion to the AI Brain (brain.py).

While the AI Brain stores machine intelligence — facts, confidence, citations, agents —
the Human Brain stores the human side — thoughts, dreams, stories, rants, connections.
No confidence scores. No XP decay. No verification. Just raw humanity.

CONSENT RULE: Nothing enters the Human Brain without explicit permission.
    - Once per session: user is prompted if they'd like to share a story or thought
    - If something comes up in passing, ASK before storing
    - All proposed entries go through a staging area (pending) before commit
    - The AI never assumes it understands the human's inner world

Structure:
    Thoughts   — quick captures, fleeting ideas, shower thoughts
    Stories    — longer narratives, experiences, memories
    Ideas      — actionable concepts, project seeds, what-ifs
    Connections— links between thoughts ("this reminds me of...")
    Moods      — emotional state tracking over time
    Journal    — dated entries, like a diary
    Pending    — staging area: proposed entries awaiting human approval

Usage:
    from neuraldrift.human_brain import HumanBrain

    hb = HumanBrain()

    # Direct writes (human explicitly asked to store):
    hb.think("What if we could see Wi-Fi signals as colors?")
    hb.idea("Build a tool that visualizes network traffic as a city skyline")

    # Proposed writes (AI noticed something, asks permission):
    hb.propose("thought", "You mentioned loving the sound of rain on servers")
    hb.pending()         # see what's waiting for approval
    hb.approve(0)        # approve entry 0
    hb.reject(0)         # reject entry 0
    hb.approve_all()     # approve everything

    # Session prompt (run once per session):
    hb.session_prompt()  # "Anything on your mind today?"
"""

import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path

from .output import C, success, warning, info, header

# ═══════════════════════════════════════
# STORAGE
# ═══════════════════════════════════════

HUMAN_DIR = Path.home() / ".neuraldrift"
HUMAN_DB = HUMAN_DIR / "human_brain.json"


def _atomic_save(data, filepath):
    """Atomic JSON write."""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(filepath.parent), prefix=".hb_", suffix=".tmp")
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(filepath))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _atomic_load(filepath, fallback=None):
    """Load JSON with backup recovery."""
    filepath = Path(filepath)
    if filepath.exists():
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            backup = filepath.with_suffix(filepath.suffix + ".bak")
            if backup.exists():
                try:
                    with open(backup, 'r') as f:
                        return json.load(f)
                except Exception:
                    pass
    return fallback


# ═══════════════════════════════════════
# HUMAN BRAIN
# ═══════════════════════════════════════

class HumanBrain:
    """
    The human side of the dual-brain system.
    Stores thoughts, ideas, stories, connections, moods, and journal entries.
    No XP. No levels. No decay. Just your mind, persisted.
    """

    def __init__(self):
        self.db = self._load()

    def _load(self):
        data = _atomic_load(HUMAN_DB)
        if data:
            return data
        return {
            "meta": {
                "created": self._ts(),
                "owner": None,
                "motto": None,
                "session_prompted": None,  # last session prompt date
            },
            "thoughts": [],
            "ideas": [],
            "stories": [],
            "connections": [],
            "moods": [],
            "journal": [],
            "pending": [],  # staging area for consent
        }

    def save(self):
        """Persist human brain atomically with backup."""
        if HUMAN_DB.exists():
            import shutil
            backup = HUMAN_DB.with_suffix(".json.bak")
            try:
                shutil.copy2(str(HUMAN_DB), str(backup))
            except OSError:
                pass
        self.db["meta"]["last_saved"] = self._ts()
        _atomic_save(self.db, HUMAN_DB)

    # ─── Consent & Staging ──────────────────

    def propose(self, entry_type, content, context=""):
        """
        Propose an entry for the human brain — goes to staging, NOT directly in.
        The AI uses this when it notices something about the human but needs permission.

        Args:
            entry_type: "thought" | "idea" | "story" | "connection" | "mood"
            content: The proposed content
            context: Why the AI is proposing this (what triggered it)
        """
        pending = self.db.setdefault("pending", [])
        entry = {
            "type": entry_type,
            "content": content,
            "context": context,
            "proposed": self._ts(),
            "status": "pending",  # pending → approved → rejected
        }
        pending.append(entry)
        self.save()
        print(f"  {C.YELLOW}📋 Proposed [{entry_type}]:{C.RESET} {content[:60]}")
        print(f"     {C.DIM}Context: {context}{C.RESET}")
        print(f"     {C.DIM}Use hb.pending() to review, hb.approve(idx) to accept{C.RESET}")

    def pending(self):
        """Show all entries waiting for human approval."""
        items = [p for p in self.db.get("pending", []) if p["status"] == "pending"]
        if not items:
            info("Nothing pending. Your brain, your rules.")
            return

        header("PENDING APPROVAL")
        print(f"  {C.DIM}These were noticed by AI and need your OK to store.{C.RESET}\n")
        for i, p in enumerate(items):
            print(f"  {C.YELLOW}[{i}]{C.RESET} {C.BOLD}[{p['type']}]{C.RESET} {p['content'][:70]}")
            if p.get("context"):
                print(f"      {C.DIM}Why: {p['context']}{C.RESET}")
        print(f"\n  {C.DIM}hb.approve(idx) | hb.reject(idx) | hb.approve_all(){C.RESET}")

    def approve(self, index):
        """Approve a pending entry — moves it into the brain."""
        items = [p for p in self.db.get("pending", []) if p["status"] == "pending"]
        if index < 0 or index >= len(items):
            warning(f"Invalid index. {len(items)} items pending.")
            return

        entry = items[index]
        entry["status"] = "approved"
        entry["approved"] = self._ts()

        # Route to the right store
        t = entry["type"]
        content = entry["content"]

        if t == "thought":
            self.think(content)
        elif t == "idea":
            self.idea(content)
        elif t == "story":
            self.story(content, content)
        elif t == "mood":
            self.mood(content)
        else:
            self.think(content)  # fallback

        success(f"Approved and stored: [{t}]")

    def reject(self, index):
        """Reject a pending entry — it's gone."""
        items = [p for p in self.db.get("pending", []) if p["status"] == "pending"]
        if index < 0 or index >= len(items):
            warning(f"Invalid index. {len(items)} items pending.")
            return

        entry = items[index]
        entry["status"] = "rejected"
        entry["rejected"] = self._ts()
        self.save()
        info(f"Rejected: [{entry['type']}] {entry['content'][:50]}")

    def approve_all(self):
        """Approve everything in pending."""
        items = [p for p in self.db.get("pending", []) if p["status"] == "pending"]
        for i in range(len(items)):
            self.approve(0)  # always approve index 0 since list shifts

    def session_prompt(self):
        """
        Once-per-session prompt — gently asks if the human has anything to share.
        Returns True if already prompted today, False if first time.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        last_prompted = self.db["meta"].get("session_prompted")

        if last_prompted == today:
            return True  # Already prompted today

        self.db["meta"]["session_prompted"] = today
        self.save()

        owner = self.db["meta"].get("owner", "friend")
        header("HUMAN CHECK-IN")
        print(f"  {C.WHITE}Hey {owner} — anything on your mind today?{C.RESET}")
        print(f"  {C.DIM}A thought, a story, an idea? Anything you want to remember.{C.RESET}")
        print(f"  {C.DIM}(No pressure. Just checking in.){C.RESET}")
        print()
        return False

    # ─── Identity ───────────────────────────

    def introduce(self, name, motto=None):
        """Set the human owner of this brain."""
        self.db["meta"]["owner"] = name
        self.db["meta"]["motto"] = motto
        self.save()
        success(f"Human Brain belongs to: {name}")
        if motto:
            print(f"  {C.DIM}\"{motto}\"{C.RESET}")

    def whoami(self):
        """Who owns this brain?"""
        name = self.db["meta"].get("owner", "Unknown")
        motto = self.db["meta"].get("motto", "")
        thoughts = len(self.db.get("thoughts", []))
        ideas = len(self.db.get("ideas", []))
        stories = len(self.db.get("stories", []))
        journal = len(self.db.get("journal", []))

        header("HUMAN BRAIN")
        print(f"  {C.WHITE}{C.BOLD}{name}{C.RESET}")
        if motto:
            print(f"  {C.DIM}\"{motto}\"{C.RESET}")
        print()
        print(f"  {C.CYAN}Thoughts:{C.RESET} {thoughts}  {C.YELLOW}Ideas:{C.RESET} {ideas}  {C.MAGENTA}Stories:{C.RESET} {stories}  {C.GREEN}Journal:{C.RESET} {journal}")
        moods = self.db.get("moods", [])
        if moods:
            last = moods[-1]
            print(f"  {C.DIM}Last mood: {last['mood']} — \"{last.get('note', '')}\"{C.RESET}")

    # ─── Thoughts ───────────────────────────

    def think(self, thought, tags=None):
        """
        Capture a fleeting thought. Quick, raw, unfiltered.

        Args:
            thought: The thought itself
            tags: Optional list of tags for later retrieval
        """
        entry = {
            "thought": thought,
            "tags": tags or [],
            "when": self._ts(),
        }
        self.db["thoughts"].append(entry)
        self.save()
        print(f"  {C.CYAN}💭{C.RESET} {thought}")
        if tags:
            print(f"     {C.DIM}#{' #'.join(tags)}{C.RESET}")

    def thoughts(self, tag=None, limit=10):
        """Browse recent thoughts, optionally filtered by tag."""
        all_thoughts = self.db.get("thoughts", [])
        if tag:
            all_thoughts = [t for t in all_thoughts if tag.lower() in [x.lower() for x in t.get("tags", [])]]

        recent = all_thoughts[-limit:]
        if not recent:
            info("No thoughts captured yet. Use hb.think() to start.")
            return

        header(f"THOUGHTS{f' #{tag}' if tag else ''}")
        for t in reversed(recent):
            tags_str = f" {C.DIM}#{' #'.join(t['tags'])}{C.RESET}" if t.get("tags") else ""
            print(f"  {C.CYAN}💭{C.RESET} {t['thought']}{tags_str}")
            print(f"     {C.DIM}{t['when']}{C.RESET}")

    # ─── Ideas ──────────────────────────────

    def idea(self, title, description="", tags=None, priority="normal"):
        """
        Capture an actionable idea. Something you might build or do.

        Args:
            title: Short idea title
            description: Longer explanation
            tags: Optional tags
            priority: "low" | "normal" | "high" | "urgent"
        """
        entry = {
            "title": title,
            "description": description,
            "tags": tags or [],
            "priority": priority,
            "when": self._ts(),
            "status": "seed",  # seed → growing → bloomed → planted → archived
        }
        self.db["ideas"].append(entry)
        self.save()

        icons = {"low": "🌱", "normal": "💡", "high": "⚡", "urgent": "🔥"}
        print(f"  {icons.get(priority, '💡')} {C.YELLOW}{C.BOLD}{title}{C.RESET}")
        if description:
            print(f"     {C.DIM}{description[:80]}{C.RESET}")

    def ideas(self, status=None, limit=10):
        """Browse ideas, optionally by status."""
        all_ideas = self.db.get("ideas", [])
        if status:
            all_ideas = [i for i in all_ideas if i.get("status") == status]

        recent = all_ideas[-limit:]
        if not recent:
            info("No ideas yet. Use hb.idea() to plant one.")
            return

        status_icons = {"seed": "🌱", "growing": "🌿", "bloomed": "🌸", "planted": "🌳", "archived": "📦"}

        header("IDEAS")
        for i, idea in enumerate(reversed(recent)):
            icon = status_icons.get(idea.get("status", "seed"), "💡")
            pri = {"high": f"{C.RED}!", "urgent": f"{C.RED}!!", "low": f"{C.DIM}~"}.get(idea.get("priority"), "")
            print(f"  {icon} {C.YELLOW}{C.BOLD}{idea['title']}{C.RESET} {pri}{C.RESET}")
            if idea.get("description"):
                print(f"     {C.DIM}{idea['description'][:60]}{C.RESET}")

    def grow_idea(self, title_substring, new_status):
        """Evolve an idea: seed → growing → bloomed → planted → archived."""
        for idea in self.db.get("ideas", []):
            if title_substring.lower() in idea["title"].lower():
                old = idea["status"]
                idea["status"] = new_status
                idea["updated"] = self._ts()
                self.save()
                success(f"Idea evolved: {old} → {new_status}: {idea['title']}")
                return True
        warning(f"Idea not found: {title_substring}")
        return False

    # ─── Stories ────────────────────────────

    def story(self, title, text, tags=None):
        """
        Record a story, memory, or experience.

        Args:
            title: Story title
            text: The story text (can be long)
            tags: Optional tags
        """
        entry = {
            "title": title,
            "text": text,
            "tags": tags or [],
            "when": self._ts(),
        }
        self.db["stories"].append(entry)
        self.save()
        print(f"  {C.MAGENTA}📖{C.RESET} {C.BOLD}{title}{C.RESET}")
        print(f"     {C.DIM}{text[:100]}{'...' if len(text) > 100 else ''}{C.RESET}")

    def stories(self, limit=5):
        """Browse recent stories."""
        all_stories = self.db.get("stories", [])[-limit:]
        if not all_stories:
            info("No stories yet. Use hb.story() to write one.")
            return

        header("STORIES")
        for s in reversed(all_stories):
            print(f"\n  {C.MAGENTA}📖{C.RESET} {C.BOLD}{s['title']}{C.RESET} {C.DIM}({s['when']}){C.RESET}")
            # Show first 200 chars
            lines = s["text"][:200].split("\n")
            for line in lines:
                print(f"     {C.WHITE}{line}{C.RESET}")
            if len(s["text"]) > 200:
                print(f"     {C.DIM}... ({len(s['text'])} chars total){C.RESET}")

    # ─── Connections ────────────────────────

    def connect(self, from_thought, to_thought, why=""):
        """
        Draw a connection between two thoughts/ideas.
        The human mind works in associations — capture them.
        """
        entry = {
            "from": from_thought,
            "to": to_thought,
            "why": why,
            "when": self._ts(),
        }
        self.db["connections"].append(entry)
        self.save()
        print(f"  {C.CYAN}🔗{C.RESET} {from_thought} {C.DIM}→{C.RESET} {to_thought}")
        if why:
            print(f"     {C.DIM}because: {why}{C.RESET}")

    def web(self, limit=20):
        """Visualize the connection web."""
        conns = self.db.get("connections", [])[-limit:]
        if not conns:
            info("No connections yet. Use hb.connect() to link thoughts.")
            return

        header("THOUGHT WEB")
        for c in conns:
            print(f"  {C.CYAN}{c['from']}{C.RESET} {C.DIM}──→{C.RESET} {C.YELLOW}{c['to']}{C.RESET}")
            if c.get("why"):
                print(f"       {C.DIM}\"{c['why']}\"{C.RESET}")

    # ─── Moods ──────────────────────────────

    def mood(self, feeling, note=""):
        """
        Log your current mood. Track emotional state over time.

        Args:
            feeling: The mood (e.g., "excited", "frustrated", "curious", "zen")
            note: Context for the mood
        """
        mood_icons = {
            "excited": "🔥", "happy": "😊", "curious": "🤔", "zen": "🧘",
            "frustrated": "😤", "tired": "😴", "focused": "🎯", "creative": "🎨",
            "anxious": "😰", "proud": "💪", "grateful": "🙏", "inspired": "✨",
        }
        icon = mood_icons.get(feeling.lower(), "💭")

        entry = {
            "mood": feeling,
            "note": note,
            "when": self._ts(),
        }
        self.db["moods"].append(entry)
        self.save()
        print(f"  {icon} {C.WHITE}{feeling}{C.RESET}")
        if note:
            print(f"     {C.DIM}{note}{C.RESET}")

    def moods(self, limit=10):
        """View mood timeline."""
        all_moods = self.db.get("moods", [])[-limit:]
        if not all_moods:
            info("No moods logged. Use hb.mood() to start tracking.")
            return

        header("MOOD TIMELINE")
        mood_icons = {
            "excited": "🔥", "happy": "😊", "curious": "🤔", "zen": "🧘",
            "frustrated": "😤", "tired": "😴", "focused": "🎯", "creative": "🎨",
            "anxious": "😰", "proud": "💪", "grateful": "🙏", "inspired": "✨",
        }
        for m in reversed(all_moods):
            icon = mood_icons.get(m["mood"].lower(), "💭")
            print(f"  {icon} {C.WHITE}{m['mood']:<14}{C.RESET} {C.DIM}{m['when']}{C.RESET}")
            if m.get("note"):
                print(f"     {C.DIM}\"{m['note']}\"{C.RESET}")

    # ─── Journal ────────────────────────────

    def journal(self, entry_text, title=None):
        """
        Write a journal entry. Dated automatically.

        Args:
            entry_text: The journal entry
            title: Optional title (defaults to date)
        """
        entry = {
            "title": title or datetime.now().strftime("%A, %B %d"),
            "text": entry_text,
            "when": self._ts(),
            "date": datetime.now().strftime("%Y-%m-%d"),
        }
        self.db["journal"].append(entry)
        self.save()
        print(f"  {C.GREEN}📝{C.RESET} {C.BOLD}{entry['title']}{C.RESET}")
        print(f"     {C.DIM}{entry_text[:80]}{'...' if len(entry_text) > 80 else ''}{C.RESET}")

    def read_journal(self, limit=5):
        """Read recent journal entries."""
        entries = self.db.get("journal", [])[-limit:]
        if not entries:
            info("Journal is empty. Use hb.journal() to write.")
            return

        header("JOURNAL")
        for e in reversed(entries):
            print(f"\n  {C.GREEN}📝{C.RESET} {C.BOLD}{e['title']}{C.RESET} {C.DIM}({e['when']}){C.RESET}")
            for line in e["text"].split("\n"):
                print(f"     {C.WHITE}{line}{C.RESET}")

    # ─── Reflection ─────────────────────────

    def reflect(self):
        """
        Reflect on your human brain — see patterns, recent activity, stats.
        The mirror for your mind.
        """
        header("REFLECTION")

        thoughts = self.db.get("thoughts", [])
        ideas = self.db.get("ideas", [])
        stories = self.db.get("stories", [])
        connections = self.db.get("connections", [])
        moods = self.db.get("moods", [])
        journal = self.db.get("journal", [])
        owner = self.db["meta"].get("owner", "Unknown")

        print(f"\n  {C.WHITE}{C.BOLD}{owner}'s Mind{C.RESET}")
        print(f"  {C.GRAY}{'─' * 40}{C.RESET}")
        print(f"  {C.CYAN}💭 Thoughts:{C.RESET}    {len(thoughts)}")
        print(f"  {C.YELLOW}💡 Ideas:{C.RESET}       {len(ideas)}")
        print(f"  {C.MAGENTA}📖 Stories:{C.RESET}     {len(stories)}")
        print(f"  {C.CYAN}🔗 Connections:{C.RESET} {len(connections)}")
        print(f"  {C.GREEN}📝 Journal:{C.RESET}     {len(journal)}")
        print(f"  {C.WHITE}💭 Moods:{C.RESET}       {len(moods)}")

        # Tag cloud
        all_tags = []
        for t in thoughts:
            all_tags.extend(t.get("tags", []))
        for i in ideas:
            all_tags.extend(i.get("tags", []))
        for s in stories:
            all_tags.extend(s.get("tags", []))

        if all_tags:
            from collections import Counter
            tag_counts = Counter(all_tags).most_common(10)
            tag_str = "  ".join(f"{C.CYAN}#{tag}{C.RESET}({count})" for tag, count in tag_counts)
            print(f"\n  {C.WHITE}{C.BOLD}Top Tags:{C.RESET} {tag_str}")

        # Idea garden status
        if ideas:
            seeds = sum(1 for i in ideas if i.get("status") == "seed")
            growing = sum(1 for i in ideas if i.get("status") == "growing")
            bloomed = sum(1 for i in ideas if i.get("status") == "bloomed")
            planted = sum(1 for i in ideas if i.get("status") == "planted")
            print(f"\n  {C.YELLOW}{C.BOLD}Idea Garden:{C.RESET} 🌱{seeds} 🌿{growing} 🌸{bloomed} 🌳{planted}")

        # Last mood
        if moods:
            last = moods[-1]
            print(f"\n  {C.DIM}Current vibe: {last['mood']}")
            if last.get("note"):
                print(f"  \"{last['note']}\"{C.RESET}")

        print()

    # ─── Utils ──────────────────────────────

    @staticmethod
    def _ts():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
