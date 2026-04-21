# strict-agent-loop

English | [简体中文](./README_zh.md)

> ⚠️ **DEPRECATED — no longer maintained.**
>
> This skill has been abandoned. Do not install it. The documentation below the
> divider is kept only for historical reference. New skills that explicitly
> replace this workflow are not planned.

## What To Do Instead

The strict-atomic-round + durable-state pattern this skill implemented is no
longer worth running as a separate skill. Both CLIs now have native features
that cover the realistic use cases. Pick the path that matches your CLI.

### If you installed this on Codex CLI

1. Uninstall:

   ```bash
   rm -rf "${CODEX_HOME:-$HOME/.codex}/skills/strict-agent-loop"
   ```

2. For in-progress workspaces, the `.codex-loop/` directories are now inert.
   Archive them if you still want the event history (`tar czf codex-loop-archive.tgz .codex-loop/`),
   otherwise delete them.

3. If you still want strict atomic-step execution from Codex, use the built-in
   primitives rather than a skill:

   - Write the atomic-step contract directly into your prompt (one bounded task
     per round, with one machine-checkable success condition).
   - Use Codex's own session resumption instead of a custom disk-backed loop.
   - If durable progress really matters, write a short append-only log in the
     workspace yourself — simpler than a skill and harder to drift.

### If you tried to install this on Claude Code

This skill was never built for Claude Code, and is no longer recommended for
either CLI. Nothing to uninstall.

For the same "strict atomic rounds with durable state" shape on Claude Code, use
the built-in features:

- The task system (`TaskCreate` / `TaskUpdate` / `TaskList`) tracks atomic
  rounds in-session without extra infrastructure.
- Subagents under `.claude/agents/` isolate each round in its own context.
- Plan mode commits the agent to a bounded plan before execution.
- Hooks in `settings.json` (`SessionStart`, `PreToolUse`, `Stop`) cover the
  "persist state across sessions" need without a separate runtime.

---

## Historical Documentation (unmaintained)

The sections below describe the original (now-deprecated) skill. They are
preserved for auditing past usage. Do not install or run this skill.

## What This Solves

- Codex often compresses long work into a vague summary and skips the middle.
- You want every round to have one bounded atomic task and one explicit local done condition.
- You want progress, announcements, and recovery state to survive context loss.
- You want unattended work to keep looping until a real stop condition is reached.
- You want disk-backed progress broadcasts so a long run does not look dead.
- You may have many different long-running loops in one repo, so the runtime needs task management and namespacing.

## How It Works

This skill does not add a magical infinite runtime to Codex. It implements a strict loop by combining:

1. a controller protocol
2. disk-backed state and append-only ledgers
3. optional outer supervision for unattended runs

Two operating modes share the same task model:

- `interactive`: the current Codex session is the controller and reports every round to the user
- `unattended`: `scripts/supervise.py` owns the outer repetition and repeatedly runs or resumes Codex

The inner loop stays the same in both modes:

1. read the authoritative task state from disk
2. announce the next atomic round
3. do exactly one small task
4. verify it with evidence
5. persist the verified round
6. re-run machine-checkable stop rules
7. refresh progress broadcasts and summaries
8. continue unless the stop condition or a real blocker has been reached

## Managed Task Layout

One repo can host many strict loops at the same time. The default layout is manager-based:

```text
<workspace-root>/
└── .codex-loop/
    ├── registry.json
    └── tasks/
        ├── parser-fix/
        │   ├── state.json
        │   ├── events.jsonl
        │   ├── iterations.jsonl
        │   ├── status-history.jsonl
        │   ├── latest-status.txt
        │   ├── latest-stop-report.json
        │   ├── run-summary.md
        │   ├── rounds/
        │   └── supervisor/
        └── docs-cleanup/
            └── ...
```

`registry.json` is the manager index.
Each task has its own durable state and logs under `tasks/<task-id>/`.

This is the main anti-conflict mechanism:

- a repo can have many loops
- each loop gets a stable `task-id`
- mutation scripts operate on one explicit task state file
- `list_tasks.py` and `show_task.py` provide lightweight management

## Workspace Outputs vs Task Bookkeeping

Keep these two areas separate:

- Actual task outputs live under `<workspace-root>/`, such as `src/`, `docs/`, `tests/`, or `output/`.
- Loop bookkeeping lives under `.codex-loop/tasks/<task-id>/`, including `state.json`, logs, stop reports, and round summaries.

This matters in practice because a vague prompt can make Codex accidentally write deliverables into the task ledger directory. The task root is for control-plane state unless you explicitly want a bookkeeping artifact there.

## Installation

### Option 1: install into the Codex skills directory

```bash
git clone https://github.com/HansBug/strict-agent-loop "${CODEX_HOME:-$HOME/.codex}/skills/strict-agent-loop"
```

Then invoke it as `$strict-agent-loop`.

### Option 2: keep it anywhere and call it by path

```bash
git clone https://github.com/HansBug/strict-agent-loop /path/to/strict-agent-loop
```

Prompt Codex like this:

```text
Use the $strict-agent-loop skill located at /path/to/strict-agent-loop for this task.
```

## Task Management

Create one managed task per long-running objective. Use a stable `task-id` when you know you will need to resume or supervise it later.

Initialize two different tasks in the same repo:

```bash
REPO=/abs/path/to/repo
SKILL=/path/to/strict-agent-loop

python "$SKILL/scripts/init_state.py" \
  --workspace-root "$REPO" \
  --task-id parser-fix \
  --goal "Fix the parser bug in strict atomic rounds." \
  --global-stop-condition "Stop only when pytest passes and the parser regression test exists." \
  --success-evidence "pytest -q passes" \
  --stop-command "pytest -q" \
  --require-path tests/test_parser_regression.py

python "$SKILL/scripts/init_state.py" \
  --workspace-root "$REPO" \
  --task-id docs-cleanup \
  --goal "Clean up the release documentation in strict atomic rounds." \
  --global-stop-condition "Stop only when the final release note exists and contains the required summary." \
  --success-evidence "release note written" \
  --require-path docs/release-note.md \
  --require-text "docs/release-note.md::Release summary"
```

List and inspect them:

```bash
python "$SKILL/scripts/list_tasks.py" --workspace-root "$REPO"
python "$SKILL/scripts/show_task.py" --workspace-root "$REPO" --task-id parser-fix
```

If you omit `--task-id`, `init_state.py` generates one from the goal and timestamp.

## Interactive Quick Start

Initialize the managed task:

```bash
REPO=/abs/path/to/repo
TASK_ID=parser-fix
STATE="$REPO/.codex-loop/tasks/$TASK_ID/state.json"
SKILL=/path/to/strict-agent-loop

python "$SKILL/scripts/init_state.py" \
  --workspace-root "$REPO" \
  --task-id "$TASK_ID" \
  --goal "Fix the parser safely in strict atomic rounds." \
  --global-stop-condition "Stop only when pytest passes, the regression test exists, and the bug is fixed." \
  --success-evidence "pytest -q passes" \
  --next-task "Reproduce the parser failure in one minimal, verifiable step." \
  --stop-command "pytest -q" \
  --require-path tests/test_parser_regression.py
```

Then prompt Codex explicitly:

```text
Use $strict-agent-loop for this repository.
Read /abs/path/to/repo/.codex-loop/tasks/parser-fix/state.json before acting.
Treat /abs/path/to/repo as the workspace root for real work artifacts.
Treat /abs/path/to/repo/.codex-loop/tasks/parser-fix/ as bookkeeping only: state, logs, stop reports, and round summaries.
This is interactive mode.
Before each round, tell me:
- the iteration number
- how many verified rounds are already complete
- the one atomic task for this round
- the local done condition
- the global stop condition
- the condition under which the loop may stop after this round
- the recent average round time and ETA if available
Write the same announcement to the task-local events.jsonl.
After each round, verify it, run check_stop.py, then run report_status.py.
Do not widen scope and do not claim completion before the stop checks pass.
```

## Unattended Quick Start

Initialize the task in unattended mode:

```bash
REPO=/abs/path/to/repo
TASK_ID=nightly-parser-fix
STATE="$REPO/.codex-loop/tasks/$TASK_ID/state.json"
SKILL=/path/to/strict-agent-loop

python "$SKILL/scripts/init_state.py" \
  --workspace-root "$REPO" \
  --task-id "$TASK_ID" \
  --operating-mode unattended \
  --goal "Finish the queued parser task without skipping the middle." \
  --global-stop-condition "Stop only when python verify_task.py returns 0 and output/final-report.md exists." \
  --success-evidence "python verify_task.py returns 0" \
  --next-task "Start from the current repo state and make one minimal verified advance." \
  --stop-command "python verify_task.py" \
  --require-path output/final-report.md \
  --max-iterations 200 \
  --supervisor-reasoning-effort medium \
  --supervisor-max-rounds-per-invocation 5 \
  --supervisor-max-consecutive-failures 3
```

By default, unattended mode now starts each Codex invocation fresh and recovers from disk. If you explicitly want to reuse the same inner Codex thread between invocations, add `--supervisor-resume-existing-thread` when you initialize the task.
If your provider tends to reject very heavy runs during busy periods, set `--supervisor-reasoning-effort low` or `medium` for better availability.

Start the supervisor:

```bash
python "$SKILL/scripts/supervise.py" \
  --state "$STATE" \
  --skill-path "$SKILL" \
  --heartbeat-seconds 30 \
  --max-invocation-seconds 1800 \
  --max-cycles 200 \
  --prompt-note "Keep each round atomic, persist every announcement and status update, and do not stop until the machine checks pass or a real blocker is recorded."
```

The supervisor keeps broadcasting liveness and progress to the task-local files, including:

- completed iteration count
- progress bar style status
- recent round durations
- recent average round duration
- estimated remaining time when there is enough signal

It also relays inner Codex announcements plus command start/completion events to outer stdout, so an operator watching the supervisor can tell whether the run is actively moving or has stalled.

If you send `SIGINT` or `SIGTERM` to `supervise.py`, it saves the latest state, records an interruption event, and exits with code `130` so you can resume the same managed task later.

## Hailstone / Collatz Example

This is a good end-to-end stress test because the total number of rounds is not obvious up front and each round can be forced to do exactly one small step.

```text
Use $strict-agent-loop for this repository.
The workspace root is this repo itself.
Keep output/sequence.json and output/report.md under the workspace root, not inside .codex-loop/tasks/<task-id>/.
The task is to build the hailstone sequence starting from 27.
Each round may compute and append exactly one next number. Never batch multiple steps into one round.
Persist the full sequence to output/sequence.json.
After the sequence reaches 1, spend one extra round writing output/report.md that summarizes the full sequence from disk.
Stop only when python verify_hailstone.py returns 0.
Every round must be announced, verified, persisted, and reported through strict-agent-loop.
```

## Advice For Long Unattended Runs

The loop is stricter than a normal Codex prompt, but it is still subject to Codex session length, tool availability, auth state, and context limits. For real unattended work in your own repo, these practices matter:

- Use one stable `task-id` per unattended objective so you can resume the exact same task later.
- Keep the task state inside the target repo so the ledger survives terminal sessions and machine restarts.
- Keep real work artifacts in the workspace root and reserve `.codex-loop/tasks/<task-id>/` for loop bookkeeping.
- Prefer one tiny verifier script in the target repo and make it the primary `--stop-command`.
- Keep `--supervisor-max-rounds-per-invocation` modest so durable checkpoints are frequent.
- Default unattended recovery is disk-first. Only enable `--supervisor-resume-existing-thread` when you specifically want the same inner Codex thread and trust that environment.
- Set `--supervisor-reasoning-effort low` or `medium` when you need higher availability from `codex exec`; leaving it empty uses your normal Codex config default.
- Use a generous `--max-invocation-seconds` so slow synthesis or reporting rounds can finish, but still set a ceiling so a bad nested Codex invocation fails loudly instead of hanging forever.
- If an invocation times out or exits non-zero after already persisting verified progress, the supervisor keeps that progress and does not count the run as an additional consecutive failure.
- If a real write command hits a read-only filesystem error during unattended execution, the supervisor disables stored thread resume and falls back to fresh disk recovery on the next cycle.
- Send `Ctrl-C` or `kill -TERM` to the supervisor when you need to pause it; it records the interruption, saves state, and exits `130`.
- The supervisor runs `codex exec` with `--skip-git-repo-check`, so unattended work does not depend on the repo looking perfectly clean.
- In prompts, explicitly tell Codex not to re-read full `TASK.md` or full `state.json` every round. After initial recovery, it should inspect only the targeted workspace artifacts and the latest persisted status it actually needs.
- Watch `latest-status.txt`, `status-history.jsonl`, and `run-summary.md` instead of trusting the console alone.
- Compact with `compact_state.py` when the controller starts carrying too much history in memory.
- If a run must recover, reuse the same task state path instead of creating a new task unless the goal really changed.
- If you run several loops in one repo, use `registry.json` plus `list_tasks.py` and `show_task.py` to avoid collisions.
- Progress bars and ETA are heuristic when your stop rules are binary, so pick realistic `max_iterations` values.

## If You Later Ask Codex “How Do I Use This?”

A correct answer should include:

- both interactive and unattended quick starts when you did not choose a mode
- the managed layout under `.codex-loop/registry.json` and `.codex-loop/tasks/<task-id>/`
- the key durable artifacts and where they live
- a reminder that unattended runs should rely on machine-checkable stop rules
- exact shell commands or prompt text, not only prose

## Repository Layout

```text
strict-agent-loop/
├── AGENTS.md
├── SKILL.md
├── README.md
├── README_zh.md
├── agents/openai.yaml
├── scripts/
│   ├── append_event.py
│   ├── check_stop.py
│   ├── compact_state.py
│   ├── init_state.py
│   ├── json_get.py
│   ├── list_tasks.py
│   ├── report_status.py
│   ├── show_task.py
│   ├── state_tools.py
│   ├── stop_tools.py
│   ├── supervise.py
│   └── update_state.py
└── references/
    ├── management.md
    ├── modes.md
    ├── prompt_templates.md
    ├── protocol.md
    ├── recovery.md
    ├── state_schema.md
    └── stop_checks.md
```

## Validation

- You can run `python ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py /path/to/strict-agent-loop`.
- You can run the lifecycle scripts directly against a temporary workspace.
- The hailstone / Collatz scenario is the best practical forward test because it catches fake batching and weak finalization.
- The GitHub Actions workflow checks the stdlib-only scripts against Python `3.7` through `3.14`.
- Python `3.7` is validated on `ubuntu-22.04` in CI because newer Ubuntu images do not reliably provide it.

`supervise.py` is not fully exercised in CI because it depends on a working local `codex` binary plus valid session or auth state.
