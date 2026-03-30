# State Schema

The authoritative loop ledger lives in `.codex-loop/state.json`.

## Top-Level Fields

- `schema_version`: Integer schema version.
- `skill_name`: Always `strict-agent-loop`.
- `created_at`: ISO-8601 UTC timestamp.
- `updated_at`: ISO-8601 UTC timestamp.
- `goal`: Overall goal.
- `global_stop_condition`: Condition required for successful termination.
- `workspace_root`: Absolute target workspace path.
- `success_evidence`: Array of evidence items expected at success.
- `blocker_definition`: What counts as a blocker.
- `status`: `running`, `completed`, `blocked`, or `failed`.
- `limits`: Hard safety limits.
- `counters`: Loop counters.
- `agent`: Executor metadata.
- `next_task`: Proposed next atomic task.
- `context_snapshot`: Compact summary used for recovery.
- `archive_summary`: Compacted digest of trimmed history.
- `history`: Verified iteration ledger.

## `limits`

- `max_iterations`
- `max_no_progress_rounds`
- `max_context_chars`

## `counters`

- `iteration`: Total recorded iterations.
- `no_progress_rounds`: Consecutive rounds with no objective progress.
- `recovery_count`: Number of executor recoveries.

## `agent`

- `executor_id`: Controller-tracked executor id.
- `spawned_from_current_context`: Whether the first executor was created with inherited context.

## `history[]`

Each history entry contains:

- `iteration`
- `timestamp`
- `task`
- `local_done_condition`
- `result_summary`
- `verification_summary`
- `progress_made`
- `status`
- `stop_condition_met`
- `evidence`
- `artifacts`
- `next_task`

Treat each history entry as verified fact, not as speculation.
