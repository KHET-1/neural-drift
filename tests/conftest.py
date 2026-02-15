"""Shared fixtures for NeuralDrift test suite."""

import pytest
from pathlib import Path


@pytest.fixture
def tmp_brain(tmp_path, monkeypatch):
    """Provide a Brain instance isolated to tmp_path."""
    import neuraldrift.brain as brain_mod

    brain_dir = tmp_path / ".neuraldrift"
    brain_dir.mkdir()
    monkeypatch.setattr(brain_mod, "BRAIN_DIR", brain_dir)
    monkeypatch.setattr(brain_mod, "BRAIN_DB", brain_dir / "brain_db.json")

    from neuraldrift.brain import Brain
    return Brain(max_recall=8)


@pytest.fixture
def tmp_human(tmp_path, monkeypatch):
    """Provide a HumanBrain instance isolated to tmp_path."""
    import neuraldrift.human_brain as hb_mod

    human_dir = tmp_path / ".neuraldrift"
    human_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(hb_mod, "HUMAN_DIR", human_dir)
    monkeypatch.setattr(hb_mod, "HUMAN_DB", human_dir / "human_brain.json")

    from neuraldrift.human_brain import HumanBrain
    return HumanBrain()


@pytest.fixture
def tmp_session(tmp_path, monkeypatch):
    """Provide a Session instance isolated to tmp_path."""
    import neuraldrift.session as sess_mod

    sess_dir = tmp_path / ".neuraldrift"
    sess_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(sess_mod, "SESSION_DIR", sess_dir)
    monkeypatch.setattr(sess_mod, "SESSION_FILE", sess_dir / "session_state.json")
    monkeypatch.setattr(sess_mod, "BRAIN_DB", sess_dir / "brain_db.json")

    from neuraldrift.session import Session
    return Session()
