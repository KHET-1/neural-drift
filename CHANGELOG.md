# Changelog

All notable changes to NeuralDrift will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-02-15

### Added
- **Dual-knowledge system**: Brain (XP, levels, decay) + HumanBrain (thoughts, ideas, stories)
- **Brain**: Learn/recall/search/associate with confidence tracking and citation bonuses
- **HumanBrain**: Consent-based staging, thought capture, idea lifecycle (seed to archived)
- **Agent system**: Checkin/checkout, personality evolution, swarm deployment, speed tiers
- **Session management**: Plan lifecycle, crash recovery (RESUME/PARTIAL/RESTART), integrity checks
- **Console TUI**: Full-screen Rich dashboard with brain stats, agent roster, event log, music player
- **Streaming server**: Unix domain socket server for real-time brain state streaming
- **Atomic persistence**: All JSON writes use tempfile + fsync + rename with rolling .bak backups
- **XP leveling**: 15 levels (Blank Slate to Omniscient), citation bonuses, uncited decay
- **Prompt vault**: Store, rate, and rotate top prompts per category
- **Scout system**: Background intel dispatch with quality tiers
- **pytest smoke test suite**: 25 tests covering Brain, HumanBrain, Session, and helpers
- MIT license
- pyproject.toml with rich dependency and dev extras

### Console TUI Polish
- Wider column ratios (3:2) with minimum sizes
- 10 agents and 10 topics visible by default
- 30 events visible in event panel
- Wider progress bars and seek bar
