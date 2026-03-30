---
name: strict-agent-loop
description: Enforce strict iterative execution with a persistent subagent, explicit per-step task announcements, disk-backed loop state, and repeated stop-condition checks. Use when Codex must avoid skipping work, must keep inheriting prior execution context across iterations, and should keep executing one small verified task at a time until a global stopping rule is satisfied or a hard blocker is reached.
---

# Strict Agent Loop

## Overview

Use this skill to turn a vague or easy-to-skimp task into a controlled loop.
Keep the control plane in the current agent, run the work plane through one persistent executor subagent, and treat the disk state as the source of truth.

## Required Workflow

1. Define the loop contract before doing any work.
2. Initialize or load the disk state.
3. Spawn or recover the executor subagent.
4. Execute exactly one atomic task per iteration.
5. Verify, persist, compact, and re-evaluate stop conditions after every iteration.
6. Stop only when the global stop condition is satisfied, a hard safety limit is hit, or a real blocker prevents further progress.

Read [protocol.md](references/protocol.md) before the first run.
Read [prompt_templates.md](references/prompt_templates.md) when composing executor prompts.
Read [state_schema.md](references/state_schema.md) when you need to inspect or repair the loop state.
Read [recovery.md](references/recovery.md) when the executor agent dies, the state drifts, or the context becomes too long.

## 1. Define the loop contract

Before spawning any subagent, explicitly define:

- `goal`
- `global_stop_condition`
- `workspace_root`
- `success_evidence`
- `blocker_definition`
- `hard_limits`
  - `max_iterations`
  - `max_no_progress_rounds`
  - optional context-compaction threshold

If the user did not provide a stop condition, infer one and say it before continuing.
Do not start the loop while the goal or stop condition is ambiguous.

## 2. Initialize or load disk state

Initialize `.codex-loop/state.json` inside the target workspace with `scripts/init_state.py`.
Never keep the only copy of progress in model memory.

Example:

```bash
python scripts/init_state.py \
  --state /abs/path/to/repo/.codex-loop/state.json \
  --goal "Refactor the package safely" \
  --global-stop-condition "Stop only when tests pass, lint passes, and the requested refactor is complete." \
  --workspace-root /abs/path/to/repo \
  --success-evidence "pytest passes" \
  --success-evidence "lint passes"
```

Reuse the existing state file if the loop already exists.
If the state file exists but is stale or inconsistent, repair it instead of discarding it blindly.

## 3. Spawn or recover the executor

Create exactly one executor subagent for the active loop.
On the first iteration, spawn it with `fork_context=true` so it inherits the current context.
Persist the returned executor id into the state file after creation.

If the executor dies or loses context:

- compact the state with `scripts/compact_state.py`
- spawn a replacement executor
- send the `context_snapshot`, recent verified history, and current loop contract
- continue the loop instead of restarting the entire task from scratch

Do not create a fresh executor on every iteration unless recovery is required.

## 4. Run one atomic task per iteration

Before dispatching work, tell the user exactly:

- the iteration number
- the one atomic task for this round
- the local done condition for this round
- the unchanged global stop condition
- the condition that will cause the loop to stop after this round

Then send the executor only the one atomic task plus the local done condition.
Do not silently broaden scope.
Do not combine diagnosis, implementation, verification, and documentation into one round unless the task is trivially small and still objectively atomic.

Good atomic tasks:

- reproduce one failing test
- patch one isolated bug
- add one regression test
- update one document section
- run one validation command and interpret the result

Bad atomic tasks:

- "finish the whole feature"
- "fix all remaining issues"
- "implement, test, document, and polish everything"

## 5. Verify and persist every round

After each executor round:

1. Inspect the changed artifacts yourself.
2. Validate the result with evidence such as tests, file diffs, logs, or command output.
3. Append the verified result with `scripts/update_state.py`.
4. Rebuild the compact snapshot with `scripts/compact_state.py` when history gets long or the executor needs recovery.
5. Re-evaluate whether the loop should stop with `scripts/check_stop.py`.

Never mark progress as complete without evidence.
Never skip the verification step because the executor "probably did it right".

## 6. Stop conditions

Stop successfully only when the global stop condition is satisfied.
Stop unsuccessfully only when at least one of these is true:

- a hard safety limit is reached
- a blocker prevents further progress
- the user interrupts or changes scope

If the loop stops unsuccessfully, say exactly why and record that reason in the state.

## Non-Negotiable Rules

- Keep the controller role in the current agent. Do not let the executor decide when the overall task is done.
- Keep the disk state authoritative. Use memory as a cache, not as the ledger.
- Keep the executor persistent across iterations whenever possible.
- Keep each iteration small enough that failure is obvious and recovery is cheap.
- Keep the user informed before each round.
- Keep the same global stop condition unless the user explicitly changes it.
- Do not claim success because "most of the work is done".

## Fast Start

1. Read [protocol.md](references/protocol.md).
2. Initialize `.codex-loop/state.json`.
3. Spawn one persistent executor with inherited context.
4. Loop through atomic tasks until `scripts/check_stop.py` says to stop.
