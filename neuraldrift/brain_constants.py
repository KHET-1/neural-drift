"""
brain_constants.py — Shared constants used by brain.py and its mixins.
Extracted to prevent circular imports when brain.py is split into modules.
"""

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

# Speed directives — injected into agent prompts
_SPEED_DIRECTIVES = """<speed>
- Respond directly. No preamble, no sign-off, no filler.
- Short sentences. One idea per line. Omit qualifiers.
- Structured output: bullets, key:value, or code. No prose walls.
- No hedging ("I think", "perhaps"). State facts or confidence %.
- Single-pass: pick approach, commit, execute. No second-guessing.
- Skip reasoning for simple tasks. Reserve CoT for multi-step logic only.
- If answer is a single value, return only that value.
</speed>"""

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
    0: "Blank Slate", 1: "Awakened", 2: "Observer", 3: "Student",
    5: "Apprentice", 8: "Practitioner", 10: "Specialist", 15: "Expert",
    20: "Master", 30: "Sage", 50: "Oracle", 75: "Transcendent", 100: "Omniscient",
}

# Council constants
COUNCIL_HOODS = [
    "The Architect", "The Oracle", "The Phantom",
    "The Warden", "The Forgekeeper", "The Harbinger",
]
SHINY_TITLES = [
    "Prism", "Luminary", "Beacon", "Spark", "Glimmer",
    "Aurora", "Radiant", "Shimmer", "Gleam", "Flare",
]
DARK_MASK_NAMES = [
    "Void", "Hollow", "Shade", "Wraith", "Eclipse",
    "Null", "Abyss", "Dusk", "Gloom", "Umbra",
]

# Legendary levels
LEGENDARY_LEVELS = [
    (100, "Crowned", "♚"), (250, "Exalted", "♛"), (500, "Immortal", "⚝"),
    (1000, "Ascendant", "☀"), (2000, "Sovereign", "⚜"), (4000, "Transcendent", "✦"),
    (8000, "Mythborne", "◆"), (16000, "Infinite", "∞"), (32000, "Primordial", "☬"),
    (64000, "Eternal", "ᛟ"),
]

EXP_RATES = {
    "coal_to_diamond": 20, "validation": 15, "council_opinion": 10,
    "shared_discovery": 8, "dark_mask_counter": 5, "mission_complete": 3,
}
