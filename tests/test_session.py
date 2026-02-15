"""Tests for neuraldrift.session.Session — plan management and crash recovery."""

import pytest


class TestPlanLifecycle:
    def test_plan_start_checkpoint_complete(self, tmp_session):
        """Full plan lifecycle: start, checkpoint, complete."""
        tmp_session.plan_start("Test Plan", ["step1", "step2"])
        plan = tmp_session.get_plan()
        assert plan is not None
        assert plan["name"] == "Test Plan"
        assert plan["completed"] is False

        tmp_session.checkpoint("step1", status="completed", data={"result": "ok"})
        assert plan["objectives"]["step1"]["status"] == "completed"

        tmp_session.checkpoint("step2", status="completed")
        tmp_session.plan_complete()
        assert tmp_session.get_plan()["completed"] is True


class TestResume:
    def test_resume_check_fresh(self, tmp_session):
        """Fresh session returns RESTART verdict."""
        result = tmp_session.resume_check(verbose=False)
        assert isinstance(result, dict)
        assert result["verdict"] in ("RESUME", "PARTIAL", "RESTART")
        # Fresh session with no checkpoints should be RESTART
        assert result["verdict"] == "RESTART"


class TestAgentSnapshot:
    def test_snapshot_and_done(self, tmp_session):
        """Snapshot agent state and mark done."""
        tmp_session.agent_snapshot("A-0001", "TestBot", "unit testing", status="active")
        assert "A-0001" in tmp_session.state["agents"]
        assert tmp_session.state["agents"]["A-0001"]["status"] == "active"

        tmp_session.agent_done("A-0001", result_summary="Tests passed")
        assert tmp_session.state["agents"]["A-0001"]["status"] == "completed"
        assert tmp_session.state["agents"]["A-0001"]["result"] == "Tests passed"


class TestIntegrity:
    def test_verify_integrity_fresh(self, tmp_session):
        """Integrity check on fresh session (no baseline)."""
        result = tmp_session.verify_integrity()
        assert isinstance(result, dict)
        # With no baseline snapshot, expect "no_baseline" or "missing"
        for key, val in result.items():
            assert val in ("ok", "changed", "missing", "no_baseline")
