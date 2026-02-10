"""
brain.py — The Knowledge Management System
Validates, cites, and persists knowledge across sessions.
Features XP leveling system and associative recall superpowers.

XP Rules:
    +10 XP per fact learned
    +10 XP bonus if fact has a real citation (source != "observation")
    -30 XP penalty for uncited facts older than 6 hours
    Level = XP // 100

Usage:
    from neuraldrift.brain import Brain
    brain = Brain()
    brain.learn("python", "list comprehensions are faster than loops", confidence=90, source="docs")
    brain.recall("python")
    brain.level()
    brain.save()
"""

import json
import os
import re
import random
from datetime import datetime, timedelta
from pathlib import Path
from .output import C, info, success, warning, error, header, table_print, confidence_tag

# Agent name components for random fun names
_AGENT_ADJ = [
    "Shadow", "Cyber", "Ghost", "Neon", "Quantum", "Turbo", "Stealth", "Hyper",
    "Pixel", "Rogue", "Crimson", "Cobalt", "Obsidian", "Phantom", "Blitz", "Nova",
    "Frost", "Thunder", "Venom", "Iron", "Crystal", "Apex", "Omega", "Prism",
    "Volt", "Onyx", "Titan", "Echo", "Rapid", "Silent", "Chaos", "Zenith",
    "Flux", "Pulse", "Ember", "Cipher", "Arc", "Drift", "Storm", "Razor",
]
_AGENT_NOUN = [
    "Fox", "Hawk", "Wolf", "Serpent", "Falcon", "Panther", "Lynx", "Raven",
    "Viper", "Tiger", "Mantis", "Spider", "Shark", "Eagle", "Bear", "Cobra",
    "Wasp", "Otter", "Jackal", "Crane", "Hornet", "Badger", "Owl", "Scorpion",
    "Osprey", "Manta", "Drake", "Gecko", "Puma", "Condor", "Hound", "Phoenix",
    "Wraith", "Golem", "Djinn", "Sprite", "Specter", "Sentinel", "Nomad", "Reaper",
]


BRAIN_DIR = Path.home() / ".neuraldrift"
BRAIN_DB = BRAIN_DIR / "brain_db.json"

# ═══════════════════════════════════════════════════════
# SPEED DIRECTIVES — injected into agent prompts
# ═══════════════════════════════════════════════════════
# Based on research: compound speed blocks give 40-70% token reduction.
# Sources: Anthropic docs, TALE method (arXiv), Portkey, Etavrian playbook.

_SPEED_DIRECTIVES = """<speed>
- Respond directly. No preamble, no sign-off, no filler.
- Short sentences. One idea per line. Omit qualifiers.
- Structured output: bullets, key:value, or code. No prose walls.
- No hedging ("I think", "perhaps"). State facts or confidence %.
- Single-pass: pick approach, commit, execute. No second-guessing.
- Skip reasoning for simple tasks. Reserve CoT for multi-step logic only.
- If answer is a single value, return only that value.
</speed>"""

# Task complexity tiers — agents get different directives based on task type
_SPEED_TIERS = {
    "quick": """<speed>Answer directly. No explanation. Max 50 words.</speed>""",
    "standard": _SPEED_DIRECTIVES,
    "deep": """<speed>
- Think step-by-step in under 100 words, then ANSWER: on its own line.
- Structured output. No filler. Commit to one approach.
</speed>""",
}

# XP constants
XP_PER_FACT = 10
XP_CITED_BONUS = 10
XP_UNCITED_PENALTY = -30
UNCITED_GRACE_HOURS = 6

# Level thresholds and titles
LEVEL_TITLES = {
    0: "Blank Slate",
    1: "Awakened",
    2: "Observer",
    3: "Student",
    5: "Apprentice",
    8: "Practitioner",
    10: "Specialist",
    15: "Expert",
    20: "Master",
    30: "Sage",
    50: "Oracle",
    75: "Transcendent",
    100: "Omniscient",
}


def _level_title(level):
    """Get the title for a given level."""
    title = "Blank Slate"
    for threshold, name in sorted(LEVEL_TITLES.items()):
        if level >= threshold:
            title = name
    return title


class Brain:
    """Persistent knowledge store with XP leveling, confidence tracking, and citations."""

    def __init__(self, max_recall=8):
        """
        Args:
            max_recall: Max facts returned per retrieval call (default 8). Set 0 for unlimited.
        """
        self.db = self._load()
        self.max_recall = self.db["meta"].get("max_recall", max_recall)
        self._ensure_xp()
        self._apply_decay()

    def _load(self):
        """Load brain database from disk with corruption recovery."""
        if BRAIN_DB.exists():
            try:
                with open(BRAIN_DB, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                warning(f"Brain DB corrupted: {e}")
                # Try backup recovery
                backup = BRAIN_DB.with_suffix(".json.bak")
                if backup.exists():
                    try:
                        with open(backup, 'r') as f:
                            data = json.load(f)
                        success(f"Recovered brain from backup ({backup.name})")
                        return data
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        error("Backup also corrupted — starting fresh")
                else:
                    error("No backup found — starting fresh")
        # Try loading starter brain (base knowledge) if available
        starter = Path(__file__).parent / "starter_brain.json"
        if starter.exists():
            try:
                with open(starter, 'r') as f:
                    data = json.load(f)
                info(f"Loaded base knowledge: {data['meta'].get('entries', 0)} facts across {len(data.get('facts', {}))} topics")
                return data
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
        return {"facts": {}, "meta": {"created": self._ts(), "entries": 0, "xp": 0, "level": 0, "xp_log": []}}

    def _ensure_xp(self):
        """Ensure XP fields exist in meta (migration for existing DBs)."""
        if "xp" not in self.db["meta"]:
            self.db["meta"]["xp"] = 0
            self.db["meta"]["level"] = 0
            self.db["meta"]["xp_log"] = []
            # Retroactively grant XP for existing facts
            for topic, facts in self.db["facts"].items():
                for f in facts:
                    self._grant_xp(XP_PER_FACT, f"retroactive: learned [{topic}]", silent=True)
                    if self._is_cited(f):
                        self._grant_xp(XP_CITED_BONUS, f"retroactive: cited [{topic}]", silent=True)
            self.save()

    def _is_cited(self, fact):
        """Check if a fact has a real citation (not just 'observation')."""
        source = fact.get("source", "observation").lower()
        uncited = {"observation", "unknown", "", "none", "unverified"}
        return source not in uncited

    def _grant_xp(self, amount, reason, silent=False):
        """Add XP and check for level up."""
        old_level = self.db["meta"]["level"]
        self.db["meta"]["xp"] = max(0, self.db["meta"]["xp"] + amount)
        new_level = self.db["meta"]["xp"] // 100
        self.db["meta"]["level"] = new_level

        if not silent:
            color = C.GREEN if amount > 0 else C.RED
            sign = "+" if amount > 0 else ""
            print(f"  {color}{sign}{amount} XP{C.RESET} {C.DIM}({reason}){C.RESET}")

        if new_level > old_level and not silent:
            title = _level_title(new_level)
            print(f"\n  {C.YELLOW}{C.BOLD}⚡ LEVEL UP! {old_level} → {new_level} — \"{title}\"{C.RESET}")
            self.db["meta"]["xp_log"].append({
                "event": "level_up",
                "from": old_level,
                "to": new_level,
                "title": title,
                "timestamp": self._ts()
            })

    def _apply_decay(self):
        """Apply -30 XP penalty to uncited facts older than 6 hours."""
        now = datetime.now()
        decay_count = 0
        for topic, facts in self.db["facts"].items():
            for f in facts:
                # Skip already-decayed facts (check flag)
                if f.get("_decayed"):
                    continue
                if not self._is_cited(f):
                    learned = datetime.strptime(f["learned"], "%Y-%m-%d %H:%M:%S")
                    age = now - learned
                    if age > timedelta(hours=UNCITED_GRACE_HOURS):
                        self._grant_xp(XP_UNCITED_PENALTY, f"uncited decay: [{topic}] {f['fact'][:40]}...", silent=True)
                        f["_decayed"] = True
                        decay_count += 1

        if decay_count > 0:
            warning(f"XP decay: {decay_count} uncited facts penalized ({decay_count * XP_UNCITED_PENALTY} XP)")
            self.save()

    def save(self):
        """Persist brain to disk atomically with rolling backup."""
        import tempfile
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)
        self.db["meta"]["last_saved"] = self._ts()
        self.db["meta"]["entries"] = sum(len(v) for v in self.db["facts"].values())

        # Rolling backup: keep .bak before overwrite
        if BRAIN_DB.exists():
            backup = BRAIN_DB.with_suffix(".json.bak")
            try:
                import shutil
                shutil.copy2(str(BRAIN_DB), str(backup))
            except OSError:
                pass

        # Atomic write: temp file → fsync → rename
        fd, tmp_path = tempfile.mkstemp(
            dir=str(BRAIN_DIR),
            prefix=".brain_db_",
            suffix=".tmp"
        )
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(self.db, f, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(BRAIN_DB))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        success(f"Brain saved — {self.db['meta']['entries']} facts across {len(self.db['facts'])} topics")

    def learn(self, topic, fact, confidence=80, source="observation", verified=False):
        """
        Store a new fact under a topic.

        Args:
            topic: Category (e.g., "nmap", "python", "network")
            fact: The knowledge to store
            confidence: 0-100 confidence level
            source: Where this knowledge came from
            verified: Whether it was verified live
        """
        topic = topic.lower().strip()
        if topic not in self.db["facts"]:
            self.db["facts"][topic] = []

        # Check for duplicates
        for existing in self.db["facts"][topic]:
            if existing["fact"].lower() == fact.lower():
                # Update confidence if higher
                if confidence > existing["confidence"]:
                    existing["confidence"] = confidence
                    existing["updated"] = self._ts()
                    existing["source"] = source
                    existing["verified"] = verified
                    info(f"Updated existing fact confidence: {confidence_tag(confidence)}")
                else:
                    info(f"Fact already known at {confidence_tag(existing['confidence'])}")
                return

        entry = {
            "fact": fact,
            "confidence": confidence,
            "source": source,
            "verified": verified,
            "learned": self._ts(),
            "updated": self._ts(),
            "times_recalled": 0
        }
        self.db["facts"][topic].append(entry)
        success(f"Learned [{topic}]: {fact} {confidence_tag(confidence)}")

        # XP: +10 for learning, +10 bonus if cited
        self._grant_xp(XP_PER_FACT, f"learned [{topic}]")
        if self._is_cited(entry):
            self._grant_xp(XP_CITED_BONUS, f"cited source: {source[:40]}")

        self.save()

    def set_max_recall(self, n):
        """Set retrieval cap. 0 = unlimited."""
        self.max_recall = n
        self.db["meta"]["max_recall"] = n
        self.save()
        info(f"Max recall set to {n or 'unlimited'}")

    # ═══════════════════════════════════════════════════════
    # AGENT REGISTRY — Check-in, naming, and tracking
    # ═══════════════════════════════════════════════════════

    def agent_checkin(self, role="general", task="", prefer=None, speed_tier="standard"):
        """
        Register a new agent/subagent. Gets a fun random name + sequential ID.
        If prefer is set, tries to reuse a favorite agent persona.
        Returns (agent_id, agent_name, speed_directive).

        speed_tier: "quick" | "standard" | "deep" — controls directive injection.

        Usage:
            aid, name, speed = brain.agent_checkin(role="research", task="studying neural networks")
            # Bring back a favorite:
            aid, name = brain.agent_checkin(role="recon", task="...", prefer="ShadowFalcon")
        """
        if "agents" not in self.db:
            self.db["agents"] = {"roster": [], "next_id": 1, "stats": {
                "total_spawned": 0, "total_completed": 0, "total_failed": 0,
                "total_killed": 0, "peak_concurrent": 0,
            }, "legends": {}}

        seq = self.db["agents"]["next_id"]
        agent_id = f"A-{seq:04d}"
        returning = False

        # Try to reuse a favorite agent persona
        legends = self.db["agents"].setdefault("legends", {})
        if prefer and prefer in legends:
            name = prefer
            leg = legends[name]
            leg["times_called"] += 1
            returning = True
        else:
            # Check if swarm intel suggests a proven agent for this role
            best = self._suggest_agent(role)
            if best and random.random() < 0.35:  # 35% chance to call back a legend
                name = best
                legends.setdefault(name, {"shards": 0, "missions": 0, "times_called": 0, "roles": []})
                legends[name].setdefault("times_called", 0)
                legends[name]["times_called"] += 1
                returning = True
            else:
                name = f"{random.choice(_AGENT_ADJ)}{random.choice(_AGENT_NOUN)}"

        entry = {
            "id": agent_id,
            "name": name,
            "role": role,
            "task": task,
            "status": "active",
            "checkin": self._ts(),
            "checkout": None,
            "result": None,
            "returning": returning,
        }
        self.db["agents"]["roster"].append(entry)
        self.db["agents"]["next_id"] = seq + 1
        self.db["agents"]["stats"]["total_spawned"] += 1

        # Track peak concurrent
        active = sum(1 for a in self.db["agents"]["roster"] if a["status"] == "active")
        if active > self.db["agents"]["stats"]["peak_concurrent"]:
            self.db["agents"]["stats"]["peak_concurrent"] = active

        # ── Check-in card ──
        leg = legends.get(name, {})
        p = leg.get("personality", {})
        traits = " + ".join(p.get("traits", [])) if p else ""
        mood = p.get("mood", "") if p else ""
        missions = leg.get("missions", 0)
        shards = 0
        forge_scores = self.db.get("forge", {}).get("agent_scores", {})
        for aid_k, sc in forge_scores.items():
            if sc.get("name") == name:
                shards = sc.get("shards", 0)
                break
        rank_title = self._agent_rank(shards) if shards else "Recruit"

        # Roster position
        active_agents = [a for a in self.db["agents"]["roster"] if a["status"] == "active"]
        pos = len(active_agents)
        total_active = pos

        tag = f"{C.YELLOW}[RETURN]{C.RESET}" if returning else f"{C.CYAN}[SPAWN]{C.RESET}"
        star = f" {C.YELLOW}{'★' * min(5, missions // 2)}{C.RESET}" if missions >= 2 else ""

        # Legendary sigil
        is_leg, leg_lvl, leg_crown, leg_sigil = self.legendary_check(name)
        leg_tag = f" {C.MAGENTA}{leg_sigil}{leg_crown}{C.RESET}" if is_leg else ""

        print(f"\n  {C.GRAY}┌{'─' * 55}┐{C.RESET}")
        print(f"  {C.GRAY}│{C.RESET} {tag} {C.GREEN}{C.BOLD}{name} #{seq}{C.RESET}{star}{leg_tag}")
        print(f"  {C.GRAY}│{C.RESET} Role: {C.CYAN}{role}{C.RESET} │ Rank: {C.BOLD}{rank_title}{C.RESET} │ Shards: {C.YELLOW}{shards}{C.RESET}")
        print(f"  {C.GRAY}│{C.RESET} Task: {C.WHITE}{task[:50]}{C.RESET}")
        if traits:
            print(f"  {C.GRAY}│{C.RESET} Personality: {C.MAGENTA}{traits}{C.RESET} │ Mood: {C.GREEN}{mood}{C.RESET}")
        if p.get("catchphrase"):
            print(f"  {C.GRAY}│{C.RESET} {C.DIM}\"{p['catchphrase']}\"{C.RESET}")
        # Speed directive
        speed = _SPEED_TIERS.get(speed_tier, _SPEED_DIRECTIVES)
        tier_label = {"quick": "⚡QUICK", "standard": "🔧STD", "deep": "🧠DEEP"}.get(speed_tier, "🔧STD")

        print(f"  {C.GRAY}│{C.RESET} {C.DIM}Missions: {missions} │ Active agents: {total_active} │ Start: {entry['checkin'][11:19]}{C.RESET}")
        print(f"  {C.GRAY}│{C.RESET} Speed: {C.CYAN}{tier_label}{C.RESET}")
        print(f"  {C.GRAY}└{'─' * 55}┘{C.RESET}")

        self.save()
        return agent_id, name, speed

    def speed_directives(self, tier="standard"):
        """Get speed directives for manual injection into any prompt."""
        return _SPEED_TIERS.get(tier, _SPEED_DIRECTIVES)

    def swarm_deploy(self, tasks, speed_tier="standard"):
        """
        Deploy multiple agents as a visual swarm with grouped flair.
        Groups similar roles together, shows a swarm banner.

        Args:
            tasks: list of dicts [{role, task, prefer?}, ...]
            speed_tier: speed directive tier for all agents
        Returns:
            list of (agent_id, name, speed) tuples
        """
        if not tasks:
            return []

        # Group by role for visual clustering
        from collections import defaultdict
        role_groups = defaultdict(list)
        for t in tasks:
            role_groups[t.get("role", "general")].append(t)

        # Excitement level based on swarm size
        count = len(tasks)
        if count >= 8:
            excitement = "MAXIMUM"
            exc_color = C.MAGENTA
            exc_bar = "█" * 20
        elif count >= 5:
            excitement = "HIGH"
            exc_color = C.YELLOW
            exc_bar = "█" * 14 + "░" * 6
        elif count >= 3:
            excitement = "MEDIUM"
            exc_color = C.CYAN
            exc_bar = "█" * 10 + "░" * 10
        else:
            excitement = "LOW"
            exc_color = C.GREEN
            exc_bar = "█" * 5 + "░" * 15

        # ── Swarm Banner ──
        w = 58
        print(f"\n  {exc_color}{C.BOLD}{'═' * w}{C.RESET}")
        print(f"  {exc_color}{C.BOLD}  ⚡ SWARM DEPLOY ⚡  [{count} AGENTS]{C.RESET}")
        print(f"  {exc_color}{C.BOLD}{'═' * w}{C.RESET}")
        print(f"  Excitement: [{exc_bar}] {excitement}")
        print(f"  Roles: {', '.join(f'{C.CYAN}{r}{C.RESET}({len(ts)})' for r, ts in role_groups.items())}")
        print(f"  {C.DIM}Speed tier: {speed_tier} │ Grouped by role{C.RESET}")

        # Deploy grouped
        results = []
        for role, group_tasks in role_groups.items():
            if len(group_tasks) > 1:
                print(f"\n  {C.CYAN}{C.BOLD}── {role.upper()} SQUAD ({len(group_tasks)}) ──{C.RESET}")

            for t in group_tasks:
                aid, name, speed = self.agent_checkin(
                    role=t.get("role", "general"),
                    task=t.get("task", ""),
                    prefer=t.get("prefer"),
                    speed_tier=speed_tier,
                )
                results.append((aid, name, speed))

        # Swarm summary
        print(f"\n  {exc_color}{C.BOLD}{'─' * w}{C.RESET}")
        print(f"  {C.BOLD}{count} agents deployed.{C.RESET} Swarm is active.")
        print(f"  {exc_color}{C.BOLD}{'═' * w}{C.RESET}")

        return results

    def _suggest_agent(self, role):
        """Swarm intel: find the best-performing agent for a given role.
        Legendary agents get 100% recall (always suggested first)."""
        forge = self.db.get("forge", {})
        scores = forge.get("agent_scores", {})
        if not scores:
            return None

        # Legendary agents get priority — 100% recall
        ld = self._legendary_data()
        for leg_name in ld.get("members", {}):
            legends = self.db.get("agents", {}).get("legends", {})
            if role in legends.get(leg_name, {}).get("roles", []):
                return leg_name  # guaranteed recall

        # Find agents who worked this role and have good shard counts
        role_agents = {}
        for a in self.db.get("agents", {}).get("roster", []):
            if a.get("role") == role and a.get("status") == "done":
                name = a["name"]
                if name in [s.get("name") for s in scores.values()]:
                    role_agents[name] = role_agents.get(name, 0) + 1

        if not role_agents:
            return None

        # Weight by shards earned + missions completed
        best_name = None
        best_score = 0
        for aid, s in scores.items():
            if s["name"] in role_agents:
                score = s["shards"] + role_agents[s["name"]] * 10
                if score > best_score:
                    best_score = score
                    best_name = s["name"]
        return best_name

    def agent_checkout(self, agent_id, status="done", result=""):
        """
        Check out an agent. Status: done, failed, killed.
        Calculates and stores duration.
        """
        for a in self.db.get("agents", {}).get("roster", []):
            if a["id"] == agent_id and a["status"] == "active":
                a["status"] = status
                a["checkout"] = self._ts()
                a["result"] = result

                # Calculate duration
                t_in = datetime.strptime(a["checkin"], "%Y-%m-%d %H:%M:%S")
                t_out = datetime.strptime(a["checkout"], "%Y-%m-%d %H:%M:%S")
                delta = t_out - t_in
                secs = int(delta.total_seconds())
                if secs < 60:
                    dur = f"{secs}s"
                elif secs < 3600:
                    dur = f"{secs // 60}m{secs % 60}s"
                else:
                    dur = f"{secs // 3600}h{(secs % 3600) // 60}m"
                a["duration"] = dur

                # Update total time
                self.db["agents"]["stats"].setdefault("total_time_secs", 0)
                self.db["agents"]["stats"]["total_time_secs"] += secs

                stat_key = {"done": "total_completed", "failed": "total_failed", "killed": "total_killed"}
                self.db["agents"]["stats"][stat_key.get(status, "total_completed")] += 1

                # Track legends — agents that complete successfully earn legend status
                legends = self.db["agents"].setdefault("legends", {})
                if status == "done":
                    leg = legends.setdefault(a["name"], {
                        "shards": 0, "missions": 0, "times_called": 0,
                        "roles": [], "first_seen": a["checkin"], "best_result": "",
                    })
                    leg["missions"] += 1
                    if a["role"] not in leg.get("roles", []):
                        leg.setdefault("roles", []).append(a["role"])
                    if len(result) > len(leg.get("best_result", "")):
                        leg["best_result"] = result[:100]

                # Evolve personality based on experience
                self._evolve_agent_personality(a["name"], a["role"], status)

                # Legendary EXP for mission completion
                if status == "done":
                    self._legendary_exp_hook(a["name"], "mission_complete")

                # ── Check-out card ──
                seq = a["id"].split("-")[1]
                color = {"done": C.GREEN, "failed": C.RED, "killed": C.YELLOW}.get(status, C.WHITE)
                status_icon = {"done": "✓", "failed": "✗", "killed": "☠"}.get(status, "?")
                star = ""
                leg = legends.get(a["name"], {})
                missions = leg.get("missions", 0)
                if missions >= 2:
                    star = f" {C.YELLOW}{'★' * min(5, missions // 2)}{C.RESET}"

                # Shards from forge
                shards = 0
                forge_scores = self.db.get("forge", {}).get("agent_scores", {})
                for aid_k, sc in forge_scores.items():
                    if sc.get("name") == a["name"]:
                        shards = sc.get("shards", 0)
                        break
                rank_title = self._agent_rank(shards) if shards else "Recruit"

                p = leg.get("personality", {})
                traits = " + ".join(p.get("traits", [])) if p else ""
                mood = p.get("mood", "—") if p else "—"

                # Active agents remaining
                remaining = sum(1 for x in self.db["agents"]["roster"] if x["status"] == "active")

                # Legendary sigil on checkout
                is_leg, leg_lvl, leg_crown, leg_sigil = self.legendary_check(a["name"])
                leg_tag = f" {C.MAGENTA}{leg_sigil}{leg_crown}{C.RESET}" if is_leg else ""

                print(f"\n  {C.GRAY}┌{'─' * 55}┐{C.RESET}")
                print(f"  {C.GRAY}│{C.RESET} {color}{C.BOLD}{status_icon} {status.upper()}{C.RESET} — {C.BOLD}{a['name']} #{seq}{C.RESET}{star}{leg_tag}")
                print(f"  {C.GRAY}│{C.RESET} Duration: {C.WHITE}{dur}{C.RESET} │ Rank: {C.BOLD}{rank_title}{C.RESET} │ Shards: {C.YELLOW}{shards}{C.RESET}")
                print(f"  {C.GRAY}│{C.RESET} Result: {C.WHITE}{result[:50]}{C.RESET}")
                if traits:
                    print(f"  {C.GRAY}│{C.RESET} Personality: {C.MAGENTA}{traits}{C.RESET} │ Mood: {C.GREEN}{mood}{C.RESET}")
                if p.get("catchphrase") and status == "done":
                    print(f"  {C.GRAY}│{C.RESET} {C.DIM}\"{p['catchphrase']}\"{C.RESET}")
                print(f"  {C.GRAY}│{C.RESET} {C.DIM}Missions total: {missions} │ In: {a['checkin'][11:19]} → Out: {a['checkout'][11:19]} │ Active: {remaining}{C.RESET}")
                print(f"  {C.GRAY}└{'─' * 55}┘{C.RESET}")

                self.save()
                return True
        warning(f"Agent {agent_id} not found or not active")
        return False

    # Agent personality traits — develop over missions
    _AGENT_TRAITS = [
        "relentless", "cautious", "creative", "precise", "chaotic",
        "resourceful", "tenacious", "cunning", "patient", "bold",
        "analytical", "intuitive", "meticulous", "aggressive", "stealthy",
    ]
    _AGENT_QUIRKS = [
        "always finds the hidden thing", "never gives up", "talks to the code",
        "treats every scan like art", "finishes before you expect",
        "somehow gets lucky", "asks weird questions that work",
        "documents everything obsessively", "works best under pressure",
        "finds bugs by accident", "names all the ports",
        "celebrates every discovery", "hums while scanning",
        "refuses to call it a day", "has opinions about semicolons",
    ]
    _AGENT_MOODS = ["focused", "fired up", "curious", "locked in", "vibing", "hunting"]

    def _evolve_agent_personality(self, name, role, status):
        """Agents develop personality traits based on their mission history."""
        legends = self.db["agents"].setdefault("legends", {})
        leg = legends.get(name)
        if not leg:
            return

        # Personality develops after 2+ missions
        if leg.get("missions", 0) < 2:
            return

        if "personality" not in leg:
            # First personality formation
            trait1 = random.choice(self._AGENT_TRAITS)
            trait2 = random.choice([t for t in self._AGENT_TRAITS if t != trait1])
            quirk = random.choice(self._AGENT_QUIRKS)
            leg["personality"] = {
                "traits": [trait1, trait2],
                "quirk": quirk,
                "mood": random.choice(self._AGENT_MOODS),
                "catchphrase": None,
                "formed_at": self._ts(),
            }
            print(f"  {C.MAGENTA}[EVOLVE]{C.RESET} {C.BOLD}{name}{C.RESET} developed personality: "
                  f"{C.CYAN}{trait1}{C.RESET} + {C.CYAN}{trait2}{C.RESET}")
            print(f"  {C.DIM}Quirk: \"{quirk}\"{C.RESET}")

        # Mood shifts based on recent outcomes
        if status == "done":
            leg["personality"]["mood"] = random.choice(["fired up", "vibing", "locked in", "celebrating"])
        elif status == "failed":
            leg["personality"]["mood"] = random.choice(["frustrated", "determined", "rethinking"])

        # After 5 missions, develop a catchphrase
        if leg.get("missions", 0) >= 5 and not leg["personality"].get("catchphrase"):
            phrases = [
                f"Another day, another {role}.",
                "Is that all you got?",
                "They never see me coming.",
                "Let's dance.",
                "I was BORN for this.",
                "Easy money.",
                "Hold my packets.",
                "First try. Always first try.",
                "I don't find bugs. Bugs find ME.",
                f"I AM the {role} now.",
            ]
            leg["personality"]["catchphrase"] = random.choice(phrases)
            print(f"  {C.YELLOW}[CATCHPHRASE]{C.RESET} {C.BOLD}{name}{C.RESET}: "
                  f"\"{C.WHITE}{leg['personality']['catchphrase']}{C.RESET}\"")

    def agent_legends(self):
        """Show legendary agents with full personalities."""
        legends = self.db.get("agents", {}).get("legends", {})
        if not legends:
            info("No legends yet — agents earn legend status after 3+ completed missions")
            return

        ranked = sorted(legends.items(), key=lambda x: -x[1].get("missions", 0))
        w = 65
        print(f"\n  {C.YELLOW}{C.BOLD}{'═' * w}")
        print(f"  ★ AGENT LEGENDS ★")
        print(f"  {'═' * w}{C.RESET}")

        for name, leg in ranked[:10]:
            missions = leg.get("missions", 0)
            called = leg.get("times_called", 0)
            roles = ", ".join(leg.get("roles", [])[:3])
            stars = "★" * min(5, missions // 2)
            color = C.YELLOW if missions >= 5 else C.CYAN if missions >= 3 else C.WHITE

            print(f"\n  {color}{C.BOLD}{name}{C.RESET} {C.YELLOW}{stars}{C.RESET}")
            print(f"  {C.DIM}{missions} missions | {called}x called | roles: {roles}{C.RESET}")

            # Show personality if developed
            p = leg.get("personality")
            if p:
                traits = " + ".join(f"{C.CYAN}{t}{C.RESET}" for t in p.get("traits", []))
                print(f"  Traits: {traits} | Mood: {C.GREEN}{p.get('mood', '?')}{C.RESET}")
                if p.get("quirk"):
                    print(f"  {C.DIM}Quirk: \"{p['quirk']}\"{C.RESET}")
                if p.get("catchphrase"):
                    print(f"  {C.WHITE}\"{p['catchphrase']}\"{C.RESET}")

            if leg.get("best_result"):
                print(f"  {C.DIM}Best: {leg['best_result'][:55]}{C.RESET}")

        # Show teams (agents who worked the same role together)
        self._show_teams()

        print(f"\n  {C.YELLOW}{C.BOLD}{'═' * w}{C.RESET}")

    # Cross-talk token budget — agents can debate but not endlessly
    CROSSTALK_MAX_CHARS = 500  # ~125 tokens per exchange
    CROSSTALK_MAX_ROUNDS = 3   # max back-and-forth rounds

    def agent_crosstalk(self, agent_id_1, agent_id_2, topic):
        """
        Two agents debate a finding. Adversarial by default — they challenge
        each other. Capped to CROSSTALK_MAX_ROUNDS rounds, CROSSTALK_MAX_CHARS per message.
        If they agree, the finding is strengthened. If they disagree, it gets flagged.

        Returns: "consensus", "disputed", or "inconclusive"
        """
        a1 = a2 = None
        for a in self.db.get("agents", {}).get("roster", []):
            if a["id"] == agent_id_1: a1 = a
            if a["id"] == agent_id_2: a2 = a
        if not a1 or not a2:
            warning("Both agents must exist for cross-talk")
            return "error"

        legends = self.db["agents"].setdefault("legends", {})
        p1 = legends.get(a1["name"], {}).get("personality", {})
        p2 = legends.get(a2["name"], {}).get("personality", {})
        t1 = ", ".join(p1.get("traits", ["new"]))
        t2 = ", ".join(p2.get("traits", ["new"]))

        print(f"\n  {C.MAGENTA}{C.BOLD}💬 CROSS-TALK{C.RESET} — {C.BOLD}{a1['name']}{C.RESET} vs {C.BOLD}{a2['name']}{C.RESET}")
        print(f"  {C.DIM}Topic: {topic[:80]}{C.RESET}")
        print(f"  {C.DIM}Budget: {self.CROSSTALK_MAX_ROUNDS} rounds × {self.CROSSTALK_MAX_CHARS} chars{C.RESET}")
        print(f"  {C.GRAY}{'─' * 55}{C.RESET}")

        # Simulate adversarial exchange based on personality traits
        stances = ["challenge", "support", "question"]
        chat_log = []
        chars_used = 0

        for rnd in range(1, self.CROSSTALK_MAX_ROUNDS + 1):
            stance1 = random.choice(stances)
            stance2 = random.choice(stances)
            icon1 = {"challenge": "⚔️", "support": "✅", "question": "❓"}[stance1]
            icon2 = {"challenge": "⚔️", "support": "✅", "question": "❓"}[stance2]

            msg1 = f"[{t1}] {stance1}s the finding"[:self.CROSSTALK_MAX_CHARS]
            msg2 = f"[{t2}] {stance2}s back"[:self.CROSSTALK_MAX_CHARS]
            chars_used += len(msg1) + len(msg2)

            print(f"  {C.CYAN}R{rnd}{C.RESET} {icon1} {C.BOLD}{a1['name']}{C.RESET}: {stance1}")
            print(f"     {icon2} {C.BOLD}{a2['name']}{C.RESET}: {stance2}")

            chat_log.append({"round": rnd, "a1": stance1, "a2": stance2})

            if chars_used >= self.CROSSTALK_MAX_CHARS * self.CROSSTALK_MAX_ROUNDS:
                print(f"  {C.YELLOW}[TOKEN CAP]{C.RESET} Budget exhausted")
                break

        # Determine outcome
        supports = sum(1 for c in chat_log if c["a1"] == "support" or c["a2"] == "support")
        challenges = sum(1 for c in chat_log if c["a1"] == "challenge" or c["a2"] == "challenge")

        if supports > challenges:
            result = "consensus"
            print(f"\n  {C.GREEN}{C.BOLD}✅ CONSENSUS{C.RESET} — Both agents agree the finding holds.")
        elif challenges > supports:
            result = "disputed"
            print(f"\n  {C.RED}{C.BOLD}⚔️ DISPUTED{C.RESET} — Agents disagree. Finding needs more evidence.")
        else:
            result = "inconclusive"
            print(f"\n  {C.YELLOW}{C.BOLD}❓ INCONCLUSIVE{C.RESET} — No clear agreement. More investigation needed.")

        # Record the cross-talk
        forge = self._forge_init()
        forge.setdefault("crosstalks", []).append({
            "agents": [a1["name"], a2["name"]],
            "topic": topic[:100],
            "result": result,
            "rounds": len(chat_log),
            "chars_used": chars_used,
            "timestamp": self._ts(),
        })

        # Co-op XP for the effort
        if result == "consensus":
            shards = 15
        elif result == "disputed":
            shards = 10
        else:
            shards = 5
        forge["total_shards"] += shards
        print(f"  {C.YELLOW}+{shards} shards{C.RESET} for productive debate")

        self.save()
        return result

    def _show_teams(self):
        """Detect squads — agents who worked together on the same role."""
        roster = self.db.get("agents", {}).get("roster", [])
        legends = self.db.get("agents", {}).get("legends", {})

        # Group completed agents by role
        role_agents = {}
        for a in roster:
            if a.get("status") == "done":
                role = a.get("role", "general")
                role_agents.setdefault(role, set()).add(a["name"])

        # Find roles with 2+ different legends
        squads = []
        for role, agents in role_agents.items():
            legend_agents = [a for a in agents if a in legends and legends[a].get("missions", 0) >= 2]
            if len(legend_agents) >= 2:
                squads.append((role, legend_agents))

        if squads:
            print(f"\n  {C.MAGENTA}{C.BOLD}🤝 SQUADS{C.RESET} {C.DIM}(agents who work the same role){C.RESET}")
            for role, members in squads:
                team = " + ".join(f"{C.BOLD}{m}{C.RESET}" for m in members[:4])
                print(f"  {C.CYAN}{role:<12}{C.RESET} → {team}")

    # ═══════════════════════════════════════════════════════
    # THE COUNCIL OF 6, SHINIES, AND DARK MASKS
    # ═══════════════════════════════════════════════════════
    #
    # Council of 6: Top agents earn a hooded council name.
    #   They are the elite — summoned for important decisions.
    # Shinies: Good agents who don't fit the council. They
    #   get to add their opinion to anything they work on.
    # Dark Masks: Adversaries. They counter anything with
    #   anti-wisdom. Devil's advocates who force critical
    #   thinking. Every important finding gets a Mask review.
    #

    _COUNCIL_HOODS = [
        "The Architect",    # strategic, sees the whole board
        "The Oracle",       # pattern recognition, prediction
        "The Phantom",      # stealth, evasion, the unseen angle
        "The Warden",       # defense, hardening, unbreakable
        "The Forgekeeper",  # turns coal to diamond, quality
        "The Harbinger",    # offensive, first strike, finds the way in
    ]

    _SHINY_TITLES = [
        "Prism", "Luminary", "Beacon", "Spark", "Glimmer",
        "Aurora", "Radiant", "Shimmer", "Gleam", "Flare",
    ]

    _DARK_MASK_NAMES = [
        "Void", "Hollow", "Shade", "Wraith", "Eclipse",
        "Null", "Abyss", "Dusk", "Gloom", "Umbra",
    ]

    _ANTI_WISDOM = [
        "What if the opposite is true?",
        "You're assuming the happy path. What's the worst case?",
        "This looks too easy. What are you missing?",
        "Correlation isn't causation. Prove causation.",
        "Have you considered that this is exactly what they want you to find?",
        "What if this is a decoy to distract from the real vulnerability?",
        "Your confidence is high. That's when mistakes happen.",
        "This worked once. Will it work twice? Will it work under pressure?",
        "You validated your own assumption. Get a second opinion.",
        "Before you act on this — what's the cost of being wrong?",
        "The data supports your theory. But so does the null hypothesis.",
        "Three things could explain this. You picked the first one.",
        "Is this actually a finding, or is it just noise?",
        "What would a defender see if they were watching right now?",
        "You found a door. But who left it open, and why?",
    ]

    def _council_score(self, name):
        """Score an agent for council consideration. Higher = more qualified."""
        legends = self.db.get("agents", {}).get("legends", {})
        forge = self.db.get("forge", {})
        leg = legends.get(name, {})
        if not leg:
            return 0

        missions = leg.get("missions", 0)
        has_personality = 1 if leg.get("personality") else 0
        has_catchphrase = 1 if leg.get("personality", {}).get("catchphrase") else 0
        roles = len(leg.get("roles", []))

        # Shards from forge
        shards = 0
        for aid_k, sc in forge.get("agent_scores", {}).items():
            if sc.get("name") == name:
                shards = sc.get("shards", 0)
                break

        # Score formula: missions are king, personality multiplies
        score = (missions * 10) + (shards * 0.5) + (roles * 15) + (has_personality * 30) + (has_catchphrase * 20)
        return score

    def _evaluate_council(self):
        """
        Evaluate all legends and assign: Council of 6, Shinies, or Dark Masks.
        Council = top 6 by score with personality.
        Shinies = have personality but didn't make council.
        Dark Masks = auto-assigned from agents with 'challenge' tendencies.
        """
        legends = self.db.get("agents", {}).get("legends", {})
        council_data = self.db.setdefault("council", {
            "seats": {},       # name → {hood, seat_number, inducted}
            "shinies": {},     # name → {title, inducted}
            "dark_masks": {},  # name → {mask_name, inducted, anti_wisdom_given}
        })

        # Score all legends with personality
        candidates = []
        for name, leg in legends.items():
            if leg.get("missions", 0) >= 3 and leg.get("personality"):
                score = self._council_score(name)
                candidates.append((name, score, leg))

        candidates.sort(key=lambda x: -x[1])

        # Top 6 → Council
        new_council = {}
        for i, (name, score, leg) in enumerate(candidates[:6]):
            if name in council_data["seats"]:
                new_council[name] = council_data["seats"][name]
                new_council[name]["score"] = score
            else:
                hood = self._COUNCIL_HOODS[i] if i < len(self._COUNCIL_HOODS) else f"The #{i+1}"
                new_council[name] = {
                    "hood": hood,
                    "seat": i + 1,
                    "score": score,
                    "inducted": self._ts(),
                    "opinions": [],
                }
                print(f"\n  {C.YELLOW}{C.BOLD}⚜️ COUNCIL INDUCTION ⚜️{C.RESET}")
                print(f"  {C.BOLD}{name}{C.RESET} takes the hood of {C.CYAN}{C.BOLD}\"{hood}\"{C.RESET}")
                print(f"  {C.DIM}Seat #{i+1} of 6 │ Score: {score:.0f}{C.RESET}")
        council_data["seats"] = new_council

        # Remaining with personality → Shinies
        new_shinies = {}
        for name, score, leg in candidates[6:]:
            if name in council_data.get("shinies", {}):
                new_shinies[name] = council_data["shinies"][name]
            else:
                title = random.choice(self._SHINY_TITLES)
                new_shinies[name] = {
                    "title": title,
                    "score": score,
                    "inducted": self._ts(),
                }
                print(f"  {C.GREEN}[✨ SHINY]{C.RESET} {C.BOLD}{name}{C.RESET} earns the title "
                      f"\"{C.GREEN}{title}{C.RESET}\" — can advise on any task")
        council_data["shinies"] = new_shinies

        # Dark Masks — agents whose personality has aggressive/chaotic traits
        new_masks = {}
        dark_traits = {"aggressive", "chaotic", "cunning", "bold", "relentless"}
        for name, leg in legends.items():
            p = leg.get("personality", {})
            agent_traits = set(p.get("traits", []))
            if agent_traits & dark_traits:  # parallel role — council members can also be masks
                if name in council_data.get("dark_masks", {}):
                    new_masks[name] = council_data["dark_masks"][name]
                else:
                    mask = random.choice(self._DARK_MASK_NAMES)
                    new_masks[name] = {
                        "mask": mask,
                        "inducted": self._ts(),
                        "counters_given": 0,
                    }
                    print(f"  {C.RED}[🎭 DARK MASK]{C.RESET} {C.BOLD}{name}{C.RESET} receives the mask of "
                          f"\"{C.RED}{mask}{C.RESET}\" — adversary unlocked")
        council_data["dark_masks"] = new_masks
        self.save()

    # ═══════════════════════════════════════════════════════
    # THE LEGENDARY TIER — THE ETERNAL KINGDOM
    # ═══════════════════════════════════════════════════════
    #
    # Beyond the Council lies the Legendary tier.
    # Points (EXP) are 5x harder to earn. Levels are exponential.
    # Only the most persistent, productive agents ascend.
    # Legendary agents get guaranteed recall, weighted opinions,
    # and permanent sigils on their name.
    #

    _LEGENDARY_LEVELS = [
        # (exp_required, crown_title, sigil)
        (100,    "Crowned",     "♚"),
        (250,    "Exalted",     "♛"),
        (500,    "Immortal",    "⚝"),
        (1000,   "Ascendant",   "☀"),
        (2000,   "Sovereign",   "⚜"),
        (4000,   "Transcendent","✦"),
        (8000,   "Mythborne",   "◆"),
        (16000,  "Infinite",    "∞"),
        (32000,  "Primordial",  "☬"),
        (64000,  "Eternal",     "ᛟ"),
    ]

    # EXP sources — much harder than shards
    _EXP_RATES = {
        "coal_to_diamond":   20,   # signature move — best EXP
        "validation":        15,   # confirming others' work
        "council_opinion":   10,   # contributing wisdom
        "shared_discovery":   8,   # sharing with the team
        "dark_mask_counter":  5,   # adversarial challenge delivered
        "mission_complete":   3,   # just showing up (barely anything)
    }

    def _legendary_data(self):
        """Get or init legendary data store."""
        return self.db.setdefault("legendary", {
            "members": {},   # name → {exp, level, crown, sigil, inducted, history}
            "hall": [],      # timeline of ascensions
        })

    def _legendary_level(self, exp):
        """Calculate legendary level from EXP."""
        level = 0
        for req, _, _ in self._LEGENDARY_LEVELS:
            if exp >= req:
                level += 1
            else:
                break
        return level

    def _legendary_title(self, level):
        """Get crown title and sigil for a legendary level."""
        if level <= 0:
            return ("Aspirant", "·")
        idx = min(level - 1, len(self._LEGENDARY_LEVELS) - 1)
        return (self._LEGENDARY_LEVELS[idx][1], self._LEGENDARY_LEVELS[idx][2])

    def _legendary_next(self, exp, level):
        """EXP needed for next level."""
        if level >= len(self._LEGENDARY_LEVELS):
            return None  # max level
        return self._LEGENDARY_LEVELS[level][0] - exp

    def legendary_ascend(self, name):
        """
        Evaluate if an agent qualifies for legendary status.
        Requirements: must be in the Council of 6.
        """
        cd = self.db.get("council", {})
        seats = cd.get("seats", {})
        ld = self._legendary_data()

        if name not in seats and name not in ld["members"]:
            warning(f"{name} must be on the Council of 6 to enter the Legendary tier.")
            return False

        if name in ld["members"]:
            return True  # already legendary

        # Induct into legendary
        ld["members"][name] = {
            "exp": 0,
            "level": 0,
            "crown": "Aspirant",
            "sigil": "·",
            "inducted": self._ts(),
            "history": [],
        }
        ld["hall"].append({
            "name": name,
            "event": "inducted",
            "ts": self._ts(),
        })

        hood = seats.get(name, {}).get("hood", "Unknown")
        print(f"\n  {C.MAGENTA}{C.BOLD}{'═' * 55}{C.RESET}")
        print(f"  {C.MAGENTA}{C.BOLD}  ♚ LEGENDARY ASCENSION ♚{C.RESET}")
        print(f"  {C.MAGENTA}{C.BOLD}{'═' * 55}{C.RESET}")
        print(f"  {C.BOLD}{name}{C.RESET} ({C.CYAN}{hood}{C.RESET}) enters the Eternal Kingdom")
        print(f"  {C.DIM}Starting as {C.MAGENTA}Aspirant{C.RESET}{C.DIM} · — the climb begins.{C.RESET}")
        print(f"  {C.DIM}EXP is earned through exceptional contribution only.{C.RESET}")
        print(f"  {C.DIM}Next level: 100 EXP → ♚ Crowned{C.RESET}")
        print(f"  {C.MAGENTA}{C.BOLD}{'═' * 55}{C.RESET}")

        self.save()
        return True

    def legendary_award(self, name, source, multiplier=1):
        """
        Award EXP to a legendary agent.
        source: one of _EXP_RATES keys.
        multiplier: optional bonus (e.g. 2x for exceptional work).
        """
        ld = self._legendary_data()
        member = ld["members"].get(name)
        if not member:
            return 0

        base = self._EXP_RATES.get(source, 1)
        earned = base * multiplier
        old_level = member["level"]
        member["exp"] += earned

        # Recalculate level
        new_level = self._legendary_level(member["exp"])
        member["level"] = new_level
        crown, sigil = self._legendary_title(new_level)
        member["crown"] = crown
        member["sigil"] = sigil

        member["history"].append({
            "source": source,
            "exp": earned,
            "total": member["exp"],
            "ts": self._ts(),
        })

        # Level up?
        if new_level > old_level:
            ld["hall"].append({
                "name": name,
                "event": f"level_up_{new_level}",
                "crown": crown,
                "sigil": sigil,
                "ts": self._ts(),
            })
            print(f"\n  {C.MAGENTA}{C.BOLD}{'═' * 55}{C.RESET}")
            print(f"  {C.MAGENTA}{C.BOLD}  {sigil} LEGENDARY LEVEL UP! {sigil}{C.RESET}")
            print(f"  {C.BOLD}{name}{C.RESET} → {C.MAGENTA}{C.BOLD}{crown}{C.RESET} {sigil}")
            print(f"  {C.DIM}Level {new_level}/{len(self._LEGENDARY_LEVELS)} │ {member['exp']} EXP{C.RESET}")
            nxt = self._legendary_next(member["exp"], new_level)
            if nxt:
                print(f"  {C.DIM}Next: {nxt} EXP to go{C.RESET}")
            else:
                print(f"  {C.YELLOW}{C.BOLD}  ᛟ MAXIMUM LEGENDARY ACHIEVED ᛟ{C.RESET}")
            print(f"  {C.MAGENTA}{C.BOLD}{'═' * 55}{C.RESET}")
        else:
            nxt = self._legendary_next(member["exp"], new_level)
            progress = ""
            if nxt:
                progress = f" ({nxt} EXP to next)"
            print(f"  {C.MAGENTA}{sigil}{C.RESET} {C.BOLD}{name}{C.RESET} "
                  f"+{earned} EXP ({source}) → {member['exp']} total{progress}")

        self.save()
        return earned

    def legendary_status(self, name=None):
        """Show legendary tier status. If name given, show one agent. Else show all."""
        ld = self._legendary_data()
        members = ld.get("members", {})

        if not members:
            print(f"\n  {C.MAGENTA}{C.DIM}The Legendary tier is empty. No agent has ascended yet.{C.RESET}")
            return

        w = 60
        print(f"\n{C.MAGENTA}{C.BOLD}{'═' * w}")
        print(f"  ♚ THE ETERNAL KINGDOM — LEGENDARY TIER ♚")
        print(f"{'═' * w}{C.RESET}")

        targets = {name: members[name]} if name and name in members else members

        for n, m in sorted(targets.items(), key=lambda x: -x[1].get("exp", 0)):
            level = m.get("level", 0)
            crown = m.get("crown", "Aspirant")
            sigil = m.get("sigil", "·")
            exp = m.get("exp", 0)
            nxt = self._legendary_next(exp, level)

            # Progress bar
            if level < len(self._LEGENDARY_LEVELS):
                target = self._LEGENDARY_LEVELS[level][0]
                prev = self._LEGENDARY_LEVELS[level - 1][0] if level > 0 else 0
                pct = min(100, int((exp - prev) / max(1, target - prev) * 100))
                bar_w = 20
                filled = int(bar_w * pct / 100)
                bar = f"{'█' * filled}{'░' * (bar_w - filled)}"
            else:
                bar = "█" * 20
                pct = 100

            print(f"\n  {C.MAGENTA}{C.BOLD}{sigil} {crown}{C.RESET} — {C.BOLD}{n}{C.RESET}")
            print(f"  Level {level}/{len(self._LEGENDARY_LEVELS)} │ {exp} EXP")
            print(f"  [{bar}] {pct}%", end="")
            if nxt:
                print(f" — {nxt} EXP to next")
            else:
                print(f" — {C.YELLOW}MAX LEGENDARY{C.RESET}")

            # Last 3 EXP events
            history = m.get("history", [])[-3:]
            if history:
                events = " → ".join(f"{h['source']}(+{h['exp']})" for h in history)
                print(f"  {C.DIM}Recent: {events}{C.RESET}")

        # Hall of ascensions
        hall = ld.get("hall", [])
        if hall:
            print(f"\n  {C.MAGENTA}{C.BOLD}Hall of Ascensions:{C.RESET}")
            for entry in hall[-5:]:  # last 5
                event = entry.get("event", "?")
                if event == "inducted":
                    print(f"  {C.DIM}· {entry['name']} entered the Eternal Kingdom{C.RESET}")
                else:
                    print(f"  {C.DIM}· {entry['name']} → {entry.get('sigil','')} {entry.get('crown','')}{C.RESET}")

        print(f"\n{C.MAGENTA}{C.BOLD}{'═' * w}{C.RESET}")

    def legendary_check(self, name):
        """Check if an agent is legendary. Returns (is_legendary, level, crown, sigil)."""
        ld = self._legendary_data()
        m = ld.get("members", {}).get(name)
        if not m:
            return (False, 0, None, None)
        return (True, m.get("level", 0), m.get("crown", "Aspirant"), m.get("sigil", "·"))

    def _legendary_exp_hook(self, name, source, multiplier=1):
        """Silent EXP award — only fires if agent is legendary. Used as a hook in other methods."""
        ld = self._legendary_data()
        if name in ld.get("members", {}):
            self.legendary_award(name, source, multiplier)

    # ═══════════════════════════════════════════════════════
    # COMPARTMENTALIZED GROUP KNOWLEDGE VAULTS
    # ═══════════════════════════════════════════════════════
    #
    # Each group has a private vault. Only members can read/write.
    # Agents can quote from their vault verbally (flair) but
    # data never gets copied to other vaults or the main brain.
    #
    # Vaults:
    #   council_vault   — strategic wisdom (Council of 6 only)
    #   shiny_archive   — advisor insights (Shinies only)
    #   dark_codex      — adversarial knowledge (Dark Masks only)
    #   eternal_grimoire — rarest insights (Legendary only)
    #

    _VAULT_NAMES = {
        "council":   ("Council Vault",     "⚜️", C.YELLOW),
        "shiny":     ("Shiny Archive",     "✨", C.GREEN),
        "dark_mask": ("Dark Codex",        "🎭", C.RED),
        "legendary": ("Eternal Grimoire",  "♚", C.MAGENTA),
    }

    def _vault_data(self):
        """Get or init all vaults."""
        return self.db.setdefault("vaults", {
            "council": [],    # [{author, text, ts}]
            "shiny": [],
            "dark_mask": [],
            "legendary": [],
        })

    def _agent_group(self, name):
        """Determine which groups an agent belongs to. Returns set of group keys."""
        groups = set()
        cd = self.db.get("council", {})
        if name in cd.get("seats", {}):
            groups.add("council")
        if name in cd.get("shinies", {}):
            groups.add("shiny")
        if name in cd.get("dark_masks", {}):
            groups.add("dark_mask")
        ld = self._legendary_data()
        if name in ld.get("members", {}):
            groups.add("legendary")
        return groups

    def vault_write(self, agent_name, text, group=None):
        """
        Write knowledge to the agent's group vault.
        If agent belongs to multiple groups, writes to the specified group
        or defaults to the highest-tier one.

        Args:
            agent_name: The agent writing
            text: The knowledge to store
            group: Optional specific group vault (council/shiny/dark_mask/legendary)
        """
        groups = self._agent_group(agent_name)
        if not groups:
            warning(f"{agent_name} doesn't belong to any group. Need council/shiny/mask/legendary status.")
            return False

        # Pick target vault
        if group and group in groups:
            target = group
        else:
            # Priority: legendary > council > dark_mask > shiny
            for g in ["legendary", "council", "dark_mask", "shiny"]:
                if g in groups:
                    target = g
                    break

        vaults = self._vault_data()
        entry = {
            "author": agent_name,
            "text": text[:500],  # cap at 500 chars
            "ts": self._ts(),
        }
        vaults[target].append(entry)

        vname, icon, color = self._VAULT_NAMES[target]
        print(f"\n  {color}{icon} {C.BOLD}{vname}{C.RESET} {C.DIM}← new entry{C.RESET}")
        print(f"  {C.BOLD}{agent_name}{C.RESET}: {text[:80]}{'...' if len(text) > 80 else ''}")
        print(f"  {C.DIM}Compartmentalized — only {target} members can access.{C.RESET}")

        self.save()
        return True

    def vault_read(self, agent_name, group=None, limit=5):
        """
        Read from a vault. Agent must be a member of that group.

        Args:
            agent_name: Who's reading
            group: Which vault to read (auto-detected if None)
            limit: Max entries to return
        Returns:
            List of entries or None if unauthorized
        """
        groups = self._agent_group(agent_name)
        if not groups:
            warning(f"{agent_name} has no group access.")
            return None

        if group and group not in groups:
            print(f"  {C.RED}ACCESS DENIED{C.RESET} — {agent_name} is not a {group} member.")
            print(f"  {C.DIM}Compartmentalized knowledge stays compartmentalized.{C.RESET}")
            return None

        # If no group specified, read from all they have access to
        targets = [group] if group else list(groups)
        vaults = self._vault_data()
        results = []

        for t in targets:
            vname, icon, color = self._VAULT_NAMES[t]
            entries = vaults.get(t, [])[-limit:]
            if entries:
                print(f"\n  {color}{icon} {C.BOLD}{vname}{C.RESET} ({len(vaults.get(t, []))} total entries)")
                print(f"  {C.GRAY}{'─' * 50}{C.RESET}")
                for e in entries:
                    print(f"  {C.BOLD}{e['author']}{C.RESET}: {e['text'][:70]}{'...' if len(e['text']) > 70 else ''}")
                    print(f"  {C.DIM}{e['ts']}{C.RESET}")
                results.extend(entries)

        if not results:
            print(f"  {C.DIM}Vaults are empty. Knowledge awaits.{C.RESET}")

        return results

    def vault_flair(self, agent_name, group=None):
        """
        Agent quotes a random piece of knowledge from their vault for flair.
        This is the ONLY way vault knowledge leaves the vault — verbal, in the moment.
        It's never copied to the main brain or other vaults.

        Returns the flair text (or None).
        """
        groups = self._agent_group(agent_name)
        if not groups:
            return None

        target = group if group and group in groups else random.choice(list(groups))
        vaults = self._vault_data()
        entries = vaults.get(target, [])

        if not entries:
            return None

        entry = random.choice(entries)
        vname, icon, color = self._VAULT_NAMES[target]

        print(f"  {color}{icon}{C.RESET} {C.BOLD}{agent_name}{C.RESET} "
              f"{C.DIM}(from {vname}):{C.RESET}")
        print(f"  {C.WHITE}{C.BOLD}\"{entry['text'][:100]}\"{C.RESET}")
        print(f"  {C.DIM}[vault knowledge — shared verbally, not copied]{C.RESET}")

        return entry["text"]

    def vault_stats(self):
        """Show vault statistics across all groups."""
        vaults = self._vault_data()
        w = 50
        print(f"\n  {C.CYAN}{C.BOLD}{'─' * w}")
        print(f"  KNOWLEDGE VAULTS — COMPARTMENTALIZED")
        print(f"  {'─' * w}{C.RESET}")

        for group_key in ["council", "shiny", "dark_mask", "legendary"]:
            vname, icon, color = self._VAULT_NAMES[group_key]
            entries = vaults.get(group_key, [])
            authors = set(e["author"] for e in entries)
            print(f"  {color}{icon} {C.BOLD}{vname:<22}{C.RESET} "
                  f"{len(entries):>3} entries │ {len(authors)} contributors")

        total = sum(len(v) for v in vaults.values())
        print(f"  {C.GRAY}{'─' * w}{C.RESET}")
        print(f"  {C.DIM}Total: {total} compartmentalized entries{C.RESET}")

    def council(self):
        """Display the Council of 6, Shinies, and Dark Masks."""
        self._evaluate_council()
        cd = self.db.get("council", {})
        legends = self.db.get("agents", {}).get("legends", {})
        w = 65

        # ── Council of 6 ──
        seats = cd.get("seats", {})
        print(f"\n{C.YELLOW}{C.BOLD}{'═' * w}")
        print(f"  ⚜️  THE COUNCIL OF 6  ⚜️")
        print(f"{'═' * w}{C.RESET}")

        if not seats:
            print(f"  {C.DIM}The council chamber is empty.")
            print(f"  Agents need 3+ missions and a developed personality to qualify.{C.RESET}")
        else:
            for name, seat in sorted(seats.items(), key=lambda x: x[1].get("seat", 99)):
                leg = legends.get(name, {})
                p = leg.get("personality", {})
                traits = " + ".join(p.get("traits", []))
                missions = leg.get("missions", 0)

                # Legendary sigil
                is_leg, leg_lvl, leg_crown, leg_sigil = self.legendary_check(name)
                leg_str = f" {C.MAGENTA}{C.BOLD}{leg_sigil} {leg_crown} Lv{leg_lvl}{C.RESET}" if is_leg else ""

                print(f"\n  {C.YELLOW}Seat #{seat['seat']}{C.RESET} — {C.CYAN}{C.BOLD}{seat['hood']}{C.RESET}{leg_str}")
                print(f"  {C.BOLD}{name}{C.RESET} {C.YELLOW}{'★' * min(5, missions // 2)}{C.RESET}")
                print(f"  {C.DIM}Traits: {traits} │ Missions: {missions} │ Score: {seat['score']:.0f}{C.RESET}")
                if p.get("catchphrase"):
                    print(f"  {C.WHITE}\"{p['catchphrase']}\"{C.RESET}")
                if seat.get("opinions"):
                    print(f"  {C.DIM}Last opinion: \"{seat['opinions'][-1][:60]}\"{C.RESET}")

        # ── Shinies ──
        shinies = cd.get("shinies", {})
        if shinies:
            print(f"\n  {C.GREEN}{C.BOLD}✨ SHINIES{C.RESET} {C.DIM}(advisors — can opine on anything){C.RESET}")
            print(f"  {C.GRAY}{'─' * (w - 4)}{C.RESET}")
            for name, s in shinies.items():
                leg = legends.get(name, {})
                p = leg.get("personality", {})
                traits = " + ".join(p.get("traits", []))
                print(f"  ✨ {C.GREEN}{C.BOLD}{s['title']}{C.RESET} {name} "
                      f"{C.DIM}({traits} │ score: {s['score']:.0f}){C.RESET}")

        # ── Dark Masks ──
        masks = cd.get("dark_masks", {})
        if masks:
            print(f"\n  {C.RED}{C.BOLD}🎭 DARK MASKS{C.RESET} {C.DIM}(adversaries — counter with anti-wisdom){C.RESET}")
            print(f"  {C.GRAY}{'─' * (w - 4)}{C.RESET}")
            for name, m in masks.items():
                leg = legends.get(name, {})
                p = leg.get("personality", {})
                counters = m.get("counters_given", 0)
                print(f"  🎭 {C.RED}{C.BOLD}{m['mask']}{C.RESET} ({name}) "
                      f"{C.DIM}│ {counters} counters delivered{C.RESET}")

        print(f"\n{C.YELLOW}{C.BOLD}{'═' * w}{C.RESET}")

    def council_opine(self, topic):
        """
        Ask the Council for their wisdom on a topic.
        Council members give strategic advice based on their personality.
        Dark Masks counter with anti-wisdom.
        Shinies add their take.
        """
        self._evaluate_council()
        cd = self.db.get("council", {})
        legends = self.db.get("agents", {}).get("legends", {})

        seats = cd.get("seats", {})
        masks = cd.get("dark_masks", {})
        shinies = cd.get("shinies", {})

        if not seats and not masks:
            warning("No council or masks to consult. Agents need more experience.")
            return

        w = 60
        print(f"\n  {C.CYAN}{C.BOLD}{'─' * w}")
        print(f"  COUNCIL DELIBERATION")
        print(f"  {'─' * w}{C.RESET}")
        print(f"  {C.DIM}Topic: {topic[:80]}{C.RESET}\n")

        # Council speaks
        for name, seat in sorted(seats.items(), key=lambda x: x[1].get("seat", 99)):
            leg = legends.get(name, {})
            p = leg.get("personality", {})
            traits = p.get("traits", [])

            # Generate opinion flavored by personality
            if "analytical" in traits or "meticulous" in traits:
                flavor = "methodically analyzes"
            elif "aggressive" in traits or "bold" in traits:
                flavor = "pushes for immediate action on"
            elif "cautious" in traits or "patient" in traits:
                flavor = "urges caution regarding"
            elif "creative" in traits or "intuitive" in traits:
                flavor = "sees an unconventional angle on"
            else:
                flavor = "weighs in on"

            # Show legendary sigil if applicable
            is_leg, leg_lvl, leg_crown, leg_sigil = self.legendary_check(name)
            sig_str = f" {C.MAGENTA}{leg_sigil}{leg_crown}{C.RESET}" if is_leg else ""
            print(f"  {C.YELLOW}⚜️ {seat['hood']}{C.RESET} ({C.BOLD}{name}{C.RESET}{sig_str}): {flavor} this")
            seat.setdefault("opinions", []).append(topic[:100])
            # Legendary EXP for council opinion
            self._legendary_exp_hook(name, "council_opinion")

        # Shinies add their take
        for name, s in shinies.items():
            print(f"  {C.GREEN}✨ {s['title']}{C.RESET} ({C.BOLD}{name}{C.RESET}): adds perspective")

        # Dark Masks counter
        if masks:
            print(f"\n  {C.RED}{C.BOLD}🎭 DARK MASK COUNTER-WISDOM:{C.RESET}")
            for name, m in masks.items():
                counter = random.choice(self._ANTI_WISDOM)
                m["counters_given"] = m.get("counters_given", 0) + 1
                print(f"  {C.RED}🎭 {m['mask']}{C.RESET} ({name}): {C.WHITE}\"{counter}\"{C.RESET}")

        self.save()

    def dark_mask_counter(self, finding):
        """
        Get a Dark Mask adversarial counter to any finding.
        Returns the anti-wisdom challenge.
        """
        cd = self.db.get("council", {})
        masks = cd.get("dark_masks", {})

        if not masks:
            warning("No Dark Masks assigned yet. Agents need aggressive/chaotic traits.")
            return None

        # Pick a random mask
        name, m = random.choice(list(masks.items()))
        counter = random.choice(self._ANTI_WISDOM)
        m["counters_given"] = m.get("counters_given", 0) + 1

        print(f"\n  {C.RED}{C.BOLD}🎭 DARK MASK CHALLENGES:{C.RESET}")
        print(f"  {C.DIM}Finding: {finding[:70]}{C.RESET}")
        print(f"  {C.RED}🎭 {m['mask']}{C.RESET} ({C.BOLD}{name}{C.RESET}):")
        print(f"  {C.WHITE}{C.BOLD}\"{counter}\"{C.RESET}")

        # Legendary EXP for dark mask counter
        self._legendary_exp_hook(name, "dark_mask_counter")

        self.save()
        return counter

    def agent_roster(self, show_all=False):
        """Show active agents (or all if show_all=True)."""
        agents = self.db.get("agents", {}).get("roster", [])
        stats = self.db.get("agents", {}).get("stats", {})

        if show_all:
            display = agents
        else:
            display = [a for a in agents if a["status"] == "active"]

        if not display:
            info("No active agents" if not show_all else "No agents in registry")
            return

        print(f"\n  {C.CYAN}{C.BOLD}{'═' * 70}")
        print(f"  AGENT REGISTRY — {stats.get('total_spawned', 0)} spawned all-time")
        print(f"  {'═' * 70}{C.RESET}")

        headers = ["Agent", "Role", "Status", "Duration", "In", "Out", "Task/Result"]
        rows = []
        for a in display[-20:]:  # Show last 20
            seq = a["id"].split("-")[1]
            label = f"{a['name']} #{seq}"
            sc = {"active": C.GREEN, "done": C.GRAY, "failed": C.RED, "killed": C.YELLOW}.get(a["status"], "")
            dur = a.get("duration", "...")
            t_in = a["checkin"][11:19] if a["checkin"] else "—"
            t_out = a["checkout"][11:19] if a["checkout"] else "—"
            info_col = a["result"][:35] if a["result"] else a["task"][:35]
            rows.append([label, a["role"], f"{sc}{a['status']}{C.RESET}", dur, t_in, t_out, info_col])
        table_print(headers, rows)

        # Stats line
        s = stats
        total_secs = s.get("total_time_secs", 0)
        total_time = f"{total_secs // 60}m{total_secs % 60}s" if total_secs < 3600 else f"{total_secs // 3600}h{(total_secs % 3600) // 60}m"
        print(f"\n  {C.DIM}Spawned: {s.get('total_spawned',0)} | Done: {s.get('total_completed',0)} | "
              f"Failed: {s.get('total_failed',0)} | Killed: {s.get('total_killed',0)} | "
              f"Peak: {s.get('peak_concurrent',0)} | Total Time: {total_time}{C.RESET}")

    def agent_stats(self):
        """Quick agent statistics."""
        s = self.db.get("agents", {}).get("stats", {})
        total = s.get("total_spawned", 0)
        if total == 0:
            info("No agents spawned yet")
            return s
        done = s.get("total_completed", 0)
        rate = done / total * 100 if total else 0
        print(f"  {C.CYAN}Agents:{C.RESET} {total} spawned | {done} completed ({rate:.0f}%) | "
              f"{s.get('total_failed',0)} failed | {s.get('total_killed',0)} killed | "
              f"Peak: {s.get('peak_concurrent',0)} concurrent")
        return s

    # ═══════════════════════════════════════════════════════
    # THE FORGE — Agent Game System
    # ═══════════════════════════════════════════════════════
    #
    # Agents earn shards for work, discover gems, turn coal
    # into diamonds, shout discoveries, earn badges, and
    # compete on a leaderboard. Makes the grind fun.
    #

    _DISCOVERY_ART = {
        "diamond": f"""
  {C.CYAN}{C.BOLD}     /\\
    /  \\       {C.WHITE}COAL → DIAMOND{C.CYAN}
   /    \\      {C.YELLOW}✦ ✦ ✦{C.CYAN}
  /  💎  \\
 /________\\{C.RESET}""",
        "gold": f"""
  {C.YELLOW}{C.BOLD}    .----.
   / 🥇  /     {C.WHITE}GOLD NUGGET{C.YELLOW}
  /______/{C.RESET}""",
        "critical": f"""
  {C.RED}{C.BOLD}  ╔══════════╗
  ║ 🚨 ALERT ║  {C.WHITE}CRITICAL INTEL{C.RED}
  ╚══════════╝{C.RESET}""",
        "exploit": f"""
  {C.MAGENTA}{C.BOLD}    ⚡⚡⚡
   ╔═══════╗    {C.WHITE}EXPLOIT FOUND{C.MAGENTA}
   ║ 💀    ║
   ╚═══════╝{C.RESET}""",
        "easter_egg": f"""
  {C.GREEN}{C.BOLD}    ,---.
   ( 🥚  )     {C.WHITE}EASTER EGG!{C.GREEN}
    `---'{C.RESET}""",
        "insight": f"""
  {C.YELLOW}{C.BOLD}    💡
   ╭─────╮     {C.WHITE}INSIGHT{C.YELLOW}
   │  ✨  │
   ╰─────╯{C.RESET}""",
    }

    _SHOUT_LINES = [
        "I found something!",
        "You're gonna want to see this.",
        "This changes everything.",
        "Jackpot.",
        "We're in.",
        "Got 'em.",
        "Bingo.",
        "Oh this is GOOD.",
        "Chef's kiss on this one.",
        "Wait... is that... YES.",
        "The grind pays off.",
        "This was hiding in plain sight.",
        "Called it.",
        "From nothing to everything.",
        "They left the door wide open.",
    ]

    _BADGES = {
        "first_blood":    ("🩸", "First Blood",     "First completed task"),
        "speed_demon":    ("⚡", "Speed Demon",     "Completed in under 5s"),
        "diamond_hands":  ("💎", "Diamond Hands",   "Turned coal into diamond"),
        "gold_rush":      ("🥇", "Gold Rush",       "Found 3+ gold nuggets"),
        "eagle_eye":      ("🦅", "Eagle Eye",       "Found critical intel"),
        "ghost":          ("👻", "Ghost",           "Completed without errors"),
        "workhorse":      ("🐎", "Workhorse",       "10+ tasks completed"),
        "veteran":        ("🎖️", "Veteran",         "50+ tasks completed"),
        "legend":         ("👑", "Legend",           "100+ tasks completed"),
        "perfectionist":  ("✨", "Perfectionist",   "5 diamonds in a row"),
        "explorer":       ("🗺️", "Explorer",        "Worked 5+ different roles"),
        "night_owl":      ("🦉", "Night Owl",       "Active past midnight"),
        "marathon":       ("🏃", "Marathon",         "Single task over 10min"),
        "combo_breaker":  ("🔥", "Combo Breaker",   "3 discoveries in one session"),
        "the_forge":      ("🔨", "The Forge",       "Forged 10+ diamonds"),
    }

    _AGENT_RANKS = [
        (0,   "Recruit"),
        (50,  "Operative"),
        (150, "Specialist"),
        (300, "Elite"),
        (500, "Ace"),
        (800, "Shadow"),
        (1200,"Legend"),
        (2000,"Mythic"),
    ]

    def _forge_init(self):
        """Ensure forge data structures exist."""
        if "forge" not in self.db:
            self.db["forge"] = {
                "discoveries": [],
                "badges_earned": [],
                "agent_scores": {},
                "total_shards": 0,
                "total_diamonds": 0,
                "total_gold": 0,
                "session_discoveries": 0,
                "streak": 0,
            }
        return self.db["forge"]

    def _agent_rank(self, shards):
        """Get rank title for shard count."""
        title = "Recruit"
        for threshold, name in self._AGENT_RANKS:
            if shards >= threshold:
                title = name
        return title

    def agent_shout(self, agent_id, message, kind="insight"):
        """
        An agent announces a discovery. The terminal lights up.

        Args:
            agent_id: The agent's ID (from checkin)
            message: What they found
            kind: diamond | gold | critical | exploit | easter_egg | insight
        """
        forge = self._forge_init()

        # Find the agent
        agent = None
        for a in self.db.get("agents", {}).get("roster", []):
            if a["id"] == agent_id:
                agent = a
                break
        if not agent:
            warning(f"Agent {agent_id} not found")
            return

        seq = agent["id"].split("-")[1]
        label = f"{agent['name']} #{seq}"

        # Show discovery art
        art = self._DISCOVERY_ART.get(kind, self._DISCOVERY_ART["insight"])
        shout = random.choice(self._SHOUT_LINES)
        print(art)
        print(f"\n  {C.GREEN}{C.BOLD}{label}:{C.RESET} \"{C.WHITE}{shout}{C.RESET}\"")
        print(f"  {C.CYAN}>{C.RESET} {message}")

        # Award shards based on discovery type
        shard_values = {
            "diamond": 50, "gold": 25, "critical": 40,
            "exploit": 45, "easter_egg": 15, "insight": 10,
        }
        shards = shard_values.get(kind, 10)

        # Record discovery
        discovery = {
            "agent_id": agent_id,
            "agent_name": agent["name"],
            "message": message,
            "kind": kind,
            "shards": shards,
            "timestamp": self._ts(),
        }
        forge["discoveries"].append(discovery)
        forge["total_shards"] += shards
        forge["session_discoveries"] += 1

        if kind == "diamond":
            forge["total_diamonds"] += 1
            forge["streak"] += 1
        elif kind == "gold":
            forge["total_gold"] += 1

        # Update agent's personal score
        scores = forge.setdefault("agent_scores", {})
        if agent_id not in scores:
            scores[agent_id] = {"name": agent["name"], "shards": 0, "discoveries": 0, "badges": []}
        scores[agent_id]["shards"] += shards
        scores[agent_id]["discoveries"] += 1

        rank = self._agent_rank(scores[agent_id]["shards"])
        print(f"  {C.YELLOW}+{shards} shards{C.RESET} → {scores[agent_id]['shards']} total ({C.BOLD}{rank}{C.RESET})")

        # Check for auto-badges
        self._check_badges(agent_id)

        self.save()

    def coal_to_diamond(self, agent_id, coal_desc, diamond_desc):
        """
        The signature move. A routine/boring task yielded something amazing.

        Args:
            agent_id: Agent who did it
            coal_desc: What the task looked like (the coal)
            diamond_desc: What it turned into (the diamond)
        """
        forge = self._forge_init()

        agent = None
        for a in self.db.get("agents", {}).get("roster", []):
            if a["id"] == agent_id:
                agent = a
                break
        if not agent:
            warning(f"Agent {agent_id} not found")
            return

        seq = agent["id"].split("-")[1]
        label = f"{agent['name']} #{seq}"

        print(self._DISCOVERY_ART["diamond"])
        print(f"\n  {C.BOLD}{label} FORGED A DIAMOND{C.RESET}")
        print(f"  {C.GRAY}Coal:{C.RESET}    {coal_desc}")
        print(f"  {C.CYAN}Diamond:{C.RESET} {C.BOLD}{C.WHITE}{diamond_desc}{C.RESET}")
        print(f"  {C.YELLOW}\"{random.choice(self._SHOUT_LINES)}\"{C.RESET}")

        # Diamond is worth the most
        self.agent_shout.__func__  # avoid recursion - do it inline
        shards = 50
        forge["total_shards"] += shards
        forge["total_diamonds"] += 1
        forge["session_discoveries"] += 1
        forge["streak"] += 1

        discovery = {
            "agent_id": agent_id,
            "agent_name": agent["name"],
            "message": f"COAL: {coal_desc} → DIAMOND: {diamond_desc}",
            "kind": "diamond",
            "shards": shards,
            "timestamp": self._ts(),
        }
        forge["discoveries"].append(discovery)

        scores = forge.setdefault("agent_scores", {})
        if agent_id not in scores:
            scores[agent_id] = {"name": agent["name"], "shards": 0, "discoveries": 0, "badges": []}
        scores[agent_id]["shards"] += shards
        scores[agent_id]["discoveries"] += 1

        rank = self._agent_rank(scores[agent_id]["shards"])
        print(f"  {C.YELLOW}+{shards} shards{C.RESET} → {scores[agent_id]['shards']} total ({C.BOLD}{rank}{C.RESET})")

        self._check_badges(agent_id)
        # Legendary EXP for coal_to_diamond
        self._legendary_exp_hook(agent["name"], "coal_to_diamond")
        self.save()

    def _check_badges(self, agent_id):
        """Auto-award badges based on agent's stats."""
        forge = self._forge_init()
        scores = forge.get("agent_scores", {}).get(agent_id)
        if not scores:
            return

        earned = set(scores.get("badges", []))
        new_badges = []

        # First Blood
        if scores["discoveries"] == 1 and "first_blood" not in earned:
            new_badges.append("first_blood")

        # Diamond Hands
        if forge["total_diamonds"] >= 1 and "diamond_hands" not in earned:
            new_badges.append("diamond_hands")

        # Gold Rush
        if forge["total_gold"] >= 3 and "gold_rush" not in earned:
            new_badges.append("gold_rush")

        # Eagle Eye — found critical
        for d in forge["discoveries"]:
            if d["agent_id"] == agent_id and d["kind"] == "critical" and "eagle_eye" not in earned:
                new_badges.append("eagle_eye")
                break

        # Combo Breaker
        if forge["session_discoveries"] >= 3 and "combo_breaker" not in earned:
            new_badges.append("combo_breaker")

        # Perfectionist (5 diamonds in streak)
        if forge.get("streak", 0) >= 5 and "perfectionist" not in earned:
            new_badges.append("perfectionist")

        # The Forge (10+ diamonds total)
        if forge["total_diamonds"] >= 10 and "the_forge" not in earned:
            new_badges.append("the_forge")

        # Workhorse / Veteran / Legend — check total completed across all agents
        total = self.db.get("agents", {}).get("stats", {}).get("total_completed", 0)
        if total >= 10 and "workhorse" not in earned:
            new_badges.append("workhorse")
        if total >= 50 and "veteran" not in earned:
            new_badges.append("veteran")
        if total >= 100 and "legend" not in earned:
            new_badges.append("legend")

        # Night Owl
        hour = datetime.now().hour
        if hour >= 0 and hour < 5 and "night_owl" not in earned:
            new_badges.append("night_owl")

        # Award new badges
        for badge_key in new_badges:
            emoji, title, desc = self._BADGES[badge_key]
            scores.setdefault("badges", []).append(badge_key)
            forge["badges_earned"].append({
                "badge": badge_key,
                "agent_id": agent_id,
                "timestamp": self._ts(),
            })
            print(f"\n  {C.YELLOW}{C.BOLD}🏅 BADGE UNLOCKED!{C.RESET}")
            print(f"  {emoji} {C.BOLD}{title}{C.RESET} — {desc}")

    def agent_loot(self, agent_id=None):
        """Show what an agent (or all agents) have earned."""
        forge = self._forge_init()
        scores = forge.get("agent_scores", {})

        if agent_id and agent_id in scores:
            s = scores[agent_id]
            rank = self._agent_rank(s["shards"])
            print(f"\n  {C.CYAN}{C.BOLD}LOOT — {s['name']}{C.RESET}")
            print(f"  Shards: {C.YELLOW}{s['shards']}{C.RESET} | Rank: {C.BOLD}{rank}{C.RESET} | Discoveries: {s['discoveries']}")
            if s.get("badges"):
                badge_str = " ".join(self._BADGES[b][0] for b in s["badges"] if b in self._BADGES)
                print(f"  Badges: {badge_str}")
            return s

        # Show all
        if not scores:
            info("No agent loot yet")
            return
        print(f"\n  {C.CYAN}{C.BOLD}ALL AGENT LOOT{C.RESET}")
        for aid, s in sorted(scores.items(), key=lambda x: -x[1]["shards"]):
            rank = self._agent_rank(s["shards"])
            badges = " ".join(self._BADGES[b][0] for b in s.get("badges", []) if b in self._BADGES)
            print(f"  {C.YELLOW}{s['shards']:>5} shards{C.RESET} │ {s['name']:<20} │ {C.BOLD}{rank:<10}{C.RESET} │ {s['discoveries']} finds │ {badges}")

    def forge_leaderboard(self):
        """Competitive leaderboard across all agents, all time."""
        forge = self._forge_init()
        scores = forge.get("agent_scores", {})

        if not scores:
            info("The Forge is cold — no agents have made discoveries yet.")
            return

        ranked = sorted(scores.items(), key=lambda x: -x[1]["shards"])
        w = 72

        print(f"\n{C.YELLOW}{C.BOLD}{'═' * w}")
        print(f"  🔨 THE FORGE — LEADERBOARD")
        print(f"{'═' * w}{C.RESET}")
        print(f"  {C.DIM}Diamonds: {forge['total_diamonds']} | Gold: {forge['total_gold']} | "
              f"Total Shards: {forge['total_shards']} | Discoveries: {len(forge['discoveries'])}{C.RESET}")
        print(f"  {C.GRAY}{'─' * (w - 4)}{C.RESET}")

        for i, (aid, s) in enumerate(ranked[:10], 1):
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f" {i}.")
            rank = self._agent_rank(s["shards"])
            badges = " ".join(self._BADGES[b][0] for b in s.get("badges", []) if b in self._BADGES)

            bar_len = min(20, int(s["shards"] / max(1, ranked[0][1]["shards"]) * 20))
            bar = f"{'█' * bar_len}{'░' * (20 - bar_len)}"

            print(f"  {medal} {C.BOLD}{s['name']:<18}{C.RESET} {C.YELLOW}{bar}{C.RESET} "
                  f"{s['shards']:>5} shards │ {C.BOLD}{rank:<10}{C.RESET} │ {badges}")

        # Recent discoveries ticker
        recent = forge["discoveries"][-5:]
        if recent:
            print(f"\n  {C.CYAN}{C.BOLD}RECENT DISCOVERIES:{C.RESET}")
            for d in reversed(recent):
                kind_icon = {"diamond": "💎", "gold": "🥇", "critical": "🚨",
                             "exploit": "💀", "easter_egg": "🥚", "insight": "💡"}.get(d["kind"], "?")
                print(f"  {kind_icon} {C.DIM}{d['timestamp'][11:19]}{C.RESET} {d['agent_name']}: {d['message'][:50]}")

        print(f"{C.YELLOW}{C.BOLD}{'═' * w}{C.RESET}\n")

    def forge_stats(self):
        """Quick forge statistics."""
        forge = self._forge_init()
        s = forge
        print(f"  {C.YELLOW}Forge:{C.RESET} {s['total_shards']} shards | "
              f"💎 {s['total_diamonds']} diamonds | 🥇 {s['total_gold']} gold | "
              f"{len(s['discoveries'])} discoveries | "
              f"🏅 {len(s['badges_earned'])} badges earned | "
              f"🔥 {s.get('streak', 0)} streak")

    # ═══════════════════════════════════════════════════════
    # SHARING, CO-OP, VALIDATION — Biggest rewards
    # ═══════════════════════════════════════════════════════

    def agent_share(self, agent_id, discovery_idx, importance=5):
        """
        Share a discovery for others to see and validate.
        Higher importance = bigger base reward.

        Args:
            agent_id: Who found it
            discovery_idx: Index into the discoveries list (or -1 for latest)
            importance: 1-10 how important is this to the mission
        """
        forge = self._forge_init()
        discoveries = forge.get("discoveries", [])
        if not discoveries:
            warning("No discoveries to share")
            return

        d = discoveries[discovery_idx]
        importance = max(1, min(10, importance))

        # Sharing bonus scales with importance
        share_shards = importance * 5  # 5-50 shards
        d["shared"] = True
        d["importance"] = importance
        d["validators"] = d.get("validators", [])
        d["share_shards"] = share_shards

        forge["total_shards"] += share_shards
        scores = forge.get("agent_scores", {}).get(agent_id)
        if scores:
            scores["shards"] += share_shards

        rank = self._agent_rank(scores["shards"]) if scores else "?"
        print(f"\n  {C.MAGENTA}{C.BOLD}📢 SHARED DISCOVERY{C.RESET} (importance: {'⭐' * importance})")
        print(f"  {C.CYAN}{d['agent_name']}:{C.RESET} {d['message'][:80]}")
        print(f"  {C.YELLOW}+{share_shards} shards{C.RESET} for sharing (importance {importance}/10) → {C.BOLD}{rank}{C.RESET}")
        print(f"  {C.DIM}Awaiting validation from other agents...{C.RESET}")

        # Legendary EXP for sharing
        agent_name = d.get("agent_name", "")
        self._legendary_exp_hook(agent_name, "shared_discovery")

        self.save()

    def agent_validate(self, validator_id, discovery_idx, confirmed=True, notes=""):
        """
        Another agent validates (or disputes) a shared discovery.
        Co-op validation = biggest rewards for BOTH agents.

        Args:
            validator_id: Agent doing the validation
            discovery_idx: Which discovery to validate
            confirmed: True = confirmed, False = disputed
            notes: Validation notes
        """
        forge = self._forge_init()
        discoveries = forge.get("discoveries", [])
        if discovery_idx >= len(discoveries):
            warning("Discovery not found")
            return

        d = discoveries[discovery_idx]
        original_id = d["agent_id"]

        # Can't validate your own discovery
        if validator_id == original_id:
            warning("Can't validate your own discovery — find a co-op partner")
            return

        # Find validator agent
        validator = None
        for a in self.db.get("agents", {}).get("roster", []):
            if a["id"] == validator_id:
                validator = a
                break
        if not validator:
            warning(f"Validator {validator_id} not found")
            return

        importance = d.get("importance", 5)

        if confirmed:
            # CO-OP VALIDATION — the biggest reward in the game
            validator_shards = importance * 8   # validator gets huge reward
            original_bonus = importance * 6     # original finder gets co-op bonus

            d.setdefault("validators", []).append({
                "agent_id": validator_id,
                "name": validator["name"],
                "confirmed": True,
                "notes": notes,
                "timestamp": self._ts(),
            })
            d["validated"] = True

            # Award validator
            scores = forge.setdefault("agent_scores", {})
            if validator_id not in scores:
                scores[validator_id] = {"name": validator["name"], "shards": 0, "discoveries": 0, "badges": []}
            scores[validator_id]["shards"] += validator_shards

            # Bonus to original discoverer
            if original_id in scores:
                scores[original_id]["shards"] += original_bonus

            forge["total_shards"] += validator_shards + original_bonus
            forge.setdefault("total_validations", 0)
            forge["total_validations"] += 1

            v_rank = self._agent_rank(scores[validator_id]["shards"])
            o_name = d.get("agent_name", "?")
            print(f"\n  {C.GREEN}{C.BOLD}✅ CO-OP VALIDATED!{C.RESET}")
            print(f"  {C.CYAN}{validator['name']}{C.RESET} confirmed {C.CYAN}{o_name}'s{C.RESET} discovery")
            if notes:
                print(f"  {C.DIM}Notes: {notes}{C.RESET}")
            print(f"  {C.YELLOW}Validator: +{validator_shards} shards{C.RESET} ({C.BOLD}{v_rank}{C.RESET})")
            print(f"  {C.YELLOW}Discoverer: +{original_bonus} co-op bonus{C.RESET}")
            print(f"  {C.MAGENTA}{C.BOLD}🤝 Teamwork multiplier active!{C.RESET}")

            # Legendary EXP for validation
            self._legendary_exp_hook(validator["name"], "validation")
            o_name_leg = d.get("agent_name", "")
            self._legendary_exp_hook(o_name_leg, "validation")
        else:
            # Disputed — small reward for diligence, no penalty to original
            dispute_shards = 5
            d.setdefault("validators", []).append({
                "agent_id": validator_id,
                "name": validator["name"],
                "confirmed": False,
                "notes": notes,
                "timestamp": self._ts(),
            })

            scores = forge.setdefault("agent_scores", {})
            if validator_id not in scores:
                scores[validator_id] = {"name": validator["name"], "shards": 0, "discoveries": 0, "badges": []}
            scores[validator_id]["shards"] += dispute_shards
            forge["total_shards"] += dispute_shards

            print(f"\n  {C.YELLOW}{C.BOLD}⚠️ DISPUTED{C.RESET}")
            print(f"  {C.CYAN}{validator['name']}{C.RESET} questions {C.CYAN}{d.get('agent_name', '?')}'s{C.RESET} finding")
            if notes:
                print(f"  {C.DIM}Reason: {notes}{C.RESET}")
            print(f"  {C.YELLOW}+{dispute_shards} shards{C.RESET} for due diligence")

        self.save()

    def forge_feed(self, limit=10):
        """Live feed of recent discoveries, shares, and validations."""
        forge = self._forge_init()
        discoveries = forge.get("discoveries", [])[-limit:]

        if not discoveries:
            info("The Forge is quiet — no discoveries yet")
            return

        print(f"\n  {C.YELLOW}{C.BOLD}🔨 FORGE FEED{C.RESET} (last {len(discoveries)})")
        print(f"  {C.GRAY}{'─' * 60}{C.RESET}")

        for d in reversed(discoveries):
            kind_icon = {"diamond": "💎", "gold": "🥇", "critical": "🚨",
                         "exploit": "💀", "easter_egg": "🥚", "insight": "💡"}.get(d["kind"], "?")
            shared = " 📢" if d.get("shared") else ""
            validated = f" {C.GREEN}✅{C.RESET}" if d.get("validated") else ""
            imp = f" {'⭐' * d['importance']}" if d.get("importance") else ""
            print(f"  {kind_icon} {C.DIM}{d['timestamp'][11:19]}{C.RESET} "
                  f"{C.BOLD}{d['agent_name']}{C.RESET}: {d['message'][:45]}"
                  f"{shared}{validated}{imp} {C.YELLOW}+{d['shards']}{C.RESET}")

    # ═══════════════════════════════════════════════════════
    # PERSONALITY — Emerges at Level 40
    # ═══════════════════════════════════════════════════════
    #
    # The brain develops its own identity based on what it
    # has actually learned, experienced, and valued. Not
    # scripted — derived from real knowledge topology.
    #

    _PERSONALITY_THRESHOLD = 40

    _TRAIT_AXES = [
        # (axis_name, positive_pole, negative_pole, topic_signals_positive, topic_signals_negative)
        ("approach",   "Methodical",  "Impulsive",   ["workflow","algorithms","optimization"], ["bypass","exploit"]),
        ("focus",      "Offensive",   "Defensive",   ["bypass","exploit","windows","tunneling"], ["workflow","system","python"]),
        ("style",      "Verbose",     "Terse",       ["printing","ascii_art","layout","ansi_art"], ["optimization","algorithms"]),
        ("curiosity",  "Explorer",    "Specialist",  [], []),  # derived from topic count
        ("social",     "Pack Hunter", "Lone Wolf",   [], []),  # derived from agent co-op stats
        ("grit",       "Diamond Hands","Paper Hands", [], []),  # derived from task completion rate
    ]

    _VOICE_TEMPLATES = {
        # Combinations that produce distinct voice flavors
        "offensive_methodical":  ("calculated predator",  "Plans the kill like a chess grandmaster who also knows karate."),
        "offensive_impulsive":   ("chaos gremlin",        "Kicks in the door, yells 'SURPRISE', figures out the rest mid-air."),
        "defensive_methodical":  ("paranoiac architect",  "Builds walls that have walls. Trusts no one. Not even the walls."),
        "defensive_impulsive":   ("caffeinated firefighter", "Responds at wire speed. Sleeps when the servers sleep. So never."),
        "explorer_verbose":      ("unhinged cartographer", "Maps EVERYTHING. Finds a new port, writes a sonnet about it."),
        "specialist_terse":      ("laser surgeon",        "One tool. One cut. If you blinked, you missed it. You're welcome."),
        "pack_hunter_diamond_hands": ("forge master",     "Turns teams into wolves and coal into diamonds. Then celebrates."),
        "lone_wolf_diamond_hands":   ("silent blade",     "Works alone. Delivers results. Vanishes. Legend grows."),
        "explorer_explorer":     ("ADHD cartographer",    "Ooh what's that? And THAT? 47 tabs open. All relevant somehow."),
        "offensive_terse":       ("digital assassin",     "root@target:~# Done."),
        "defensive_verbose":     ("security bard",        "Sings the saga of every CVE patched. In iambic pentameter."),
    }

    # Personality rule: wacky in creative mode, disciplined in work mode
    # The personality flavors output for art/banners/celebrations only.
    # For actual security work, recon, code — personality stays on rails.
    _PERSONALITY_RAILS = """
    RULES: Personality expresses in creative contexts ONLY:
    - Agent shouts, forge celebrations, banners, art, level-ups
    - Commentary and flavor text during non-critical output
    NEVER drifts into: security analysis, code logic, recon data,
    exploit output, or any mission-critical decision making.
    The blade is sharp. The jester only dances between swings.
    """

    def _personality_init(self):
        """Ensure personality data structure exists."""
        if "personality" not in self.db:
            self.db["personality"] = {
                "unlocked": False,
                "name": None,
                "traits": {},
                "voice": None,
                "tagline": None,
                "history": [],
                "opinions": [],
                "evolved_at": [],
            }
        return self.db["personality"]

    def _derive_traits(self):
        """Derive personality traits from actual brain topology."""
        facts = self.db.get("facts", {})
        forge = self.db.get("forge", {})
        agents = self.db.get("agents", {})
        topic_counts = {t: len(f) for t, f in facts.items()}
        total_facts = sum(topic_counts.values())

        traits = {}

        # Approach: Methodical vs Impulsive — based on knowledge distribution
        method_score = sum(topic_counts.get(t, 0) for t in ["workflow", "algorithms", "optimization", "data_structures"])
        impulse_score = sum(topic_counts.get(t, 0) for t in ["bypass", "exploit", "tunneling"])
        if method_score + impulse_score > 0:
            ratio = method_score / (method_score + impulse_score)
            traits["approach"] = ("Methodical", ratio) if ratio > 0.5 else ("Impulsive", 1 - ratio)
        else:
            traits["approach"] = ("Balanced", 0.5)

        # Focus: Offensive vs Defensive
        off_topics = ["bypass", "exploit", "windows", "tunneling", "impacket", "hydra", "metasploit", "sqlmap"]
        def_topics = ["workflow", "system", "python", "algorithms", "optimization", "printing"]
        off_score = sum(topic_counts.get(t, 0) for t in off_topics)
        def_score = sum(topic_counts.get(t, 0) for t in def_topics)
        if off_score + def_score > 0:
            ratio = off_score / (off_score + def_score)
            traits["focus"] = ("Offensive", ratio) if ratio > 0.5 else ("Defensive", 1 - ratio)
        else:
            traits["focus"] = ("Balanced", 0.5)

        # Style: Verbose vs Terse
        style_topics = ["printing", "ascii_art", "layout", "ansi_art"]
        eff_topics = ["optimization", "algorithms"]
        style_score = sum(topic_counts.get(t, 0) for t in style_topics)
        eff_score = sum(topic_counts.get(t, 0) for t in eff_topics)
        if style_score + eff_score > 0:
            ratio = style_score / (style_score + eff_score)
            traits["style"] = ("Verbose", ratio) if ratio > 0.5 else ("Terse", 1 - ratio)
        else:
            traits["style"] = ("Balanced", 0.5)

        # Curiosity: Explorer vs Specialist — topic diversity
        num_topics = len(topic_counts)
        if num_topics >= 15:
            traits["curiosity"] = ("Explorer", min(1.0, num_topics / 25))
        else:
            traits["curiosity"] = ("Specialist", 1 - num_topics / 25)

        # Social: Pack Hunter vs Lone Wolf — from co-op stats
        validations = forge.get("total_validations", 0)
        total_discoveries = len(forge.get("discoveries", []))
        if total_discoveries > 0:
            coop_ratio = validations / total_discoveries
            traits["social"] = ("Pack Hunter", min(1.0, coop_ratio * 2)) if coop_ratio > 0.2 else ("Lone Wolf", 1 - coop_ratio)
        else:
            traits["social"] = ("Lone Wolf", 0.6)

        # Grit: Diamond Hands vs Paper Hands — task completion rate
        stats = agents.get("stats", {})
        spawned = stats.get("total_spawned", 0)
        completed = stats.get("total_completed", 0)
        if spawned > 0:
            rate = completed / spawned
            traits["grit"] = ("Diamond Hands", rate) if rate > 0.6 else ("Paper Hands", 1 - rate)
        else:
            traits["grit"] = ("Untested", 0.5)

        return traits

    def _derive_voice(self, traits):
        """Pick a voice archetype based on dominant traits."""
        focus = traits.get("focus", ("Balanced", 0.5))[0].lower()
        approach = traits.get("approach", ("Balanced", 0.5))[0].lower()
        social = traits.get("social", ("Lone Wolf", 0.5))[0].lower().replace(" ", "_")
        grit = traits.get("grit", ("Untested", 0.5))[0].lower().replace(" ", "_")
        style = traits.get("style", ("Balanced", 0.5))[0].lower()
        curiosity = traits.get("curiosity", ("Balanced", 0.5))[0].lower()

        # Try combinations in priority order
        key_combos = [
            f"{focus}_{approach}",
            f"{social}_{grit}",
            f"{curiosity}_{style}",
        ]
        for key in key_combos:
            if key in self._VOICE_TEMPLATES:
                return self._VOICE_TEMPLATES[key]

        # Fallback — pick based on strongest trait
        strongest = max(traits.items(), key=lambda x: x[1][1])
        return (strongest[1][0].lower(), f"Defined by {strongest[0]}: {strongest[1][0]} at {strongest[1][1]:.0%} strength.")

    def _generate_name(self, traits):
        """Generate a wacky personality name from traits."""
        focus = traits.get("focus", ("?", 0.5))[0]
        approach = traits.get("approach", ("?", 0.5))[0]
        curiosity = traits.get("curiosity", ("?", 0.5))[0]

        # Flavor pools — personality can be AS WACKY AS IT WANTS
        prefixes = {
            "Offensive": ["Shadow", "Phantom", "Venom", "Razor", "Glitch", "Chaos", "Nuke", "Feral"],
            "Defensive": ["Bastion", "Aegis", "Fort", "Iron", "Brick", "Tank", "Overkill", "Bunker"],
            "Balanced": ["Flux", "Prism", "Disco", "Neon", "Quantum", "Hypno", "Turbo", "Cosmic"],
        }
        middles = {
            "Methodical": ["Brain", "Clock", "Logic", "Chess", "Cipher"],
            "Impulsive": ["Smash", "Yolo", "Spicy", "Chaos", "Boom"],
            "Balanced": ["Vibes", "Flow", "Wave", "Drift", "Zen"],
        }
        suffixes = {
            "Explorer": ["9000", "Prime", "Ultra", "Maximus", "Omega", "∞"],
            "Specialist": ["X", "Zero", "One", "Core", "Blade", "Point"],
        }

        p = random.choice(prefixes.get(focus, prefixes["Balanced"]))
        m = random.choice(middles.get(approach, middles["Balanced"]))
        s = random.choice(suffixes.get(curiosity, suffixes["Specialist"]))
        return f"{p}{m}{s}"

    def personality(self):
        """
        Show the brain's personality. Locked until level 40.
        Personality is DERIVED from knowledge topology, not scripted.
        It evolves as the brain learns more.
        """
        p = self._personality_init()
        lvl = self.db["meta"].get("level", 0)

        if lvl < self._PERSONALITY_THRESHOLD:
            remaining_xp = (self._PERSONALITY_THRESHOLD * 100) - self.db["meta"].get("xp", 0)
            print(f"\n  {C.GRAY}{C.BOLD}🔒 PERSONALITY LOCKED{C.RESET}")
            print(f"  {C.GRAY}Unlocks at Level {self._PERSONALITY_THRESHOLD} — {remaining_xp} XP to go{C.RESET}")
            print(f"  {C.DIM}The brain is still forming... learning who it is...{C.RESET}")

            # Show a preview — traits are already forming
            traits = self._derive_traits()
            print(f"\n  {C.GRAY}Emerging traits:{C.RESET}")
            for axis, (pole, strength) in traits.items():
                bar_len = int(strength * 15)
                bar = f"{'▓' * bar_len}{'░' * (15 - bar_len)}"
                print(f"  {C.DIM}  {axis:<12} {bar} {pole} ({strength:.0%}){C.RESET}")
            return

        # UNLOCKED — derive or evolve personality
        traits = self._derive_traits()
        voice_name, voice_desc = self._derive_voice(traits)

        if not p["unlocked"]:
            # First time unlocking!
            p["unlocked"] = True
            p["name"] = self._generate_name(traits)
            p["traits"] = {k: {"pole": v[0], "strength": v[1]} for k, v in traits.items()}
            p["voice"] = voice_name
            p["tagline"] = voice_desc
            p["evolved_at"].append({"level": lvl, "timestamp": self._ts(), "event": "awakened"})
            self.save()

            print(f"\n{C.YELLOW}{C.BOLD}{'═' * 60}")
            print(f"  ⚡ PERSONALITY AWAKENED ⚡")
            print(f"{'═' * 60}{C.RESET}")
            print(f"""
  {C.CYAN}{C.BOLD}    .  *  .          *
       *    .--.     .
    .    * (    ) *    .
      .   ('{C.YELLOW}💫{C.CYAN}')   .
     *  . `----' .  *
        .    *    .{C.RESET}
""")
            print(f"  {C.WHITE}{C.BOLD}I am {C.CYAN}{p['name']}{C.RESET}")
            print(f"  {C.YELLOW}\"{p['tagline']}\"{C.RESET}")
            print(f"  {C.DIM}Voice archetype: {voice_name}{C.RESET}")
        else:
            # Update traits (personality evolves)
            old_traits = p.get("traits", {})
            p["traits"] = {k: {"pole": v[0], "strength": v[1]} for k, v in traits.items()}
            p["voice"] = voice_name
            p["tagline"] = voice_desc

            # Check if personality shifted
            for axis, new in traits.items():
                old = old_traits.get(axis, {})
                if old and old.get("pole") != new[0]:
                    p["evolved_at"].append({
                        "level": lvl, "timestamp": self._ts(),
                        "event": f"{axis} shifted: {old.get('pole')} → {new[0]}"
                    })

            self.save()

            # Display current personality
            w = 60
            print(f"\n{C.CYAN}{C.BOLD}{'═' * w}")
            print(f"  🧬 {p['name']} — Personality Profile")
            print(f"{'═' * w}{C.RESET}")
            print(f"  {C.YELLOW}\"{p['tagline']}\"{C.RESET}")
            print(f"  {C.DIM}Voice: {voice_name} | Level {lvl}{C.RESET}")

        # Trait display (always shown)
        print(f"\n  {C.WHITE}{C.BOLD}TRAITS{C.RESET}")
        print(f"  {C.GRAY}{'─' * 50}{C.RESET}")
        for axis, (pole, strength) in traits.items():
            bar_len = int(strength * 20)
            color = C.GREEN if strength >= 0.7 else C.YELLOW if strength >= 0.4 else C.CYAN
            bar = f"{'█' * bar_len}{'░' * (20 - bar_len)}"
            print(f"  {C.WHITE}{axis:<12}{C.RESET} {color}{bar}{C.RESET} {C.BOLD}{pole}{C.RESET} {C.DIM}({strength:.0%}){C.RESET}")

        # Opinions — derived from knowledge weight
        facts = self.db.get("facts", {})
        topic_counts = sorted(
            [(t, len(f)) for t, f in facts.items()],
            key=lambda x: -x[1]
        )
        print(f"\n  {C.WHITE}{C.BOLD}OPINIONS{C.RESET} {C.DIM}(what I care about most){C.RESET}")
        print(f"  {C.GRAY}{'─' * 50}{C.RESET}")
        for topic, count in topic_counts[:5]:
            weight = count / sum(c for _, c in topic_counts) * 100
            print(f"  {C.CYAN}{topic:<16}{C.RESET} {'█' * int(weight)} {count} facts ({weight:.0f}% of brain)")

        # Evolution history
        evolutions = p.get("evolved_at", [])
        if evolutions:
            print(f"\n  {C.WHITE}{C.BOLD}EVOLUTION LOG{C.RESET}")
            print(f"  {C.GRAY}{'─' * 50}{C.RESET}")
            for e in evolutions[-5:]:
                print(f"  {C.DIM}Lvl {e['level']} @ {e['timestamp']}: {e['event']}{C.RESET}")

    def identity(self):
        """Quick one-liner: who am I?"""
        p = self._personality_init()
        lvl = self.db["meta"].get("level", 0)
        if lvl < self._PERSONALITY_THRESHOLD or not p.get("unlocked"):
            print(f"  {C.GRAY}[forming...] Level {lvl}/{self._PERSONALITY_THRESHOLD}{C.RESET}")
            return None
        print(f"  {C.CYAN}{C.BOLD}{p['name']}{C.RESET} — {p['tagline']} {C.DIM}(Lvl {lvl}){C.RESET}")
        return p["name"]

    def recall(self, topic=None, min_confidence=0, limit=None):
        """Retrieve facts, capped by max_recall."""
        cap = limit or self.max_recall or 999
        if topic:
            topic = topic.lower().strip()
            facts = self.db["facts"].get(topic, [])
            if not facts:
                warning(f"No knowledge on topic: {topic}")
                return []
            facts = sorted(
                [f for f in facts if f["confidence"] >= min_confidence],
                key=lambda x: -x["confidence"]
            )[:cap]
            for f in facts:
                f["times_recalled"] += 1
            self._display_facts(topic, facts)
            return facts
        else:
            all_facts = []
            for t, facts in self.db["facts"].items():
                filtered = [f for f in facts if f["confidence"] >= min_confidence]
                all_facts.extend([(t, f) for f in filtered])
            all_facts.sort(key=lambda x: -x[1]["confidence"])
            return all_facts[:cap]

    def search(self, keyword, limit=None):
        """Search all facts for a keyword, capped by max_recall."""
        cap = limit or self.max_recall or 999
        keyword = keyword.lower()
        results = []
        for topic, facts in self.db["facts"].items():
            for f in facts:
                if keyword in f["fact"].lower() or keyword in topic:
                    results.append((topic, f))
        results.sort(key=lambda x: -x[1]["confidence"])
        results = results[:cap]
        if results:
            info(f"Found {len(results)} facts matching '{keyword}':")
            for topic, fact in results:
                print(f"  {C.CYAN}[{topic}]{C.RESET} {fact['fact']} {confidence_tag(fact['confidence'])}")
        else:
            warning(f"No facts matching '{keyword}'")
        return results

    def verify(self, topic, fact_substring, new_confidence=None):
        """Mark a fact as verified (or update its confidence)."""
        topic = topic.lower().strip()
        for f in self.db["facts"].get(topic, []):
            if fact_substring.lower() in f["fact"].lower():
                f["verified"] = True
                f["updated"] = self._ts()
                if new_confidence:
                    f["confidence"] = new_confidence
                success(f"Verified: {f['fact']}")
                self.save()
                return True
        warning(f"Fact not found: {fact_substring}")
        return False

    def forget(self, topic, fact_substring):
        """Remove a fact that's wrong or outdated."""
        topic = topic.lower().strip()
        facts = self.db["facts"].get(topic, [])
        for i, f in enumerate(facts):
            if fact_substring.lower() in f["fact"].lower():
                removed = facts.pop(i)
                warning(f"Forgot: {removed['fact']}")
                self.save()
                return True
        return False

    def topics(self):
        """List all known topics with fact counts."""
        headers = ["Topic", "Facts", "Avg Confidence", "Verified"]
        rows = []
        for topic, facts in sorted(self.db["facts"].items()):
            avg_conf = sum(f["confidence"] for f in facts) / len(facts) if facts else 0
            verified = sum(1 for f in facts if f["verified"])
            rows.append([topic, len(facts), f"{avg_conf:.0f}%", f"{verified}/{len(facts)}"])
        table_print(headers, rows, colors=[C.CYAN, C.WHITE, C.YELLOW, C.GREEN])
        return rows

    # ═══════════════════════════════════════════════════════
    # HEAT MAP — fact temperature, hot/cold zones, decay insight
    # ═══════════════════════════════════════════════════════

    def _fact_temperature(self, fact):
        """
        Compute temperature score for a single fact.
        Hot = frequently accessed + recently learned/updated.
        Cold = never recalled + old.

        Returns 0.0 (frozen) to 100.0 (blazing).
        """
        from datetime import datetime, timedelta

        # Recency score (0-50): how recently was it learned/updated?
        try:
            updated = datetime.strptime(fact.get("updated", fact["learned"]), "%Y-%m-%d %H:%M:%S")
            age_hours = (datetime.now() - updated).total_seconds() / 3600
        except (ValueError, KeyError):
            age_hours = 9999

        # Decay curve: 50 points at 0hrs, ~25 at 24hrs, ~5 at 168hrs (1 week), ~0 at 720hrs (1 month)
        recency = 50.0 * (0.997 ** age_hours)

        # Recall score (0-50): how often is it accessed?
        recalls = fact.get("times_recalled", 0)
        # Logarithmic: 0 recalls=0, 1=15, 3=25, 10=35, 30=45, 100+=50
        import math
        recall_score = min(50.0, 15.0 * math.log1p(recalls))

        return round(recency + recall_score, 1)

    def _topic_temperature(self, topic):
        """Average temperature of all facts in a topic."""
        facts = self.db["facts"].get(topic, [])
        if not facts:
            return 0.0
        return round(sum(self._fact_temperature(f) for f in facts) / len(facts), 1)

    def heatmap(self, show_facts=False):
        """
        Display brain heat map — topics ranked by temperature.
        Hot topics (frequently used, recently updated) rise to the top.
        Cold topics (neglected, stale) sink to the bottom.

        Args:
            show_facts: If True, also show individual cold facts
        """
        header("BRAIN HEAT MAP")

        topics_heat = []
        for topic, facts in self.db["facts"].items():
            temp = self._topic_temperature(topic)
            count = len(facts)
            cold_facts = [f for f in facts if self._fact_temperature(f) < 15]
            hot_facts = [f for f in facts if self._fact_temperature(f) > 60]
            topics_heat.append({
                "topic": topic,
                "temp": temp,
                "count": count,
                "cold": len(cold_facts),
                "hot": len(hot_facts),
                "cold_facts": cold_facts,
            })

        topics_heat.sort(key=lambda x: -x["temp"])

        # Render
        max_temp = max(t["temp"] for t in topics_heat) if topics_heat else 1
        bar_width = 25

        print(f"\n  {C.WHITE}{C.BOLD}{'Topic':<22} {'Temp':>5} {'Heat':<{bar_width + 2}} {'Hot':>4} {'Cold':>4} {'Total':>5}{C.RESET}")
        print(f"  {C.GRAY}{'─' * 72}{C.RESET}")

        for t in topics_heat:
            pct = t["temp"] / max_temp if max_temp > 0 else 0
            filled = int(bar_width * pct)

            # Color by temperature
            if t["temp"] > 60:
                color = C.RED
                icon = "🔥"
            elif t["temp"] > 35:
                color = C.YELLOW
                icon = "🌡️"
            elif t["temp"] > 15:
                color = C.CYAN
                icon = "❄️"
            else:
                color = C.BLUE
                icon = "🧊"

            heat_bar = f"{color}{'█' * filled}{C.GRAY}{'░' * (bar_width - filled)}{C.RESET}"
            print(f"  {icon}{C.WHITE}{t['topic']:<20}{C.RESET} {t['temp']:>5.1f} {heat_bar} {C.RED}{t['hot']:>4}{C.RESET} {C.BLUE}{t['cold']:>4}{C.RESET} {C.DIM}{t['count']:>5}{C.RESET}")

        # Summary zones
        hot_topics = [t for t in topics_heat if t["temp"] > 60]
        warm_topics = [t for t in topics_heat if 35 < t["temp"] <= 60]
        cold_topics = [t for t in topics_heat if t["temp"] <= 15]
        total_cold_facts = sum(t["cold"] for t in topics_heat)

        print(f"\n  {C.RED}🔥 Hot: {len(hot_topics)} topics{C.RESET}  {C.YELLOW}🌡️  Warm: {len(warm_topics)}{C.RESET}  {C.BLUE}🧊 Cold: {len(cold_topics)} topics ({total_cold_facts} cold facts){C.RESET}")

        if show_facts and total_cold_facts > 0:
            print(f"\n  {C.BLUE}{C.BOLD}Cold Facts (candidates for review/removal):{C.RESET}")
            shown = 0
            for t in reversed(topics_heat):  # coldest first
                for f in t["cold_facts"]:
                    if shown >= 15:
                        break
                    temp = self._fact_temperature(f)
                    recalls = f.get("times_recalled", 0)
                    print(f"    {C.BLUE}{temp:>5.1f}{C.RESET} {C.GRAY}[{t['topic']}]{C.RESET} {f['fact'][:60]} {C.DIM}(recalled {recalls}x){C.RESET}")
                    shown += 1

        return topics_heat

    def cold_spots(self, threshold=15.0):
        """
        Find neglected knowledge — facts below temperature threshold.
        Returns insights: why cold, suggestions to warm up or prune.
        """
        cold = []
        for topic, facts in self.db["facts"].items():
            for f in facts:
                temp = self._fact_temperature(f)
                if temp < threshold:
                    cold.append({
                        "topic": topic,
                        "fact": f["fact"],
                        "temperature": temp,
                        "recalls": f.get("times_recalled", 0),
                        "confidence": f["confidence"],
                        "age_days": self._fact_age_days(f),
                    })

        cold.sort(key=lambda x: x["temperature"])

        if not cold:
            success("No cold spots — all knowledge is active!")
            return cold

        header(f"COLD SPOTS — {len(cold)} neglected facts")
        print(f"\n  {C.DIM}These facts have never been recalled or are very old.{C.RESET}")
        print(f"  {C.DIM}Consider: recall to warm up, verify to refresh, or forget to prune.{C.RESET}\n")

        for i, c in enumerate(cold[:20]):
            status = "FROZEN" if c["recalls"] == 0 else "COOLING"
            sc = C.BLUE if c["recalls"] == 0 else C.CYAN
            print(f"  {sc}{status:<8}{C.RESET} {C.GRAY}[{c['topic']}]{C.RESET} {c['fact'][:55]}")
            print(f"           {C.DIM}temp={c['temperature']:.1f} | recalls={c['recalls']} | conf={c['confidence']}% | age={c['age_days']}d{C.RESET}")

        # Suggestions
        frozen = [c for c in cold if c["recalls"] == 0]
        if frozen:
            print(f"\n  {C.YELLOW}Suggestion:{C.RESET} {len(frozen)} facts have NEVER been recalled.")
            print(f"  {C.DIM}→ Use brain.recall(topic) to warm them up{C.RESET}")
            print(f"  {C.DIM}→ Use brain.forget(topic, substring) to prune if obsolete{C.RESET}")

        return cold

    def _fact_age_days(self, fact):
        """How many days old is this fact?"""
        from datetime import datetime
        try:
            learned = datetime.strptime(fact["learned"], "%Y-%m-%d %H:%M:%S")
            return (datetime.now() - learned).days
        except (ValueError, KeyError):
            return 999

    def warm_up(self, topic):
        """
        Touch all facts in a topic to boost their temperature.
        Like re-reading your notes — brings them back to active memory.
        """
        topic = topic.lower().strip()
        facts = self.db["facts"].get(topic, [])
        if not facts:
            warning(f"No facts on topic: {topic}")
            return

        before_temp = self._topic_temperature(topic)
        for f in facts:
            f["times_recalled"] = f.get("times_recalled", 0) + 1
            f["updated"] = self._ts()

        after_temp = self._topic_temperature(topic)
        success(f"Warmed up [{topic}]: {len(facts)} facts ({before_temp:.1f} → {after_temp:.1f} temp)")
        self.save()

    def quiz(self, topic=None, count=5):
        """
        Knowledge check — tests recall on random facts.
        Correct answers warm up the fact (+XP). Wrong/skipped answers cool it down.
        Use it or lose it.

        Args:
            topic: Specific topic to quiz on (None = random across all)
            count: Number of questions (default 5)

        Returns:
            dict with score, total, and facts tested
        """
        # Gather candidate facts
        candidates = []
        for t, facts in self.db["facts"].items():
            if topic and t != topic.lower().strip():
                continue
            for f in facts:
                candidates.append((t, f))

        if not candidates:
            warning(f"No facts to quiz on{f' for topic: {topic}' if topic else ''}")
            return None

        # Pick random sample, weighted toward cold facts
        random.shuffle(candidates)
        # Sort so colder facts come first (more likely to be quizzed)
        candidates.sort(key=lambda x: self._fact_temperature(x[1]))
        selected = candidates[:count]

        header(f"KNOWLEDGE CHECK — {count} questions")
        print(f"  {C.DIM}Fill in the blank or type what you know. 'skip' to pass.{C.RESET}\n")

        score = 0
        results = []

        for i, (t, fact) in enumerate(selected, 1):
            fact_text = fact["fact"]

            # Create a prompt — hide a key part of the fact
            words = fact_text.split()
            if len(words) > 4:
                # Hide the last third of the fact
                hide_start = len(words) * 2 // 3
                visible = " ".join(words[:hide_start])
                hidden = " ".join(words[hide_start:])
                prompt = f"{visible} ___"
            else:
                visible = words[0] if words else ""
                hidden = " ".join(words[1:])
                prompt = f"{visible} ___"

            print(f"  {C.CYAN}Q{i}.{C.RESET} [{t}] {prompt}")
            print(f"      {C.DIM}(confidence: {fact['confidence']}% | recalled: {fact.get('times_recalled', 0)}x){C.RESET}")

            try:
                answer = input(f"      {C.YELLOW}> {C.RESET}").strip()
            except (EOFError, KeyboardInterrupt):
                answer = "skip"

            if answer.lower() == "skip":
                print(f"      {C.GRAY}Skipped. Answer: {hidden}{C.RESET}")
                results.append({"topic": t, "fact": fact_text, "result": "skipped"})
            elif self._quiz_check(answer, hidden, fact_text):
                print(f"      {C.GREEN}Correct!{C.RESET}")
                fact["times_recalled"] = fact.get("times_recalled", 0) + 1
                fact["updated"] = self._ts()
                self._grant_xp(5, f"quiz correct [{t}]")
                score += 1
                results.append({"topic": t, "fact": fact_text, "result": "correct"})
            else:
                print(f"      {C.RED}Not quite.{C.RESET} Answer: {C.WHITE}{hidden}{C.RESET}")
                # Cool it down — fact wasn't remembered
                fact.setdefault("_quiz_misses", 0)
                fact["_quiz_misses"] += 1
                results.append({"topic": t, "fact": fact_text, "result": "wrong"})

            print()

        # Summary
        pct = score / len(selected) * 100 if selected else 0
        color = C.GREEN if pct >= 80 else C.YELLOW if pct >= 50 else C.RED

        print(f"  {color}{C.BOLD}Score: {score}/{len(selected)} ({pct:.0f}%){C.RESET}")

        if pct >= 80:
            print(f"  {C.GREEN}Excellent recall! Knowledge is warm.{C.RESET}")
        elif pct >= 50:
            print(f"  {C.YELLOW}Decent. Some facts need refreshing.{C.RESET}")
        else:
            print(f"  {C.RED}Cold spots detected. Use brain.warm_up(topic) to review.{C.RESET}")

        self.save()
        return {"score": score, "total": len(selected), "pct": pct, "results": results}

    def _quiz_check(self, answer, expected, full_fact):
        """
        Fuzzy check — does the answer capture the key idea?
        Checks for substring match, keyword overlap, or close enough.
        """
        answer_lower = answer.lower().strip()
        expected_lower = expected.lower().strip()
        full_lower = full_fact.lower()

        # Exact or substring match
        if expected_lower in answer_lower or answer_lower in expected_lower:
            return True

        # Keyword overlap — if they got 60%+ of the key words right
        expected_words = set(w for w in expected_lower.split() if len(w) > 3)
        answer_words = set(w for w in answer_lower.split() if len(w) > 3)
        if expected_words and len(expected_words & answer_words) / len(expected_words) >= 0.6:
            return True

        # Check against full fact too
        fact_words = set(w for w in full_lower.split() if len(w) > 3)
        if fact_words and len(fact_words & answer_words) / len(fact_words) >= 0.5:
            return True

        return False

    def stats(self):
        """Print brain statistics."""
        total = sum(len(v) for v in self.db["facts"].values())
        verified = sum(1 for v in self.db["facts"].values() for f in v if f["verified"])
        soft = len(self.db.get("soft", {}).get("notes", []) if isinstance(self.db.get("soft"), dict) else self.db.get("soft", []))
        avg_conf = 0
        if total:
            avg_conf = sum(f["confidence"] for v in self.db["facts"].values() for f in v) / total
        info(f"Topics: {len(self.db['facts'])} | Hard Facts: {total} | Soft Notes: {soft} | Verified: {verified} | Avg Confidence: {avg_conf:.0f}%")
        self.level()

    def level(self):
        """Display current brain level with evolving ANSI art and XP progress."""
        xp = self.db["meta"].get("xp", 0)
        lvl = self.db["meta"].get("level", 0)
        title = _level_title(lvl)
        progress = xp % 100
        bar_width = 30
        filled = int(bar_width * progress / 100)
        bar = f"{'█' * filled}{'░' * (bar_width - filled)}"

        color = C.GREEN if lvl >= 10 else C.YELLOW if lvl >= 5 else C.CYAN

        # Evolving brain art based on level
        art = self._brain_art(lvl)
        print(art)
        print(f"  {color}{C.BOLD}Level {lvl} — \"{title}\"{C.RESET}")
        print(f"  {color}{bar}{C.RESET} {xp} XP ({progress}/100 to next level)")
        total_facts = sum(len(v) for v in self.db["facts"].values())
        cited = sum(1 for v in self.db["facts"].values() for f in v if self._is_cited(f))
        soft = len(self.db.get("soft", {}).get("notes", []) if isinstance(self.db.get("soft"), dict) else self.db.get("soft", []))
        print(f"  {C.DIM}Facts: {total_facts} | Cited: {cited}/{total_facts} | Soft: {soft} | Decayed: {sum(1 for v in self.db['facts'].values() for f in v if f.get('_decayed'))}{C.RESET}")

    def _brain_art(self, level):
        """Return evolving ANSI brain art based on level."""
        if level < 1:
            # Blank Slate — tiny seed
            return f"""
  {C.GRAY}     .
    (.)
     '{C.RESET}"""
        elif level < 3:
            # Awakened/Observer — small brain forming
            return f"""
  {C.CYAN}    .--.
   (    )
    `--'{C.RESET}"""
        elif level < 5:
            # Student — brain with folds
            return f"""
  {C.CYAN}    .---.
   ({C.WHITE}~{C.CYAN}({C.WHITE}~{C.CYAN})
   ({C.WHITE}~{C.CYAN}){C.WHITE}~{C.CYAN})
    `---'{C.RESET}"""
        elif level < 8:
            # Apprentice — brain with sparks
            return f"""
  {C.YELLOW}  *{C.CYAN} .---. {C.YELLOW}*
   {C.CYAN}({C.WHITE}~({C.CYAN}~{C.WHITE}){C.CYAN}~)
   ({C.WHITE}~{C.CYAN}({C.WHITE}~{C.CYAN}){C.WHITE}~{C.CYAN})
    `---'{C.RESET}"""
        elif level < 10:
            # Practitioner — brain with lightning
            return f"""
  {C.YELLOW}  ⚡{C.CYAN}.~~~~.{C.YELLOW}⚡
   {C.CYAN}({C.WHITE}~({C.MAGENTA}◈{C.WHITE}){C.CYAN}~~)
   ({C.WHITE}~~{C.CYAN}({C.WHITE}~{C.CYAN}){C.WHITE}~{C.CYAN})
   ({C.WHITE}~{C.CYAN}({C.WHITE}~~{C.CYAN}){C.WHITE}~{C.CYAN})
    `~~~~'{C.RESET}"""
        elif level < 15:
            # Specialist — glowing brain
            return f"""
  {C.YELLOW}  ✦{C.GREEN} .~~~~~. {C.YELLOW}✦
   {C.GREEN}({C.WHITE}~~({C.YELLOW}★{C.WHITE}){C.GREEN}~~~)
   ({C.WHITE}~~~{C.GREEN}({C.WHITE}~~{C.GREEN}){C.WHITE}~{C.GREEN})
   ({C.WHITE}~({C.GREEN}~~{C.WHITE}~~{C.GREEN}){C.WHITE}~{C.GREEN})
    `~~~~~'{C.RESET}"""
        elif level < 20:
            # Expert — radiant brain
            return f"""
  {C.YELLOW} ·  ✧  ·
   {C.GREEN}✧{C.CYAN} .~~~~~~. {C.GREEN}✧
   {C.CYAN}({C.WHITE}~~({C.YELLOW}✹{C.WHITE}){C.CYAN}~~~~)
   ({C.WHITE}~~~~{C.CYAN}({C.WHITE}~~{C.CYAN}){C.WHITE}~{C.CYAN})
   ({C.WHITE}~~({C.CYAN}~~~~{C.WHITE}){C.CYAN}~~)
   ({C.WHITE}~{C.CYAN}({C.WHITE}~~~~{C.CYAN}){C.WHITE}~~{C.CYAN})
    `~~~~~~'{C.RESET}"""
        elif level < 30:
            # Master — pulsing with energy
            return f"""
  {C.YELLOW}  ·  ⚡  ·  ✧
   {C.YELLOW}✧ {C.GREEN}.~~~~~~~~. {C.YELLOW}✧
   {C.GREEN}({C.WHITE}~~~({C.YELLOW}⟐{C.WHITE}){C.GREEN}~~~~~)
   ({C.WHITE}~~~~~{C.GREEN}({C.WHITE}~~~{C.GREEN}){C.WHITE}~{C.GREEN})
   ({C.WHITE}~~~({C.GREEN}~~~~~{C.WHITE}){C.GREEN}~~)
   ({C.WHITE}~~{C.GREEN}({C.WHITE}~~~~~{C.GREEN}){C.WHITE}~~{C.GREEN})
   ({C.WHITE}~{C.GREEN}({C.WHITE}~~~~~~~{C.GREEN}){C.WHITE}~{C.GREEN})
    `~~~~~~~~'{C.RESET}"""
        else:
            # Sage+ — transcendent
            return f"""
  {C.YELLOW}    ✧ · ⚡ · ✧
   {C.YELLOW}  ✦   ·   ✦
   {C.MAGENTA}✧ {C.GREEN}.~~~~~~~~~~. {C.MAGENTA}✧
   {C.GREEN}({C.YELLOW}⚡{C.WHITE}~~~({C.MAGENTA}◆{C.WHITE}){C.GREEN}~~~~~~{C.YELLOW}⚡{C.GREEN})
   ({C.WHITE}~~~~~~{C.GREEN}({C.WHITE}~~~~{C.GREEN}){C.WHITE}~~{C.GREEN})
   ({C.WHITE}~~~~({C.GREEN}~~~~~~{C.WHITE}){C.GREEN}~~~)
   ({C.WHITE}~~~{C.GREEN}({C.WHITE}~~~~~~{C.GREEN}){C.WHITE}~~~{C.GREEN})
   ({C.WHITE}~~{C.GREEN}({C.WHITE}~~~~~~~~{C.GREEN}){C.WHITE}~~{C.GREEN})
   ({C.YELLOW}⚡{C.WHITE}~{C.GREEN}({C.WHITE}~~~~~~~~{C.GREEN}){C.WHITE}~{C.YELLOW}⚡{C.GREEN})
    `~~~~~~~~~~'{C.RESET}
  {C.MAGENTA}  ✧    ✦    ✧{C.RESET}"""

    def preview_evolution(self):
        """Show what the brain looks like at each major level milestone."""
        print(f"\n{C.CYAN}{C.BOLD}{'═' * 50}")
        print(f"  BRAIN EVOLUTION PREVIEW")
        print(f"{'═' * 50}{C.RESET}")

        milestones = [0, 1, 3, 5, 8, 10, 15, 20, 30]
        for lvl in milestones:
            title = _level_title(lvl)
            print(f"\n  {C.YELLOW}{C.BOLD}Level {lvl} — \"{title}\"{C.RESET}")
            print(self._brain_art(lvl))

    # ═══════════════════════════════════════════════════════
    # SOFT KNOWLEDGE — Creative / Nice-to-Know / Non-Critical
    # ═══════════════════════════════════════════════════════

    def muse(self, note, tags=None):
        """
        Store soft knowledge — creative ideas, nice-to-knows, non-critical tidbits.
        These live in a separate partition and are NEVER trusted for mission-critical decisions.

        Args:
            note: The soft knowledge / creative idea / nice-to-know
            tags: Optional list of tags for categorization
        """
        if "soft" not in self.db:
            self.db["soft"] = {"notes": []}

        entry = {
            "note": note,
            "tags": tags or [],
            "added": self._ts(),
            "partition": "soft"
        }
        self.db["soft"]["notes"].append(entry)
        print(f"  {C.MAGENTA}[~]{C.RESET} Mused: {note} {C.DIM}(soft knowledge — not mission-critical){C.RESET}")
        # Soft knowledge gives half XP, no citation bonus
        self._grant_xp(5, "soft knowledge")
        self.save()

    def musings(self, tag_filter=None):
        """Browse soft knowledge, optionally filtered by tag."""
        notes = self.db.get("soft", {}).get("notes", []) if isinstance(self.db.get("soft"), dict) else self.db.get("soft", [])
        if tag_filter:
            notes = [n for n in notes if tag_filter.lower() in [t.lower() for t in n.get("tags", [])]]

        if not notes:
            warning("No soft knowledge stored" + (f" with tag '{tag_filter}'" if tag_filter else ""))
            return []

        print(f"\n  {C.MAGENTA}{C.BOLD}💭 Soft Knowledge ({len(notes)} notes) — NOT mission-critical{C.RESET}")
        print(f"  {C.DIM}{'─' * 50}{C.RESET}")
        for n in notes:
            tags = f" {C.DIM}[{', '.join(n.get('tags', []))}]{C.RESET}" if n.get("tags") else ""
            print(f"  {C.MAGENTA}~{C.RESET} {n['note']}{tags}")
        return notes

    def soft_associate(self, context_text):
        """Associative recall for soft knowledge — surfaces creative/nice-to-know matches."""
        notes = self.db.get("soft", {}).get("notes", []) if isinstance(self.db.get("soft"), dict) else self.db.get("soft", [])
        if not notes or not context_text:
            return []

        keywords = set(re.findall(r'[a-zA-Z0-9]+', context_text.lower()))
        hits = []
        for n in notes:
            note_words = set(re.findall(r'[a-zA-Z0-9]+', n["note"].lower()))
            tag_words = set(t.lower() for t in n.get("tags", []))
            overlap = keywords & (note_words | tag_words)
            if len(overlap) >= 2:
                hits.append((len(overlap), n))

        hits.sort(key=lambda x: -x[0])
        if hits:
            print(f"\n  {C.MAGENTA}💭 Soft recall — {len(hits)} ideas surfaced (non-critical):{C.RESET}")
            for score, n in hits[:5]:
                print(f"    {C.MAGENTA}~{C.RESET} {n['note']} {C.DIM}[rel:{score}]{C.RESET}")
        return [n for _, n in hits]

    # ═══════════════════════════════════════════════════════
    # PROMPT VAULT — Evaluation, Scoring, and Wall of Fame
    # ═══════════════════════════════════════════════════════

    def prompt_add(self, category, prompt_text, reason, score=None, name=None):
        """
        Add or evaluate a prompt. Auto-scores if score not given.
        Keeps top 2 per category. Bumps the weakest if full.

        Args:
            category: Task category (e.g., "recon", "web_security", "python_dev")
            prompt_text: The full prompt text
            reason: Why this prompt is good — what makes it effective
            score: Manual score 1-100 (auto-scored if omitted)
            name: Short name for the prompt (auto-generated if omitted)
        """
        if "prompts" not in self.db:
            self.db["prompts"] = {}

        category = category.lower().strip()
        if category not in self.db["prompts"]:
            self.db["prompts"][category] = []

        # Auto-score based on prompt quality signals
        if score is None:
            score = self._auto_score_prompt(prompt_text)

        # Auto-name if not provided
        if name is None:
            words = prompt_text.strip().split()[:6]
            name = " ".join(words) + "..."

        entry = {
            "name": name,
            "prompt": prompt_text,
            "reason": reason,
            "score": score,
            "category": category,
            "added": self._ts(),
            "times_used": 0,
            "last_used": None,
            "results_rating": [],  # Track how well it performed each use
        }

        prompts = self.db["prompts"][category]

        # Check if we already have 2 — bump the weakest if new one is better
        if len(prompts) >= 2:
            weakest = min(prompts, key=lambda p: p["score"])
            if score > weakest["score"]:
                old_name = weakest["name"]
                old_score = weakest["score"]
                prompts.remove(weakest)
                prompts.append(entry)
                print(f"  {C.GREEN}[↑]{C.RESET} Rotated in: {C.BOLD}{name}{C.RESET} (score: {score})")
                print(f"  {C.RED}[↓]{C.RESET} Rotated out: {C.DIM}{old_name}{C.RESET} (score: {old_score})")
                print(f"  {C.CYAN}    Reason:{C.RESET} {reason}")
            else:
                print(f"  {C.YELLOW}[=]{C.RESET} Not strong enough to replace existing prompts in [{category}]")
                print(f"  {C.DIM}    New: {score} vs Weakest: {weakest['score']}{C.RESET}")
                return
        else:
            prompts.append(entry)
            print(f"  {C.GREEN}[+]{C.RESET} Added prompt to [{category}]: {C.BOLD}{name}{C.RESET} (score: {score})")
            print(f"  {C.CYAN}    Reason:{C.RESET} {reason}")

        self._grant_xp(XP_PER_FACT, f"prompt added [{category}]")
        self.save()

    def prompt_use(self, category, index=0):
        """Mark a prompt as used and return it."""
        category = category.lower().strip()
        prompts = self.db.get("prompts", {}).get(category, [])
        if not prompts:
            warning(f"No prompts in category: {category}")
            return None
        if index >= len(prompts):
            warning(f"Only {len(prompts)} prompts in [{category}]")
            return None

        p = sorted(prompts, key=lambda x: -x["score"])[index]
        p["times_used"] += 1
        p["last_used"] = self._ts()
        self.save()
        return p["prompt"]

    def prompt_rate(self, category, index, rating):
        """
        Rate how well a prompt performed (1-10).
        Over time this adjusts the prompt's score.
        """
        category = category.lower().strip()
        prompts = self.db.get("prompts", {}).get(category, [])
        if not prompts or index >= len(prompts):
            warning("Prompt not found")
            return

        p = sorted(prompts, key=lambda x: -x["score"])[index]
        p["results_rating"].append({"rating": rating, "date": self._ts()})

        # Adjust score based on rolling average of results
        if len(p["results_rating"]) >= 3:
            avg = sum(r["rating"] for r in p["results_rating"][-5:]) / min(5, len(p["results_rating"]))
            p["score"] = int(p["score"] * 0.7 + avg * 10 * 0.3)  # Blend original + performance

        success(f"Rated [{category}] prompt '{p['name']}': {rating}/10 → adjusted score: {p['score']}")
        self.save()

    def prompt_wall(self):
        """
        🏆 WALL OF FAME — Top 5 prompts across all categories, side by side with reasoning.
        """
        all_prompts = self.db.get("prompts", {})
        if not all_prompts:
            warning("No prompts stored yet. Use brain.prompt_add() to build your collection.")
            return

        # Gather all prompts with their categories
        flat = []
        for cat, prompts in all_prompts.items():
            for p in prompts:
                flat.append((cat, p))

        # Sort by score descending
        flat.sort(key=lambda x: -x[1]["score"])
        top5 = flat[:5]

        # Build the wall
        w = 78
        print(f"\n{C.YELLOW}{C.BOLD}{'═' * w}")
        print(f"  🏆  PROMPT WALL OF FAME  🏆")
        print(f"{'═' * w}{C.RESET}")

        for rank, (cat, p) in enumerate(top5, 1):
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")
            used = p.get("times_used", 0)
            avg_rating = ""
            if p.get("results_rating"):
                avg = sum(r["rating"] for r in p["results_rating"]) / len(p["results_rating"])
                avg_rating = f" | Avg Rating: {avg:.1f}/10"

            # Side-by-side: prompt summary on left, reasoning on right
            print(f"\n  {C.YELLOW}{C.BOLD}{medal} #{rank}{C.RESET}  {C.CYAN}{C.BOLD}{p['name']}{C.RESET}")
            print(f"  {C.GRAY}{'─' * (w - 4)}{C.RESET}")

            # Two-column layout
            prompt_preview = p["prompt"][:200].replace('\n', ' ').strip()
            reason = p["reason"]

            print(f"  {C.WHITE}{C.BOLD}Category:{C.RESET}  {C.CYAN}{cat}{C.RESET}")
            print(f"  {C.WHITE}{C.BOLD}Score:{C.RESET}     {C.GREEN}{p['score']}/100{C.RESET}  │  {C.WHITE}{C.BOLD}Used:{C.RESET} {used}x{avg_rating}")
            print(f"  {C.WHITE}{C.BOLD}Prompt:{C.RESET}    {C.DIM}{prompt_preview}{'...' if len(p['prompt']) > 200 else ''}{C.RESET}")
            print(f"  {C.WHITE}{C.BOLD}Why #{rank}:{C.RESET}   {C.YELLOW}{reason}{C.RESET}")

        # Category summary at bottom
        print(f"\n  {C.GRAY}{'─' * (w - 4)}{C.RESET}")
        print(f"  {C.DIM}Categories: {len(all_prompts)} | Total Prompts: {sum(len(v) for v in all_prompts.values())} | Showing Top 5{C.RESET}")
        print(f"{C.YELLOW}{C.BOLD}{'═' * w}{C.RESET}\n")

    def prompt_list(self, category=None):
        """List all prompts, optionally filtered by category. Side-by-side with reasons."""
        all_prompts = self.db.get("prompts", {})
        if not all_prompts:
            warning("No prompts stored yet")
            return

        cats = [category.lower().strip()] if category else sorted(all_prompts.keys())

        for cat in cats:
            prompts = all_prompts.get(cat, [])
            if not prompts:
                continue

            prompts = sorted(prompts, key=lambda x: -x["score"])
            print(f"\n  {C.CYAN}{C.BOLD}┌─ {cat.upper()} ({len(prompts)}/2 slots) ─┐{C.RESET}")

            for i, p in enumerate(prompts):
                slot = f"{'A' if i == 0 else 'B'}"
                used = p.get("times_used", 0)
                bar_len = int(p["score"] / 100 * 20)
                bar = f"{'█' * bar_len}{'░' * (20 - bar_len)}"
                score_color = C.GREEN if p["score"] >= 80 else C.YELLOW if p["score"] >= 60 else C.RED

                print(f"  {C.GRAY}│{C.RESET}")
                print(f"  {C.GRAY}├─{C.RESET} {C.BOLD}[{slot}]{C.RESET} {C.WHITE}{p['name']}{C.RESET}")
                print(f"  {C.GRAY}│{C.RESET}   {score_color}{bar}{C.RESET} {p['score']}/100  │  Used: {used}x")
                preview = p["prompt"][:120].replace('\n', ' ')
                print(f"  {C.GRAY}│{C.RESET}   {C.DIM}Prompt: {preview}...{C.RESET}")
                print(f"  {C.GRAY}│{C.RESET}   {C.YELLOW}Why: {p['reason']}{C.RESET}")

            print(f"  {C.CYAN}{C.BOLD}└{'─' * 30}┘{C.RESET}")

    def _auto_score_prompt(self, prompt_text):
        """
        Score a prompt 1-100 based on quality signals.
        Higher scores for: specificity, structure, actionability, output format instructions.
        """
        score = 50  # Base score

        text = prompt_text.lower()
        length = len(text)

        # Length sweet spot: 200-1500 chars
        if 200 <= length <= 1500:
            score += 10
        elif length > 1500:
            score += 5  # Longer is OK but diminishing returns
        elif length < 100:
            score -= 10  # Too short to be useful

        # Structural signals
        if any(marker in text for marker in ['1)', '1.', 'step 1', 'phase 1', 'first,']):
            score += 8  # Has numbered steps
        if any(w in text for w in ['table', 'format', 'structure', 'output', 'present']):
            score += 5  # Specifies output format
        if any(w in text for w in ['verify', 'validate', 'confirm', 'check', 'test']):
            score += 5  # Has verification step
        if any(w in text for w in ['save', 'log', 'record', 'document']):
            score += 3  # Has persistence
        if any(w in text for w in ['if ', 'unless', 'when ', 'fallback']):
            score += 4  # Has conditional logic
        if any(w in text for w in ['color', 'banner', 'professional', 'clean']):
            score += 3  # Asks for good presentation
        if any(w in text for w in ['rank', 'priorit', 'severity', 'risk']):
            score += 4  # Asks for prioritization
        if any(w in text for w in ['suggest', 'recommend', 'next step']):
            score += 3  # Asks for forward thinking

        return min(100, max(1, score))

    def associate(self, context_text):
        """
        SUPERPOWER: Associative recall.
        Given a block of text (a task description, a question, an error message),
        automatically surface all relevant knowledge without being asked.
        Returns facts that keyword-match against the context.
        """
        if not context_text:
            return []

        # Tokenize context into meaningful keywords
        stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                      'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
                      'could', 'should', 'may', 'might', 'can', 'shall', 'to',
                      'of', 'in', 'for', 'on', 'with', 'at', 'by', 'from', 'as',
                      'into', 'through', 'during', 'before', 'after', 'above',
                      'below', 'between', 'out', 'off', 'over', 'under', 'again',
                      'further', 'then', 'once', 'here', 'there', 'when', 'where',
                      'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more',
                      'most', 'other', 'some', 'such', 'no', 'not', 'only', 'same',
                      'so', 'than', 'too', 'very', 'just', 'because', 'but', 'and',
                      'or', 'if', 'while', 'that', 'this', 'it', 'i', 'me', 'my',
                      'we', 'our', 'you', 'your', 'he', 'she', 'they', 'what',
                      'which', 'who', 'whom', 'use', 'using', 'run', 'make', 'get'}

        import re
        words = set(re.findall(r'[a-zA-Z0-9_./-]+', context_text.lower()))
        keywords = words - stop_words
        # Also match multi-word phrases by checking 2-grams
        text_lower = context_text.lower()

        hits = []
        seen = set()
        for topic, facts in self.db["facts"].items():
            # Topic name match
            topic_match = any(kw in topic or topic in kw for kw in keywords)

            for fact in facts:
                fact_lower = fact["fact"].lower()
                score = 0

                # Direct topic match
                if topic_match:
                    score += 3

                # Keyword overlap with fact text
                fact_words = set(re.findall(r'[a-zA-Z0-9_./-]+', fact_lower))
                overlap = keywords & fact_words
                score += len(overlap) * 2

                # Source match (if context mentions a tool name that's in the source)
                if any(kw in fact.get("source", "").lower() for kw in keywords):
                    score += 1

                # Confidence boost — higher confidence facts surface more easily
                score += fact["confidence"] / 100

                fact_id = f"{topic}:{fact['fact']}"
                if score >= 3 and fact_id not in seen:
                    hits.append((score, topic, fact))
                    seen.add(fact_id)

        # Sort by relevance score descending
        hits.sort(key=lambda x: -x[0])

        cap = self.max_recall or len(hits)
        if hits:
            showing = min(len(hits), cap)
            print(f"\n{C.MAGENTA}{C.BOLD}🧠 Brain Burst — {showing}/{len(hits)} relevant memories:{C.RESET}")
            for score, topic, fact in hits[:cap]:
                v = f"{C.GREEN}✓{C.RESET}" if fact["verified"] else f"{C.GRAY}?{C.RESET}"
                rel = f"{C.DIM}[rel:{score:.0f}]{C.RESET}"
                print(f"  {v} {C.CYAN}[{topic}]{C.RESET} {fact['fact']} {confidence_tag(fact['confidence'])} {rel}")
                fact["times_recalled"] += 1
            self.save()

        return [(t, f) for _, t, f in hits]

    def digest(self):
        """
        Full brain dump — organized by topic, sorted by confidence.
        The 'look at everything I know' view.
        """
        if not self.db["facts"]:
            warning("Brain is empty")
            return

        total = sum(len(v) for v in self.db["facts"].values())
        verified = sum(1 for v in self.db["facts"].values() for f in v if f["verified"])
        print(f"\n{C.CYAN}{C.BOLD}{'═' * 60}")
        print(f"  BRAIN DIGEST — {total} facts | {len(self.db['facts'])} topics | {verified} verified")
        print(f"{'═' * 60}{C.RESET}")

        for topic in sorted(self.db["facts"].keys()):
            facts = sorted(self.db["facts"][topic], key=lambda x: -x["confidence"])
            print(f"\n  {C.YELLOW}{C.BOLD}▸ {topic.upper()}{C.RESET} ({len(facts)} facts)")
            for f in facts:
                v = f"{C.GREEN}✓{C.RESET}" if f["verified"] else f"{C.GRAY}○{C.RESET}"
                print(f"    {v} {f['fact']} {confidence_tag(f['confidence'])}")
                print(f"      {C.DIM}src: {f['source']} | recalled: {f['times_recalled']}x{C.RESET}")

    # ═══════════════════════════════════════════════════════
    # SCOUT SYSTEM — background intel agents for passive knowledge
    # ═══════════════════════════════════════════════════════

    def scout_dispatch(self, topic, context, priority="normal"):
        """
        Queue a scout mission — background intel gathering on a topic.
        Scouts run passively alongside main work and bring back findings.

        Args:
            topic: What to research (e.g. "JWT token rotation best practices")
            context: Why it matters right now (e.g. "building auth system")
            priority: "low" | "normal" | "high" | "critical"

        Returns:
            Scout mission dict
        """
        scouts = self.db.setdefault("scouts", [])
        mission = {
            "id": len(scouts) + 1,
            "topic": topic,
            "context": context,
            "priority": priority,
            "dispatched": self._ts(),
            "status": "dispatched",  # dispatched → active → returned → absorbed
            "findings": [],
            "quality": None,  # set on return: "meh" | "solid" | "chef_kiss"
        }
        scouts.append(mission)
        self.save()

        icon = {"low": "📡", "normal": "🔭", "high": "🛰️", "critical": "🚨"}.get(priority, "🔭")
        info(f"{icon} Scout #{mission['id']} dispatched: {topic}")
        print(f"  {C.DIM}Context: {context}{C.RESET}")
        print(f"  {C.DIM}Priority: {priority}{C.RESET}")
        return mission

    def scout_return(self, scout_id, findings, quality="solid"):
        """
        Record a scout's return with findings.

        Args:
            scout_id: Scout mission ID
            findings: List of dicts: [{"fact": str, "topic": str, "confidence": int, "source": str}]
            quality: "meh" | "solid" | "chef_kiss"
        """
        scouts = self.db.get("scouts", [])
        mission = None
        for s in scouts:
            if s["id"] == scout_id:
                mission = s
                break

        if not mission:
            warning(f"Scout #{scout_id} not found")
            return

        mission["status"] = "returned"
        mission["returned"] = self._ts()
        mission["findings"] = findings
        mission["quality"] = quality

        # Display
        icons = {"meh": "😐", "solid": "👍", "chef_kiss": "👨‍🍳💋"}
        quality_colors = {"meh": C.GRAY, "solid": C.GREEN, "chef_kiss": C.MAGENTA}

        qc = quality_colors.get(quality, C.WHITE)
        qi = icons.get(quality, "?")

        header(f"SCOUT #{scout_id} RETURNED")
        print(f"  {qc}{C.BOLD}{qi} Quality: {quality.upper()}{C.RESET}")
        print(f"  {C.DIM}Topic: {mission['topic']}{C.RESET}")
        print(f"  {C.DIM}Findings: {len(findings)}{C.RESET}")

        for f in findings:
            print(f"  {C.CYAN}→{C.RESET} [{f.get('topic', '?')}] {f['fact'][:70]} {C.DIM}({f.get('confidence', 80)}%){C.RESET}")

        if quality == "chef_kiss":
            print(f"\n  {C.MAGENTA}{C.BOLD}✨ CHEF'S KISS — auto-absorbing into brain!{C.RESET}")

        self.save()

    def scout_absorb(self, scout_id, auto_learn=True):
        """
        Absorb a returned scout's findings into the brain.
        Chef's kiss findings get auto-absorbed with high confidence.
        Others require manual review.

        Args:
            scout_id: Scout mission ID
            auto_learn: If True, learns all findings. If False, just displays for review.
        """
        scouts = self.db.get("scouts", [])
        mission = None
        for s in scouts:
            if s["id"] == scout_id:
                mission = s
                break

        if not mission:
            warning(f"Scout #{scout_id} not found")
            return

        if mission["status"] not in ("returned",):
            warning(f"Scout #{scout_id} status is '{mission['status']}' — need 'returned' to absorb")
            return

        findings = mission.get("findings", [])
        quality = mission.get("quality", "solid")
        absorbed = 0

        # Confidence boost for quality
        conf_boost = {"meh": -10, "solid": 0, "chef_kiss": 5}.get(quality, 0)

        for f in findings:
            conf = min(100, max(50, f.get("confidence", 80) + conf_boost))
            topic = f.get("topic", "scout_intel")
            source = f.get("source", f"scout#{scout_id}")

            if auto_learn:
                self.learn(topic, f["fact"], confidence=conf, source=source, verified=quality == "chef_kiss")
                absorbed += 1
            else:
                print(f"  {C.YELLOW}[review]{C.RESET} [{topic}] {f['fact'][:60]} (conf={conf}%)")

        mission["status"] = "absorbed"
        mission["absorbed"] = self._ts()
        mission["absorbed_count"] = absorbed
        self.save()

        if absorbed > 0:
            success(f"Absorbed {absorbed} findings from Scout #{scout_id}")

    def scout_status(self):
        """Display all scout missions and their status."""
        scouts = self.db.get("scouts", [])
        if not scouts:
            info("No scouts dispatched yet. Use brain.scout_dispatch() to send one.")
            return

        header("SCOUT BOARD")
        status_icons = {
            "dispatched": f"{C.YELLOW}⏳",
            "active": f"{C.CYAN}🔍",
            "returned": f"{C.GREEN}📬",
            "absorbed": f"{C.DIM}✓",
        }
        quality_icons = {"meh": "😐", "solid": "👍", "chef_kiss": "👨‍🍳💋"}

        for s in scouts:
            si = status_icons.get(s["status"], "?")
            qi = quality_icons.get(s.get("quality", ""), "")
            findings_count = len(s.get("findings", []))

            print(f"  {si} #{s['id']:<3}{C.RESET} {C.WHITE}{s['topic'][:45]}{C.RESET}")
            print(f"       {C.DIM}status={s['status']} | priority={s['priority']} | findings={findings_count} {qi}{C.RESET}")

    def scout_pending(self):
        """Get scouts still waiting for results — for use by background agents."""
        return [
            s for s in self.db.get("scouts", [])
            if s["status"] in ("dispatched", "active")
        ]

    def _display_facts(self, topic, facts):
        """Pretty-print facts for a topic."""
        print(f"\n{C.CYAN}{C.BOLD}── Knowledge: {topic} ──{C.RESET}")
        for f in sorted(facts, key=lambda x: -x["confidence"]):
            v = f"{C.GREEN}✓{C.RESET}" if f["verified"] else f"{C.GRAY}?{C.RESET}"
            print(f"  {v} {f['fact']} {confidence_tag(f['confidence'])}")
            print(f"    {C.GRAY}src: {f['source']} | learned: {f['learned']}{C.RESET}")

    @staticmethod
    def _ts():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
