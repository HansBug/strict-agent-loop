# Protocol

Use this protocol when the task is large enough, ambiguous enough, or quality-sensitive enough that Codex might otherwise compress the middle.

## Controller Model

- The current Codex session is always the controller.
- Keep one persistent executor subagent when possible.
- The controller owns scope, verification, stop checks, recovery, and disk state.
- The executor owns only one atomic task at a time.

## Required Contract Before Iteration 1

Define all of these before starting:

- `goal`
- `global_stop_condition`
- `workspace_root`
- `success_evidence`
- `blocker_definition`
- `operating_mode`
- `max_iterations`
- `max_no_progress_rounds`

If unattended mode is used, also define:

- `max_rounds_per_invocation`
- `max_consecutive_failures`
- machine-checkable stop rules

Do not continue if any of those are materially unclear.

## Disk-Backed Sources Of Truth

The loop should be recoverable from disk.
At minimum, maintain:

- `.codex-loop/registry.json`
- `.codex-loop/tasks/<task-id>/state.json`
- `.codex-loop/tasks/<task-id>/events.jsonl`
- `.codex-loop/tasks/<task-id>/iterations.jsonl`
- `.codex-loop/tasks/<task-id>/status-history.jsonl`
- `.codex-loop/tasks/<task-id>/latest-status.txt`
- `.codex-loop/tasks/<task-id>/latest-stop-report.json`
- `.codex-loop/tasks/<task-id>/run-summary.md`
- `.codex-loop/tasks/<task-id>/rounds/iteration-XXXX.md`

Treat the task-local `state.json` as the current working state and the JSONL/Markdown artifacts as the full durable trail.
Treat `registry.json` as the manager index that tells you which task roots exist.
Treat `<workspace_root>/...` as the place for real deliverables and `.codex-loop/tasks/<task-id>/...` as the bookkeeping area.

## Atomicity Rules

A task is atomic only if all of these are true:

- it has one clear output
- it can be verified with one short check
- failure is easy to localize
- recovery does not require replaying the whole loop

If a proposed round sounds like a milestone, it is too large.

## Required Announcement Before Each Round

Before dispatching each round, announce:

- `Iteration N`
- `Completed so far`
- `This round`
- `Local done condition`
- `Global stop condition`
- `Stop after this round if`
- recent average round time and ETA when available

Interactive mode should say this to the user and log it to `events.jsonl`.
Unattended mode should log it to `events.jsonl` and keep the outer supervisor stdout visibly informative.
The authoritative completed-round count is `state.counters.iteration`.

## Required Controller Actions After Each Round

1. Inspect the changed files or command output yourself.
2. Verify the result with evidence.
3. Record the round with `update_state.py`.
4. Re-check stop conditions with `check_stop.py`.
5. Refresh status outputs with `report_status.py`.
6. Compact state if context pressure is growing.

Do not skip verification.
Do not rely on the executor's word alone.
After the first recovery read, do not keep re-reading full state and task documents every round unless disk state is actually unclear.
Run these commands strictly sequentially. Do not start the next command until the previous one has completed, and never overlap `update_state.py`, `check_stop.py`, or `report_status.py`.

## Stop Rules

Stop immediately if any of these is true:

- the machine-checkable stop rules pass
- the loop status becomes `blocked`
- the loop status becomes `failed`
- `max_iterations` is reached
- `max_no_progress_rounds` is reached

If machine-checkable stop rules exist, they are the authority.

## Compaction

The in-memory `history` window may be compacted.
That does not mean information was lost.
The full per-round and per-status history should still be recoverable from:

- `iterations.jsonl`
- `events.jsonl`
- `status-history.jsonl`
- `rounds/`
- `run-summary.md`
