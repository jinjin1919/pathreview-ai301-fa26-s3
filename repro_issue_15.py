import sys
sys.path.insert(0, "/Users/jinxu/pathreview-ai301-fa26-s3")

from agent.orchestrator import Orchestrator
from agent.memory.session_store import SessionStore
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


readme_tool = CountingTool("readme_scorer")
market_tool = CountingTool("market_analyzer")

fake_redis = FakeRedis()
orchestrator = Orchestrator(
    tools={"readme_scorer": readme_tool, "market_analyzer": market_tool},
    session_store=SessionStore(fake_redis),
)

result_a = orchestrator.run(
    "profile-A", {"readme_content": "Profile A's README says X"}
)
result_b = orchestrator.run(
    "profile-B", {"readme_content": "Profile B's README says something totally different"}
)

print("readme_scorer call_count:", readme_tool.call_count)
print("market_analyzer call_count:", market_tool.call_count)
print("profile A market_analyzer result:", result_a["tool_results"]["market_analyzer"])
print("profile B market_analyzer result:", result_b["tool_results"]["market_analyzer"])
print("profile A readme_scorer result:", result_a["tool_results"]["readme_scorer"])
print("profile B readme_scorer result:", result_b["tool_results"]["readme_scorer"])
print("redis DELETE calls across both runs:", fake_redis.delete_calls)

assert readme_tool.call_count == 2, "control: different readme input per profile, should run twice"
assert market_tool.call_count == 1, "BUG: market_analyzer's identical hardcoded input should be a cache miss per profile, but only ran once total"
assert result_a["tool_results"]["market_analyzer"] == result_b["tool_results"]["market_analyzer"]
assert fake_redis.delete_calls == [], "BUG: SessionStore.delete() is never invoked by run()"
print("\nReproduced: profile B silently received profile A's cached market_analyzer result, and no session state was ever deleted.")
