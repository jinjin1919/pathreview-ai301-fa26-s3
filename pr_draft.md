# Agent session state is not cleared between reviews for the same user

## Summary
<!-- One paragraph describing what this PR does and why -->
this PR fix agent session state is not cleared between different profile_id. 

`Orchestrator.run()` now starts every review from a clean slate. It creates a fresh `ContextManager` and deletes the profile's existing Redis session before executing the plan, and it persists only the current run's results instead of merging them into previous state. Previously the orchestrator reused one in-memory cache across runs. Because `market_analyzer`'s input is hardcoded to `{"detected_skills": {}}`, its cache key was identical for every profile, so a second profile silently received the first profile's cached result. `SessionStore.delete()` was also never called, so old session state lingered and was merged into new results. This PR adds regression tests in `tests/unit/test_orchestrator`.py that fail without the fix.


## Issue
Closes #15

## Changes
<!-- Bullet list of the specific changes made -->
- From file: `agent/memory/context_manager.py` — added `ContextManager.clear()`: reset `self.results = {}`.
- From file: `agent/orchestrator.py` — In `run()`, right after the `orchestrator_start` log (line 42): call `self.context_manager.clear()` and `self.session_store.delete(profile_id)` (if a store is configured). This makes the old `get(profile_id)`/merge lines always return `{}`, so remove them and persist `results` directly via `session_store.set(profile_id, results)`.


## Testing
<!-- How did you verify your changes? -->
- [ ] **CI is green on this PR (all five jobs)** — required for review
- [ ] Unit tests pass (`make test-unit`)
- [ ] Integration tests pass (`make test-integration`)
- [ ] Linter passes (`make lint`)
- [ ] Type checker passes (`make typecheck`)
- [ ] New/updated tests cover the changes
- [ ] If this fixes a seeded bug: removed its `@pytest.mark.xfail` marker (and any
      matching suppression in `pyproject.toml`)

## Screenshots / Demo
<!-- If applicable, add screenshots or a link to a demo video -->

## Notes for Reviewers
<!-- Anything the reviewer should pay particular attention to -->

 