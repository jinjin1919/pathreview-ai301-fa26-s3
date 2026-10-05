"""Tests for orchestrator.py"""

import pytest

from agent.memory.session_store import SessionStore
from agent.orchestrator import Orchestrator
from agent.tools.base import BaseTool, ToolResult


class FakeRedis:
    """Dict-backed stand-in for redis.Redis, tracking delete() calls."""

    def __init__(self):
        self.store = {}
        self.delete_calls = []

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.store[key] = value

    def delete(self, key):
        self.delete_calls.append(key)
        self.store.pop(key, None)


class CountingTool(BaseTool):
    """Returns a fresh, uniquely-marked result every time it's actually executed."""

    def __init__(self, name):
        self.name = name
        self.description = "test double"
        self.call_count = 0

    def execute(self, input_data: dict) -> ToolResult:
        self.call_count += 1
        return ToolResult(success=True, data={"call_number": self.call_count})


PROFILE_A_DATA = {"readme_content": "Profile A's README says X"}
PROFILE_B_DATA = {"readme_content": "Profile B's README says something totally different"}


@pytest.mark.unit
class TestOrchestratorSessionIsolation:
    """Regression tests for issue #15: session state must not leak between profiles."""

    @pytest.fixture
    def readme_tool(self):
        return CountingTool("readme_scorer")

    @pytest.fixture
    def market_tool(self):
        return CountingTool("market_analyzer")

    @pytest.fixture
    def fake_redis(self):
        return FakeRedis()

    @pytest.fixture
    def orchestrator(self, readme_tool, market_tool, fake_redis):
        return Orchestrator(
            tools={"readme_scorer": readme_tool, "market_analyzer": market_tool},
            session_store=SessionStore(fake_redis),
        )

    def test_market_analyzer_reexecutes_per_profile(self, orchestrator, market_tool):
        """market_analyzer's hardcoded input must not cache-collide across profiles."""
        orchestrator.run("profile-A", PROFILE_A_DATA)
        orchestrator.run("profile-B", PROFILE_B_DATA)

        assert market_tool.call_count == 2

    def test_market_analyzer_results_differ_per_profile(self, orchestrator):
        """Profile B must not receive profile A's cached market_analyzer result."""
        result_a = orchestrator.run("profile-A", PROFILE_A_DATA)
        result_b = orchestrator.run("profile-B", PROFILE_B_DATA)

        assert (
            result_a["tool_results"]["market_analyzer"]
            != result_b["tool_results"]["market_analyzer"]
        )

    def test_readme_scorer_control_runs_per_profile(self, orchestrator, readme_tool):
        """Control: readme_scorer's genuinely different input should always re-execute."""
        orchestrator.run("profile-A", PROFILE_A_DATA)
        orchestrator.run("profile-B", PROFILE_B_DATA)

        assert readme_tool.call_count == 2

    def test_session_deleted_at_start_of_each_run(self, orchestrator, fake_redis):
        """SessionStore.delete() must run for each profile, clearing prior state."""
        orchestrator.run("profile-A", PROFILE_A_DATA)
        orchestrator.run("profile-B", PROFILE_B_DATA)

        assert fake_redis.delete_calls == ["session:profile-A", "session:profile-B"]
