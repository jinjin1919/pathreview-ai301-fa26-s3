# Repro report — issue #15: Agent session state is not cleared between reviews for the same user

## Environment

- Commit: `2f4e82f52efbcfcc57d65b3fa5348672163ca088` on `main` (`git rev-parse HEAD`)
- Python: 3.12.8 (project requires `>=3.11`)
- Dependencies: `redis==8.1.0`, `structlog==26.1.0` (`pip freeze` in the repro venv)
- OS: macOS (Darwin 23.6.0)

## Steps

Starting from forking the pathreview repo. and clone the forked repo to my local.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
make setup
pip install -q redis structlog
```

Save as `repro_issue_15.py` (repo root's parent dir on `sys.path` so `agent.*` imports
resolve without an editable install):

```python
import sys
sys.path.insert(0, "/path/to/pathreview-ai301-fa26-s3")

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
```

Run it:

```bash
python3.12 repro_issue_15.py
```

`readme_scorer` is the control: each profile gets genuinely different `readme_content`,
so its cache key differs and it correctly runs twice. `market_analyzer`'s input is
hardcoded to `{"detected_skills": {}}` regardless of profile
([agent/orchestrator.py:127](agent/orchestrator.py#L127)), so it deterministically
collides across profiles without needing to contrive matching inputs by hand.

## Expected

Calling `Orchestrator.run()` for a second, different profile should never return a
result computed for a different profile. `market_analyzer` should reflect a fresh
execution for profile B (`call_count == 2`, distinct data per profile), and profile B's
session state should start clean rather than inheriting profile A's stored keys.

## Actual

- `market_analyzer` `call_count` stayed at `1` after both runs — it only actually
  executed once, during profile A's run.
- Profile B's `tool_results["market_analyzer"]` is byte-for-byte identical to profile
  A's (`{'call_number': 1}` for both), even though profile B is a different profile
  with different data.
- structlog's own output names the cache hit directly on profile B's run:
  `tool_result_cache_hit key=market_analyzer:... tool=market_analyzer` /
  `tool_cache_hit tool=market_analyzer`.
- `fake_redis.delete_calls` is `[]` after both runs — `SessionStore.delete()` is never
  invoked by `run()`, despite being fully implemented
  ([agent/memory/session_store.py:68-81](agent/memory/session_store.py#L68-L81)).
- All three `assert` statements in the script pass, i.e. the script completes and prints
  the final "Reproduced:" line rather than raising `AssertionError`.

## Artifact (full captured stdout)

```
(.venv) ~@Jins-MBP pathreview-ai301-fa26-s3 % pip install -q redis structlog
(.venv) ~@Jins-MBP pathreview-ai301-fa26-s3 % python3.12 repro_issue_15.py  
2026-09-27 20:24:46 [info     ] orchestrator_start             profile_id=profile-A
2026-09-27 20:24:46 [info     ] plan_built                     plan_size=2
2026-09-27 20:24:46 [info     ] session_not_found              session_id=profile-A
2026-09-27 20:24:46 [info     ] tool_result_cache_miss         key=readme_scorer:23d92bf1d91da35e00cc3595a78bc3c647a1fa962589737008469dd3a0dd611d tool=readme_scorer
2026-09-27 20:24:46 [info     ] tool_result_stored             key=readme_scorer:23d92bf1d91da35e00cc3595a78bc3c647a1fa962589737008469dd3a0dd611d tool=readme_scorer
2026-09-27 20:24:46 [info     ] tool_executed                  success=True tool=readme_scorer
2026-09-27 20:24:46 [info     ] tool_result_cache_miss         key=market_analyzer:95e4a8f9276c0150ec6978a4ef9d9a2cac4d341eeaa23a74725f91d9eea97930 tool=market_analyzer
2026-09-27 20:24:46 [info     ] tool_result_stored             key=market_analyzer:95e4a8f9276c0150ec6978a4ef9d9a2cac4d341eeaa23a74725f91d9eea97930 tool=market_analyzer
2026-09-27 20:24:46 [info     ] tool_executed                  success=True tool=market_analyzer
2026-09-27 20:24:46 [info     ] session_stored                 session_id=profile-A ttl_seconds=3600
2026-09-27 20:24:46 [info     ] orchestrator_complete          profile_id=profile-A tools_executed=2
2026-09-27 20:24:46 [info     ] orchestrator_start             profile_id=profile-B
2026-09-27 20:24:46 [info     ] plan_built                     plan_size=2
2026-09-27 20:24:46 [info     ] session_not_found              session_id=profile-B
2026-09-27 20:24:46 [info     ] tool_result_cache_miss         key=readme_scorer:d3e05b1e701b424dfc6262693fe91f534632ed2bf752d2bc70c7530abc7561a3 tool=readme_scorer
2026-09-27 20:24:46 [info     ] tool_result_stored             key=readme_scorer:d3e05b1e701b424dfc6262693fe91f534632ed2bf752d2bc70c7530abc7561a3 tool=readme_scorer
2026-09-27 20:24:46 [info     ] tool_executed                  success=True tool=readme_scorer
2026-09-27 20:24:46 [info     ] tool_result_cache_hit          key=market_analyzer:95e4a8f9276c0150ec6978a4ef9d9a2cac4d341eeaa23a74725f91d9eea97930 tool=market_analyzer
2026-09-27 20:24:46 [info     ] tool_cache_hit                 tool=market_analyzer
2026-09-27 20:24:46 [info     ] tool_executed                  success=True tool=market_analyzer
2026-09-27 20:24:46 [info     ] session_stored                 session_id=profile-B ttl_seconds=3600
2026-09-27 20:24:46 [info     ] orchestrator_complete          profile_id=profile-B tools_executed=2
readme_scorer call_count: 2
market_analyzer call_count: 1
profile A market_analyzer result: {'call_number': 1}
profile B market_analyzer result: {'call_number': 1}
profile A readme_scorer result: {'call_number': 1}
profile B readme_scorer result: {'call_number': 2}
redis DELETE calls across both runs: []

Reproduced: profile B silently received profile A's cached market_analyzer result, and no session state was ever deleted.
```

## Behavior matches the issue's target

The issue claims: "Orchestrator keeps one ContextManager and never empties it, so one
orchestrator handling two reviews returns the first run's result for every tool whose
input hasn't changed. Empty that cache and delete the profile's saved session state
when run starts."

This reproduction shows exactly that, and only that:

- One `Orchestrator` instance, two `run()` calls for two different profiles — matches
  "one orchestrator handling two reviews".
- `market_analyzer`'s stable, per-run-identical input reproduces "the first run's
  result for every tool whose input hasn't changed" precisely, while `readme_scorer`
  (whose input legitimately differs per profile) is a control showing normal,
  non-buggy behavior side by side — ruling out an adjacent/different bug (e.g. "nothing
  ever re-executes").
- `fake_redis.delete_calls == []` reproduces the second half of the issue: the profile's
  saved session state is never deleted when `run()` starts.

