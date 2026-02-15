"""Tests for neuraldrift.human_brain.HumanBrain — personal knowledge side."""

import pytest


class TestHumanBrainInit:
    def test_init(self, tmp_human):
        """Creates empty human brain with expected structure."""
        assert tmp_human.db["meta"]["owner"] is None
        assert tmp_human.db.get("thoughts", []) == []
        assert tmp_human.db.get("ideas", []) == []


class TestIdentity:
    def test_introduce_and_whoami(self, tmp_human):
        """Set identity and retrieve it."""
        tmp_human.introduce("TestUser", motto="Knowledge is power")
        assert tmp_human.db["meta"]["owner"] == "TestUser"
        assert tmp_human.db["meta"]["motto"] == "Knowledge is power"
        # whoami prints to stdout — verify no crash
        tmp_human.whoami()


class TestThoughts:
    def test_think_and_thoughts(self, tmp_human):
        """Add thought, retrieve it."""
        tmp_human.think("What if we used Rust instead?", tags=["dev", "idea"])
        all_thoughts = tmp_human.db.get("thoughts", [])
        assert len(all_thoughts) == 1
        assert "Rust" in all_thoughts[0]["thought"]
        assert "dev" in all_thoughts[0].get("tags", [])

    def test_multiple_thoughts(self, tmp_human):
        """Multiple thoughts accumulate."""
        tmp_human.think("First thought")
        tmp_human.think("Second thought")
        tmp_human.think("Third thought")
        assert len(tmp_human.db.get("thoughts", [])) == 3


class TestIdeas:
    def test_idea_lifecycle(self, tmp_human):
        """Add idea, grow it through stages."""
        tmp_human.idea("Build a CLI tool", description="Argparse based", priority="high")
        ideas = tmp_human.db.get("ideas", [])
        assert len(ideas) == 1
        assert ideas[0]["status"] == "seed"

        result = tmp_human.grow_idea("CLI tool", "growing")
        assert result is True
        assert tmp_human.db["ideas"][0]["status"] == "growing"


class TestConsent:
    def test_propose_approve_reject(self, tmp_human):
        """Consent flow: propose, approve one, reject one."""
        tmp_human.propose("thought", "AI noticed you like Python", context="coding patterns")
        tmp_human.propose("idea", "Try async refactor", context="performance review")

        pending = [p for p in tmp_human.db.get("pending", []) if p["status"] == "pending"]
        assert len(pending) == 2

        tmp_human.approve(0)
        pending = [p for p in tmp_human.db.get("pending", []) if p["status"] == "pending"]
        assert len(pending) == 1

        tmp_human.reject(0)
        pending = [p for p in tmp_human.db.get("pending", []) if p["status"] == "pending"]
        assert len(pending) == 0
