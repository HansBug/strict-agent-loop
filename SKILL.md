---
name: strict-agent-loop
description: Enforce strict iterative execution for interactive long tasks and unattended Codex-supervised runs, with one small verified task per round, explicit round announcements, append-only disk logs, recoverable state, progress broadcasts, and machine-checkable stop conditions. Use when Codex must not skip the middle, must inherit prior context across rounds, and should continue until an external stop rule or real blocker is reached.
---

# Strict Agent Loop

## Overview

Use this skill when the work is large, quality-sensitive, or easy for Codex to compress into a vague summary.
The current Codex session is always the controller for the task it is handling.
This skill supports two operating modes:

- `interactive`: the controller stays in front of the user and reports every round
- `unattended`: an outer supervisor repeatedly runs or resumes Codex while the inner controller keeps following the same strict loop protocol

Read [protocol.md](references/protocol.md) before starting.
Read [management.md](references/management.md) before choosing or creating a task id.
Read [modes.md](references/modes.md) when choosing a mode.
Read [stop_checks.md](references/stop_checks.md) when defining machine-checkable stop rules.
Read [recovery.md](references/recovery.md) when recovering from executor loss, supervisor loss, or context pressure.

## If Asked How To Use This Skill

When the user asks how to use this skill, answer concretely.

1. Explain that there are two modes:
   - `interactive`: the current Codex session remains user-facing
   - `unattended`: `scripts/supervise.py` owns the outer while-loop
2. If the user did not choose a mode, show both quick starts.
3. Always explain the managed layout:
   - `.codex-loop/registry.json`
   - `.codex-loop/tasks/<task-id>/state.json`
   - task-local `events.jsonl`, `iterations.jsonl`, `status-history.jsonl`, `latest-status.txt`, `latest-stop-report.json`, `run-summary.md`, `rounds/`, and unattended-only `supervisor/`
4. Always mention `list_tasks.py` and `show_task.py` when the repo may host multiple loops.
5. Always mention that unattended runs should rely on machine-checkable stop conditions, not only natural-language claims.
6. Give the user an exact prompt or shell command, not only prose.

## Managed Task Selection

Default to the managed layout under `<workspace_root>/.codex-loop/`.

- Before starting work, check whether `.codex-loop/registry.json` already exists.
- Each long-running objective should have one task id and one task root under `.codex-loop/tasks/<task-id>/`.
- If the user is starting new work and did not specify a task id, derive one from the goal by using `scripts/init_state.py`.
- If the user wants to resume and gives a task id, use that exact managed task.
- If the user wants to resume but did not name a task:
  - if exactly one plausible running task exists, use it
  - if several plausible tasks exist, show `scripts/list_tasks.py` output and ask which task to continue
- Do not ask the user to enumerate storage paths unless they explicitly want custom paths.

## Required Loop Contract

Before iteration 1, define all of these:

- `goal`
- `global_stop_condition`
- `workspace_root`
- `success_evidence`
- `blocker_definition`
- `operating_mode`
- `stop_checks`
- `hard_limits`
  - `max_iterations`
  - `max_no_progress_rounds`
  - optional context compaction threshold
- unattended only:
  - `max_rounds_per_invocation`
  - `max_consecutive_failures`

Do not start the loop while the goal or stop rule is materially unclear.

## Disk Is Authoritative

Do not rely on memory alone.
At minimum, keep these artifacts current and queryable:

- `.codex-loop/registry.json`
- `.codex-loop/tasks/<task-id>/state.json`
- `.codex-loop/tasks/<task-id>/events.jsonl`
- `.codex-loop/tasks/<task-id>/iterations.jsonl`
- `.codex-loop/tasks/<task-id>/status-history.jsonl`
- `.codex-loop/tasks/<task-id>/latest-status.txt`
- `.codex-loop/tasks/<task-id>/latest-stop-report.json`
- `.codex-loop/tasks/<task-id>/run-summary.md`
- `.codex-loop/tasks/<task-id>/rounds/iteration-XXXX.md`

If unattended mode is active, also keep:

- `.codex-loop/tasks/<task-id>/supervisor/`

The in-memory `history` window in `state.json` may be compacted.
The full append-only record still lives in `iterations.jsonl`, `events.jsonl`, `status-history.jsonl`, and `rounds/`.

## Interactive Mode

Interactive mode is for long tasks where a human is present and wants to see every round.

Rules:

- Keep the current Codex session as controller.
- Use one persistent executor subagent whenever possible.
- Before each round, tell the user:
  - iteration number
  - completed rounds so far
  - this round
  - local done condition
  - global stop condition
  - stop after this round if
  - recent average round time and estimated remaining time when available
- Write the same announcement to `events.jsonl` with `scripts/append_event.py`.
- After the round, verify, record it with `scripts/update_state.py`, re-check stop conditions with `scripts/check_stop.py`, then refresh `latest-status.txt`, `status-history.jsonl`, `latest-stop-report.json`, and `run-summary.md` with `scripts/report_status.py`.

## Unattended Mode

Unattended mode is for long-running work where the outer while-loop must survive beyond one Codex invocation.

Architecture:

- the outer loop lives in `scripts/supervise.py`
- the supervisor starts or resumes Codex with `codex exec` or `codex exec resume`
- the inner Codex session still uses this skill as controller
- disk artifacts bridge one invocation to the next

Rules:

- The supervisor owns outer repetition.
- The inner controller still owns task decomposition, verification, and executor management for its current invocation.
- Each unattended invocation must stop cleanly after:
  - the global stop condition is met
  - a real blocker is reached
  - the per-invocation round budget is consumed
- Because no human is present, round announcements must still be written to disk.
- The supervisor must refresh durable progress broadcasts so the run does not look dead.

## Broadcast Rules

Broadcasting is mandatory in both modes.

Interactive mode:

- tell the user directly
- write the round announcement to `events.jsonl`
- refresh `status-history.jsonl`, `latest-status.txt`, and `run-summary.md`

Unattended mode:

- write `round.started` announcements to `events.jsonl`
- refresh `status-history.jsonl`, `latest-status.txt`, `latest-stop-report.json`, and `run-summary.md`
- let the supervisor print heartbeat-style summaries that include:
  - completed iteration count
  - approximate progress bar
  - recent iteration times
  - recent average iteration time
  - estimated remaining time when possible

## One Atomic Task Per Round

Each round must stay objectively small.

Good atomic tasks:

- reproduce one failure
- compute one next hailstone number
- patch one isolated bug
- add one regression test
- update one document section
- run one validation command and interpret it

Bad atomic tasks:

- finish the whole feature
- fix all remaining issues
- implement, test, document, and polish everything

## Required Round Lifecycle

For every round:

1. Announce the round.
2. Log the announcement with `scripts/append_event.py`.
3. Do exactly one atomic task.
4. Verify the result with evidence.
5. Record the verified round with `scripts/update_state.py`.
6. Re-check machine stop conditions with `scripts/check_stop.py`.
7. Refresh durable progress outputs with `scripts/report_status.py`.
8. Compact state with `scripts/compact_state.py` when context pressure grows.

Never mark progress as complete without evidence.
Never skip verification because the executor probably did it right.

## Machine-Checkable Stop Conditions

Natural-language stop conditions are not enough for unattended runs.
Whenever possible, define machine checks such as:

- `--stop-command "pytest -q"`
- `--stop-command "ruff check ."`
- `--require-path docs/feature.md`
- `--require-text "README.md::hailstone sequence"`

If stop checks exist, treat them as the authority.
Do not claim success while stop checks still fail.

## Recovery

If the executor disappears or loses context:

1. compact the state
2. rebuild from `context_snapshot`, `run-summary.md`, recent `history`, `iterations.jsonl`, and `events.jsonl`
3. spawn a replacement executor
4. continue without restarting iteration numbering

If unattended mode loses its Codex thread:

1. keep the same state file and append-only logs
2. clear the stored thread id
3. let the supervisor start a fresh Codex invocation
4. recover from disk state, not from memory

## Fast Start

Interactive quick start:

1. Use `$strict-agent-loop`.
2. Tell Codex the goal, stop condition, and evidence.
3. Require durable round announcements and progress reporting.

Unattended quick start:

1. Initialize a managed task with `scripts/init_state.py --workspace-root <repo> --task-id <task-id> --operating-mode unattended`.
2. Define machine stop checks.
3. Start `scripts/supervise.py` against `.codex-loop/tasks/<task-id>/state.json`.
