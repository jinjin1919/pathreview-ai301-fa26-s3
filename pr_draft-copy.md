# Agent session state is not cleared between reviews for the same user

## Summary
`Orchestrator.run()` now starts every review from a clean slate. At the start of each run it calls the new `ContextManager.clear()` on the orchestrator's existing manager (which logs `context_cleared`) and deletes the profile's existing Redis session before executing the plan. It then persists only the current run's results instead of merging them into previous state. Previously the orchestrator reused one in-memory cache across runs. Because `market_analyzer`'s input is hardcoded to `{"detected_skills": {}}`, its cache key was identical for every profile, so a second profile silently received the first profile's cached result. `SessionStore.delete()` was also never called, so old session state lingered and was merged into new results. This PR adds `tests/unit/test_orchestrator.py`; 4 of its 5 tests fail on `main` and all pass with the fix (see `test_evidence.md`).

## Issue
Closes #15

## Changes
- `agent/memory/context_manager.py`: added `ContextManager.clear()`, which resets `self.results` and emits a `context_cleared` log line.
- `agent/orchestrator.py`: in `run()`, right after the `orchestrator_start` log, call `self.context_manager.clear()` on the existing manager. Also call `self.session_store.delete(profile_id)` (when a store is configured) before executing the plan, drop the old `get(profile_id)`/merge logic, and persist `results` directly via `session_store.set(profile_id, results)`.
- `tests/unit/test_orchestrator.py`: new regression tests for cross-profile cache and session isolation, plus a test for `ContextManager.clear()`.

## Testing
<!-- How did you verify your changes? -->
- [x] **CI is green on this PR (all five jobs)** — required for review
- [v] Unit tests pass (`make test-unit`)
- [x] Integration tests pass (`make test-integration`)
- [v] Linter passes (`make lint`)
- [v] Type checker passes (`make typecheck`)
- [v] New/updated tests cover the changes
- [ ] If this fixes a seeded bug: removed its `@pytest.mark.xfail` marker (and any
      matching suppression in `pyproject.toml`)

## Screenshots / Demo
<!-- If applicable, add screenshots or a link to a demo video -->

N/A

## Notes for Reviewers
<!-- Anything the reviewer should pay particular attention to -->
I used AI to help me: 
- revise my harness for eval and live run. 
- fix error during project setup
- help me understand the process flow where is the entry point and general structure of the project. 
- help me understand the flow for my issue I am working on 
- help me list couple of approaches for resolving the issue
- help me to weight different approaches for resolving the issue
- help me draft test scripts
- help me do planing. 