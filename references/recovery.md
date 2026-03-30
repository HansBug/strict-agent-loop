# Recovery

Use this guide when the executor agent is lost, the context grows too large, or the loop state drifts.

## Executor Lost

1. Run `scripts/compact_state.py` on the current state file.
2. Read `context_snapshot` plus the most recent history.
3. Spawn a replacement executor.
4. Send the recovery prompt from [prompt_templates.md](prompt_templates.md).
5. Record the new executor id in the state on the next verified update with `--agent-id <new_id> --recovery`.

## State Drift

State drift usually means the repo no longer matches the state ledger.

Resolve it by:

1. inspecting the real repo state
2. correcting `next_task` and `status`
3. appending a fresh verified entry that explains the correction

Do not delete the old history unless it is obviously corrupted.

## Context Too Long

If the controller or executor starts relying on stale memory:

1. compact the state
2. use the compact snapshot as the canonical summary
3. continue from the current iteration instead of replaying the full transcript

## When to Abort

Abort the loop if any of these is true:

- the repo is in an unrecoverable or unsafe state
- the requested stop condition is impossible or contradictory
- the user changes the goal enough that the old state is no longer relevant
