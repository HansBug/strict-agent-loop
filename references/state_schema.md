# State Schema

The authoritative current state lives in `.codex-loop/tasks/<task-id>/state.json`.
This file is intentionally paired with append-only ledgers so the rolling history window can be compacted without losing the full trail.

The task manager index lives separately at `.codex-loop/registry.json`.
It is not the full state. It is a workspace-level lookup table for managed tasks.

## Top-Level Fields

- `schema_version`: integer schema version
- `skill_name`: always `strict-agent-loop`
- `created_at`: ISO-8601 UTC timestamp
- `updated_at`: ISO-8601 UTC timestamp
- `task`: task management metadata
- `goal`: overall goal
- `global_stop_condition`: condition required for successful termination
- `workspace_root`: absolute target workspace path
- `success_evidence`: evidence expected at success
- `blocker_definition`: what counts as a blocker
- `operating_mode`: `interactive` or `unattended`
- `status`: `running`, `completed`, `blocked`, or `failed`
- `limits`: hard safety limits
- `counters`: loop counters
- `agent`: executor metadata
- `logging`: durable artifact paths and counters
- `stop_checks`: machine-checkable stop rules
- `supervisor`: unattended supervisor metadata
- `blocker`: current blocker state
- `next_task`: planned next atomic task
- `context_snapshot`: compact summary used for recovery
- `archive_summary`: compacted digest of trimmed history
- `history`: recent verified history window

## `task`

- `id`: managed task id
- `root_dir`: task-local durable root
- `manager_dir`: workspace-level `.codex-loop` directory

## `limits`

- `max_iterations`
- `max_no_progress_rounds`
- `max_context_chars`

## `counters`

- `iteration`: total recorded verified iterations
- `no_progress_rounds`: consecutive rounds with no objective progress
- `recovery_count`: number of executor recoveries

## `agent`

- `executor_id`: controller-tracked executor id
- `spawned_from_current_context`: whether the initial executor inherited current context

## `logging`

- `event_log_path`
- `iteration_log_path`
- `status_history_path`
- `round_summary_dir`
- `status_text_path`
- `stop_report_path`
- `run_summary_path`
- `events_written`
- `iterations_persisted`
- `status_snapshots_written`
- `last_event_at`
- `last_iteration_at`
- `last_status_at`
- `last_round_summary_path`
- `last_stop_report_at`
- `last_run_summary_at`

## `stop_checks`

- `commands`
- `paths_exist`
- `text_patterns`

## `supervisor`

- `enabled`
- `codex_bin`
- `model`
- `sandbox`
- `thread_id`
- `resume_existing_thread`
- `max_rounds_per_invocation`
- `max_consecutive_failures`
- `invocation_count`
- `consecutive_failures`
- `last_invoked_at`
- `last_completed_at`
- `last_exit_code`
- `last_prompt_path`
- `last_output_path`
- `last_jsonl_path`
- `log_dir`

## `history[]`

Each entry in the rolling history window contains:

- `iteration`
- `timestamp`
- `task`
- `announcement`
- `local_done_condition`
- `result_summary`
- `verification_summary`
- `progress_made`
- `status`
- `stop_condition_met`
- `stop_reason`
- `needs_human_input`
- `evidence`
- `artifacts`
- `next_task`
- `elapsed_since_previous_seconds`
- `round_summary_path`

This is a recent working window, not the full archive.

## Full Append-Only Trail

The full trail lives outside `history`:

- task-local `events.jsonl`: control-plane events and announcements
- task-local `iterations.jsonl`: full verified round records
- task-local `status-history.jsonl`: progress broadcasts and heartbeats
- task-local `rounds/`: human-readable per-round summaries
- task-local `run-summary.md`: current whole-cycle summary

## Registry Entry

`registry.json` keeps one lightweight entry per managed task so operators can discover and resume tasks safely.

Each entry includes:

- `id`
- `state_path`
- `task_root_dir`
- `manager_dir`
- `goal`
- `operating_mode`
- `status`
- `workspace_root`
- `created_at`
- `updated_at`
- `iteration`
- `next_task`
- `last_event_at`
- `latest_status_path`
- `latest_stop_report_path`
- `run_summary_path`
- `needs_human_input`
- `blocker_reason`
