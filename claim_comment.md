Reproduced on `issue#15`: instantiated one `Orchestrator` and called
`.run()` for two different profiles with tool doubles that count their own invocations.
`market_analyzer`'s result for profile B came back byte-for-byte identical to profile
A's, and the double's `call_count` stayed at `1` across both runs — the structlog output
even names it directly (`tool_result_cache_hit` / `tool_cache_hit` for `market_analyzer`
on profile B's run). Root cause: `market_analyzer`'s input is hardcoded to
`{"detected_skills": {}}` (agent/orchestrator.py:127), and `Orchestrator.__init__`
creates one `ContextManager` (agent/orchestrator.py:30) whose cache key
(`agent/memory/context_manager.py:26`) never includes `profile_id`, so any tool call with
matching input collides across profiles for the lifetime of the orchestrator instance. I
also confirmed `SessionStore.delete()` (agent/memory/session_store.py:68) exists and
works but is never called from `run()`, so a profile's prior session state is never
cleared at the start of a new run.


Next: scope `ContextManager`'s cache per profile (or reset it at the start of `run()`),
and add the missing `session_store.delete(profile_id)` call before a run's plan
executes.
