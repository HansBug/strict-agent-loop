# Recovery

Use this guide when the executor is lost, the Codex thread is gone, or the context grows too large.

## Recovering An Interactive Executor

1. Run `scripts/compact_state.py` on the current state file.
2. Read `context_snapshot` from `state.json`.
3. Read `run-summary.md` for the current whole-cycle view.
4. Read `iterations.jsonl`, `events.jsonl`, and recent files under `rounds/` if more detail is needed.
5. Spawn a replacement executor.
6. Use the recovery prompt from [prompt_templates.md](prompt_templates.md).
7. Persist the new executor id on the next verified update with `--agent-id <new_id> --recovery`.

Do not restart from iteration 1.

## Recovering An Unattended Run

If `codex exec resume` fails or the stored thread becomes unusable:

1. keep the same task root under `.codex-loop/tasks/<task-id>/`
2. clear the stored thread id
3. let the supervisor start a fresh invocation
4. recover from the task-local disk state and append-only logs

The important files are:

- `.codex-loop/registry.json`
- `state.json`
- `run-summary.md`
- `events.jsonl`
- `iterations.jsonl`
- `status-history.jsonl`
- `rounds/`
- `supervisor/`

## State Drift

State drift means the repo no longer matches the ledger.

Resolve it by:

1. inspecting the actual repo state
2. correcting `next_task` and `status`
3. appending a fresh verified round that explains the correction

Do not delete old history unless it is obviously corrupted.

## Context Pressure

If the controller starts relying on stale memory:

1. compact the state
2. use `run-summary.md` and `context_snapshot` as the canonical summary
3. recover details from append-only logs when needed

## When To Abort

Abort the loop if any of these is true:

- the repo is in an unsafe or unrecoverable state
- the requested stop condition is impossible or contradictory
- the user changed the goal enough that the old state is no longer relevant
