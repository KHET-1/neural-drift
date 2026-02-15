"""Tests for neuraldrift.brain.Brain — core knowledge system."""

import pytest


class TestBrainInit:
    def test_brain_init(self, tmp_brain):
        """Brain() creates with empty state."""
        assert tmp_brain.db["facts"] == {}
        assert tmp_brain.db["meta"]["xp"] == 0
        assert tmp_brain.db["meta"]["level"] == 0
        assert tmp_brain.db["meta"]["entries"] == 0


class TestLearnRecall:
    def test_learn_and_recall(self, tmp_brain):
        """Learn a fact, recall it back."""
        tmp_brain.learn("python", "Lists are mutable", confidence=90, source="docs")
        results = tmp_brain.recall("python")
        assert len(results) == 1
        assert results[0]["fact"] == "Lists are mutable"
        assert results[0]["confidence"] == 90

    def test_learn_increments_xp(self, tmp_brain):
        """XP goes up after learning."""
        xp_before = tmp_brain.db["meta"]["xp"]
        tmp_brain.learn("test", "XP test fact", source="pytest")
        assert tmp_brain.db["meta"]["xp"] > xp_before

    def test_learn_duplicate_updates(self, tmp_brain):
        """Learning the same fact with higher confidence updates it."""
        tmp_brain.learn("python", "dicts are ordered", confidence=60)
        tmp_brain.learn("python", "dicts are ordered", confidence=95)
        results = tmp_brain.recall("python")
        assert len(results) == 1
        assert results[0]["confidence"] == 95


class TestSearch:
    def test_search_finds_keyword(self, tmp_brain):
        """Search finds facts by keyword."""
        tmp_brain.learn("network", "TCP uses three-way handshake", source="rfc")
        tmp_brain.learn("python", "asyncio uses event loop", source="docs")
        results = tmp_brain.search("handshake")
        assert len(results) >= 1
        assert any("handshake" in r[1]["fact"].lower() for r in results)

    def test_search_no_match(self, tmp_brain):
        """Search returns empty for no match."""
        tmp_brain.learn("test", "some fact")
        results = tmp_brain.search("nonexistent_xyz_keyword")
        assert results == []


class TestAssociate:
    def test_associate_finds_related(self, tmp_brain):
        """Associate finds related facts from context text."""
        tmp_brain.learn("python", "asyncio uses event loop for concurrency", source="docs")
        tmp_brain.learn("network", "TCP port 80 serves HTTP", source="rfc")
        results = tmp_brain.associate("How does the Python event loop work?")
        # Should find the asyncio fact (keyword overlap: python, event, loop)
        assert len(results) >= 1


class TestLevel:
    def test_level_reflects_xp(self, tmp_brain):
        """Level increases with sufficient XP."""
        assert tmp_brain.db["meta"]["level"] == 0
        # Learn enough cited facts to gain a level (100 XP = level 1)
        # Each cited fact = 10 base + 10 cite bonus = 20 XP, so 5 facts = 100 XP
        for i in range(5):
            tmp_brain.learn("test", f"fact {i}", source=f"source_{i}")
        assert tmp_brain.db["meta"]["level"] >= 1


class TestStats:
    def test_stats_runs(self, tmp_brain):
        """Stats prints without error."""
        tmp_brain.learn("test", "a fact")
        # stats() prints to stdout, just verify it doesn't crash
        tmp_brain.stats()


class TestMuse:
    def test_muse_and_musings(self, tmp_brain):
        """Soft notes round-trip."""
        tmp_brain.muse("Maybe try rust for the rewrite", tags=["idea", "rust"])
        notes = tmp_brain.musings()
        assert len(notes) >= 1
        assert "rust" in notes[0]["note"].lower()


class TestAgents:
    def test_agent_checkin_checkout(self, tmp_brain):
        """Agent lifecycle: checkin, checkout."""
        agent_id, name, _ = tmp_brain.agent_checkin(role="researcher", task="test task")
        assert agent_id.startswith("A-")
        assert isinstance(name, str) and len(name) > 0

        result = tmp_brain.agent_checkout(agent_id, status="done", result="completed")
        assert result is True

    def test_agent_roster_after_checkin(self, tmp_brain):
        """Roster returns data after checkin."""
        tmp_brain.agent_checkin(role="scout", task="recon")
        # roster() prints to stdout — just verify no crash
        tmp_brain.agent_roster(show_all=True)

    def test_agent_stats(self, tmp_brain):
        """Agent stats returns expected keys."""
        aid, _, _ = tmp_brain.agent_checkin(role="test", task="unit test")
        tmp_brain.agent_checkout(aid, status="done")
        stats = tmp_brain.agent_stats()
        assert isinstance(stats, dict)
        assert "total_spawned" in stats
        assert stats["total_spawned"] >= 1


class TestPersistence:
    def test_save_and_load(self, tmp_path, monkeypatch):
        """Persistence round-trip: save, create new Brain, verify data."""
        import neuraldrift.brain as brain_mod

        brain_dir = tmp_path / ".neuraldrift"
        brain_dir.mkdir()
        monkeypatch.setattr(brain_mod, "BRAIN_DIR", brain_dir)
        monkeypatch.setattr(brain_mod, "BRAIN_DB", brain_dir / "brain_db.json")

        from neuraldrift.brain import Brain

        b1 = Brain()
        b1.learn("persistence", "this survives restart", source="test")
        b1.save()

        b2 = Brain()
        results = b2.recall("persistence")
        assert len(results) == 1
        assert "survives" in results[0]["fact"]


class TestForget:
    def test_forget_removes_fact(self, tmp_brain):
        """Learn then forget removes fact."""
        tmp_brain.learn("temp", "delete me please", source="test")
        assert len(tmp_brain.recall("temp")) == 1
        result = tmp_brain.forget("temp", "delete me")
        assert result is True
        assert len(tmp_brain.recall("temp")) == 0

    def test_forget_nonexistent(self, tmp_brain):
        """Forget returns False for nonexistent fact."""
        result = tmp_brain.forget("nope", "doesn't exist")
        assert result is False
