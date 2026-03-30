# AGENTS.md

This file is for future maintainers working inside this repository.
Treat it as the high-signal maintenance note for how the repo is supposed to evolve.

## Purpose

`strict-agent-loop` is a Codex skill plus a small stdlib-only runtime for enforcing strict iterative execution.
The repository has two jobs at the same time:

- define the skill behavior and user-facing guidance
- provide reliable helper scripts that make the loop durable and recoverable

If you change one side, review the other side too.

## Core Design

The design is intentionally split into three layers:

1. Controller protocol
   The current Codex session is the controller.
   It owns scope, verification, stop checks, and recovery decisions.
2. Durable runtime
   The scripts under `scripts/` persist loop state, append-only logs, status broadcasts, and unattended supervision metadata.
3. User guidance
   `SKILL.md`, `README.md`, `README_zh.md`, and `references/` must stay aligned with the actual runtime behavior.

The repository is not trying to build a generic scheduler.
It is trying to make Codex noticeably less likely to skip the middle of a long task.

## Stability Rules

These are effectively part of the public contract.
Do not change them casually.

- The default durable workspace layout lives under `<workspace_root>/.codex-loop/`.
- `state.json` is the current authoritative state.
- `events.jsonl`, `iterations.jsonl`, `status-history.jsonl`, `rounds/`, and `run-summary.md` are the durable trail.
- The runtime must remain stdlib-only.
- The helper scripts must stay compatible with Python `3.7` through `3.14`.
- The skill should prefer default conventions over asking the user to specify many storage paths.

If a change requires breaking one of these assumptions, update the docs and call it out explicitly in the commit.

## Default Storage Convention

Unless the user explicitly overrides it, assume:

- workspace root is the target repo root
- manager registry path is `<workspace_root>/.codex-loop/registry.json`
- each task gets its own root at `<workspace_root>/.codex-loop/tasks/<task-id>/`
- task state path is `<workspace_root>/.codex-loop/tasks/<task-id>/state.json`
- all task-local durable artifacts live under the same task root
- real work outputs stay in `<workspace_root>/...`, not inside the task root unless the task explicitly wants bookkeeping-style artifacts there

Future changes should preserve this default-first behavior.
Prompt examples should say "use the default managed `.codex-loop/` layout" instead of making users spell out every file path.

The management helpers are intentionally simple:

- `init_state.py` may derive the default task-local state path automatically
- mutation scripts still require `--state` so operators cannot accidentally update the wrong task
- `list_tasks.py` and `show_task.py` are the intended low-friction management entrypoints

## Recovery Model

Recovery is disk-first, not memory-first.

When something goes wrong, the intended recovery order is:

1. `registry.json` to find the right task
2. the task's `state.json`
3. the task's `run-summary.md`
4. the task's `iterations.jsonl`
5. the task's `events.jsonl`
6. the task's `status-history.jsonl`
7. the task's `rounds/`
8. unattended only: the task's `supervisor/`

For unattended mode, the default policy is now fresh Codex invocations with disk recovery.
Reusing the same Codex thread is opt-in.
Reasoning effort is separately configurable for unattended runs and may need to be lowered for provider availability.
If the supervisor receives `SIGINT` or `SIGTERM`, it should save state, append an interruption event, and exit `130`.

If you change the schema or artifact set, make sure this recovery order still makes sense and update `references/recovery.md`.

## Script Responsibilities

- `init_state.py`
  Initializes the state and writes the first status artifacts.
  It should stay easy to use, with sensible defaults.
- `update_state.py`
  Records one verified iteration.
  This is the most important script for correctness.
- `append_event.py`
  Records controller or supervisor events without mutating the semantic history.
- `check_stop.py`
  Evaluates stop conditions and writes the latest stop report.
- `report_status.py`
  Refreshes human-readable and machine-readable progress outputs.
- `compact_state.py`
  Shrinks the rolling in-memory history window without destroying the append-only trail.
- `json_get.py`
  Reads specific dotted paths from JSON state files for targeted recovery checks without dumping the whole file.
- `supervise.py`
  Owns unattended outer-loop execution and heartbeat-style broadcasting.
  It also relays inner Codex announcements and command lifecycle events to outer stdout.
- `list_tasks.py`
  Lists managed tasks from the workspace registry.
- `show_task.py`
  Resolves one managed task and prints its canonical paths and latest registry metadata.
- `state_tools.py`
  Shared schema, paths, rendering, and append-only helpers.
- `stop_tools.py`
  Machine-checkable stop evaluation.

If you add a new runtime behavior, decide clearly which script owns it.
Avoid smearing one responsibility across many files.

## Documentation Sync Rules

When changing runtime behavior, check all of these:

- `SKILL.md`
- `README.md`
- `README_zh.md`
- `references/protocol.md`
- `references/recovery.md`
- `references/state_schema.md`
- `references/stop_checks.md`
- `agents/openai.yaml`

If the change affects default usage, update the copy-paste install prompt in both READMEs.

## Validation Expectations

Before pushing, at minimum do all of these:

- `python -m py_compile scripts/*.py`
- `~/.pyenv/versions/3.7.6/bin/python -m py_compile scripts/*.py`
- run the lifecycle smoke flow or the GitHub Actions equivalent
- forward-test a real strict-loop task when the runtime semantics changed
- when unattended behavior changes, prove interruption, recovery, and progress broadcasting on a real supervisor run
- when interactive behavior changes, prove a real multi-round online session instead of only checking the state files

The canonical real-world test in this repo is a hailstone / Collatz sequence task where:

- each round appends exactly one new number
- the total round count is not obvious up front
- the final report must aggregate the full history from disk

That scenario is useful because it catches fake batching and weak finalization behavior.

## When Touching The Schema

If you change persistent fields or artifact semantics:

- update `references/state_schema.md`
- decide whether `schema_version` should change
- keep old fields readable when reasonable
- make sure append-only logs still remain queryable after compaction
- confirm `run-summary.md` still points to the right durable artifacts

## What Not To Do

- Do not add third-party Python dependencies for convenience.
- Do not turn user prompts into a requirement to enumerate storage paths.
- Do not make the unattended mode depend only on natural-language claims of success.
- Do not silently remove durable artifacts from the default layout.
- Do not let docs drift away from the actual runtime behavior.
