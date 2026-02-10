
<div align="center">

<img src="assets/banner.svg" alt="NeuralDrift — Your knowledge has a temperature" width="600" />

```
 ███╗   ██╗███████╗██╗   ██╗██████╗  █████╗ ██╗
 ████╗  ██║██╔════╝██║   ██║██╔══██╗██╔══██╗██║
 ██╔██╗ ██║█████╗  ██║   ██║██████╔╝███████║██║
 ██║╚██╗██║██╔══╝  ██║   ██║██╔══██╗██╔══██║██║
 ██║ ╚████║███████╗╚██████╔╝██║  ██║██║  ██║███████╗
 ╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝

          ██████╗ ██████╗ ██╗███████╗████████╗
          ██╔══██╗██╔══██╗██║██╔════╝╚══██╔══╝
          ██║  ██║██████╔╝██║█████╗     ██║
          ██║  ██║██╔══██╗██║██╔══╝     ██║
          ██████╔╝██║  ██║██║██║        ██║
          ╚═════╝ ╚═╝  ╚═╝╚═╝╚═╝        ╚═╝
```

**Your knowledge has a temperature.**

*Freshly learned facts burn hot. Neglected ones drift cold.*

[![License: MIT](https://img.shields.io/badge/License-MIT-cyan.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-magenta.svg)](https://python.org)

</div>

---

## What Is NeuralDrift?

A dual-knowledge system with two brains that grow with you:

```
     AI BRAIN                         HUMAN BRAIN
  ╭──────────────╮                 ╭──────────────╮
  │ ◉ Facts      │                 │ ◎ Thoughts   │
  │ ◉ Agents     │      ⚡         │ ◎ Stories    │
  │ ◉ Scouts     │  ◇──◆──◇       │ ◎ Ideas      │
  │ ◉ Heat Maps  │      ⚡         │ ◎ Moods      │
  │ ◉ Council    │                 │ ◎ Journal    │
  │ ◉ Legends    │                 │ ◎ Connections│
  ╰──────┬───────╯                 ╰──────┬───────╯
         └────────────┤ YOU ├─────────────┘
```

**AI Brain** — Structured intelligence. Facts with confidence levels, XP leveling, agent swarms, scout intel, knowledge temperature tracking.

**Human Brain** — Your personal space. Thoughts, stories, ideas, moods, journal entries. No scores. No decay. No judgment.

### The Consent Rule

Nothing enters the Human Brain without explicit permission. The AI proposes, you approve or reject. Always.

---

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/KHET-1/neural-drift.git
cd neural-drift
bash setup.sh
```

### 2. Use It

```python
from neuraldrift.brain import Brain
from neuraldrift.human_brain import HumanBrain

# AI Brain — teach it things
brain = Brain()
brain.learn("python", "f-strings are faster than .format()",
            confidence=90, source="PEP 498")
brain.recall("python")
brain.level()

# Human Brain — your personal space
hb = HumanBrain()
hb.introduce("your_name")
hb.think("What if knowledge had a color?")
hb.idea("Build a thought visualizer", "Map connections between ideas")
```

### 3. See It

```bash
# Opening scroll (animated)
python3 -m neuraldrift.scroll

# Terminal dashboard
python3 neuraldrift/tools/brain_dashboard.py

# First-run walkthrough
python3 -m neuraldrift.welcome
```

---

## Features

### AI Brain

| Feature | Description |
|---------|-------------|
| **Knowledge Storage** | Facts with topic, confidence %, source, and timestamp |
| **XP & Leveling** | +10 XP per fact, +10 cited bonus, -30 uncited penalty. Level = XP / 100 |
| **Associative Recall** | `recall(topic)`, `search(keyword)`, `associate(text)` |
| **Heat Maps** | Knowledge temperature — hot (recent) vs cold (neglected) |
| **Agent Swarm** | Deploy named agents with personalities and traits |
| **Council of 6** | Top agents earn hooded titles (Architect, Oracle, Phantom...) |
| **Scouts** | Background intel gathering with quality tiers |
| **Legendary System** | Council members ascend through 10 legendary ranks |
| **Prompt Vault** | Store and rate your best prompts by category |
| **Soft Notes** | Quick musings without formal structure |

### Human Brain

| Feature | Description |
|---------|-------------|
| **Thoughts** | Fleeting ideas, shower thoughts, quick captures |
| **Stories** | Longer narratives, experiences, memories |
| **Ideas** | Actionable concepts, project seeds, what-ifs |
| **Moods** | Emotional state tracking (no judgment) |
| **Journal** | Dated diary entries |
| **Connections** | Links between thoughts ("this reminds me of...") |
| **Consent Flow** | AI proposes → staging area → you approve/reject |

---

## API Reference

### AI Brain

```python
from neuraldrift.brain import Brain
brain = Brain()

# Core
brain.learn(topic, fact, confidence, source, verified=False)
brain.recall(topic, limit=8)
brain.search(keyword, limit=8)
brain.associate(text)                # find related facts across all topics

# Tracking
brain.level()                        # show current level and XP
brain.stats()                        # full overview
brain.digest()                       # compact summary
brain.heatmap(show_facts=True)       # knowledge temperature
brain.cold_spots(threshold=15)       # find neglected topics
brain.warm_up(topic)                 # refresh a cold topic

# Soft Notes
brain.muse(note, tags=[])            # quick thought (5 XP)
brain.musings()                      # list soft notes
brain.soft_associate(text)           # find related musings

# Prompts
brain.prompt_add(category, text, reason)
brain.prompt_wall()                  # display all prompts
brain.prompt_rate(category, index, score)

# Agents
brain.agent_checkin(role, task)       # deploy an agent → (id, name)
brain.agent_checkout(id, status, result)
brain.agent_roster(show_all=True)
brain.agent_stats()

# Council & Hierarchy
brain.council()                      # show the Council of 6
brain.council_opine(topic)           # council weighs in

# Scouts
brain.scout_dispatch(topic, context, priority)
brain.scout_return(id, findings, quality)
brain.scout_absorb(id, auto_learn=True)
brain.scout_status()

# Legendary
brain.legendary_ascend(name)         # promote council member
brain.legendary_status(name=None)    # check legendary ranks
brain.agent_legends()                # list all legends
```

### Human Brain

```python
from neuraldrift.human_brain import HumanBrain
hb = HumanBrain()

# Direct writes
hb.introduce(name, motto=None)      # first-time setup
hb.think(thought, tags=[])          # quick capture
hb.idea(title, description)         # actionable concept
hb.story(title, content)            # longer narrative
hb.mood(feeling, context="")        # emotional state
hb.journal(entry)                   # diary entry
hb.connect(from_thought, to_thought, reason)

# Consent flow (AI proposes, human decides)
hb.propose(type, content, context="")
hb.pending()                        # review proposals
hb.approve(index)                   # accept
hb.reject(index)                    # decline
hb.approve_all()                    # accept everything

# Reflection
hb.reflect()                        # patterns in your mind
hb.session_prompt()                 # "anything on your mind?"
```

---

## The Agent Kingdom

As your AI Brain levels up, features unlock:

| Level | Title | Unlocks |
|-------|-------|---------|
| 0 | Blank Slate | Basic facts and recall |
| 1 | Awakened | XP tracking |
| 3 | Student | Search and associate |
| 5 | Apprentice | Named agents with personalities |
| 8 | Practitioner | Agent traits develop |
| 10 | Specialist | Forge system — agents collaborate |
| 15 | Expert | Scout intel gathering |
| 20 | Master | Council of 6 — hooded titles |
| 30 | Sage | Shinies and Dark Masks |
| 50 | Oracle | Heat maps, full kingdom |
| 75 | Transcendent | Legendary ascension |
| 100 | Omniscient | Everything. You made it. |

---

## Persistence & Recovery

Everything is crash-safe:

- **Atomic writes** — temp file + fsync + rename (never corrupts mid-write)
- **Rolling backups** — `.bak` file before every save
- **Corruption recovery** — auto-recovers from backup if main file is damaged
- **Session checkpoints** — tracks plan progress, agent state, dirty flags
- **Resume protocol** — on startup, determines RESUME vs PARTIAL vs RESTART

```python
from neuraldrift.startup import preflight
verdict = preflight()  # "RESUME" | "PARTIAL" | "RESTART"
```

---

## Philosophy

The AI Brain is precise, structured, and mechanical. It measures confidence, tracks XP, penalizes uncited claims, and runs agent armies.

The Human Brain is none of those things. It's messy, emotional, contradictory, and beautiful. A thought doesn't need a confidence score. A story doesn't expire. A mood isn't wrong just because it doesn't make sense.

Both brains persist. Both matter. Together they're more than either alone.

**Your knowledge has a temperature.** Freshly learned facts burn hot. Neglected ones drift cold. NeuralDrift tracks that drift — so nothing important ever goes completely dark.

---

## File Structure

```
neural-drift/
├── neuraldrift/              # Core package
│   ├── brain.py              # AI Brain (3400+ lines)
│   ├── human_brain.py        # Human Brain with consent model
│   ├── brain_constants.py    # Shared constants (levels, agents, XP)
│   ├── output.py             # Colored terminal output + CandyCane spinner
│   ├── banners.py            # Tool banners
│   ├── helpers.py            # Atomic JSON I/O, utilities
│   ├── session.py            # Crash recovery & checkpoints
│   ├── startup.py            # Preflight health checks
│   ├── scroll.py             # Animated opening sequence
│   ├── welcome.py            # First-run interactive walkthrough
│   └── tools/
│       └── brain_dashboard.py  # Terminal brain dashboard
├── setup.sh                  # One-command install
├── pyproject.toml            # Python packaging
├── LICENSE                   # MIT
└── README.md                 # You are here
```

---

## License

MIT. See [LICENSE](LICENSE).

---

<div align="center">

*Two brains. One system. Built for you.*

</div>
