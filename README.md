# strict-agent-loop

English | [简体中文](./README_zh.md)

`strict-agent-loop` is a Codex skill for work that must not be shortcut. It forces a controller-style loop that does one small verified task per round, persists the round to disk, re-checks stop conditions, and keeps going until success or a real blocker.

The helper scripts are stdlib-only and written to stay compatible with Python `3.7` through `3.14`.

## What It Solves

- Codex tries to compress the middle of a long task.
- You want one bounded task per round instead of vague milestones.
- You want a durable ledger instead of relying on model memory.
- You want unattended runs that survive beyond one Codex invocation.
- You want progress broadcasts that make it obvious the run is still alive.

## How It Works

There are two modes.

- `interactive`: the current Codex session is the controller and reports every round to the user.
- `unattended`: `scripts/supervise.py` owns the outer while-loop and repeatedly calls `codex exec` or `codex exec resume`.

The inner controller follows the same contract in both modes:

1. Read the authoritative state from `.codex-loop/state.json`.
2. Announce exactly one atomic task for the next round.
3. Do the round, verify it, and persist the result.
4. Re-run machine-checkable stop checks.
5. Refresh progress broadcasts and append-only logs.
6. Continue until stop checks pass or a blocker is recorded.

This repository deliberately separates the rolling state window from the full audit trail:

- `state.json` keeps the current working state and a recent history window.
- `iterations.jsonl`, `events.jsonl`, `status-history.jsonl`, and `rounds/` keep the append-only full record.

That means the loop can compact memory pressure without losing the full timeline.

## Durable Artifacts

These files are the core of the system. They are meant to be queryable even after compaction or session loss.

- `.codex-loop/state.json`: authoritative current state, limits, next task, rolling history window.
- `.codex-loop/events.jsonl`: append-only control-plane timeline, including round announcements.
- `.codex-loop/iterations.jsonl`: append-only verified round ledger with the full round payload.
- `.codex-loop/status-history.jsonl`: append-only progress broadcasts and heartbeat snapshots.
- `.codex-loop/latest-status.txt`: current human-readable status snapshot.
- `.codex-loop/latest-stop-report.json`: latest machine stop-evaluation result.
- `.codex-loop/run-summary.md`: current run-level summary with links to durable artifacts.
- `.codex-loop/rounds/iteration-XXXX.md`: human-readable per-round summaries.
- `.codex-loop/supervisor/`: unattended-only prompts, Codex JSONL output, and invocation logs.

## Install

### Option 1: install into the Codex skills directory

```bash
git clone https://github.com/HansBug/strict-agent-loop "${CODEX_HOME:-$HOME/.codex}/skills/strict-agent-loop"
```

Then invoke it as `$strict-agent-loop`.

### Option 2: keep it anywhere and pass the path explicitly

```bash
git clone https://github.com/HansBug/strict-agent-loop /path/to/strict-agent-loop
```

Then call it with an explicit path:

```text
Use $strict-agent-loop at /path/to/strict-agent-loop for this task.
```

## Interactive Quick Start

Initialize the state inside the target repository:

```bash
python /path/to/strict-agent-loop/scripts/init_state.py \
  --state /abs/path/to/repo/.codex-loop/state.json \
  --goal "Fix the parser safely in strict atomic rounds." \
  --global-stop-condition "Stop only when pytest passes, the regression test exists, and the parser bug is fixed." \
  --workspace-root /abs/path/to/repo \
  --success-evidence "pytest -q passes" \
  --next-task "Reproduce the parser failure in one small round and capture the exact failing behavior." \
  --stop-command "pytest -q" \
  --require-path tests/test_parser_regression.py
```

Then prompt Codex explicitly:

```text
Use $strict-agent-loop for this repository.
Read /abs/path/to/repo/.codex-loop/state.json before acting.
Operate in interactive mode.
Before each round, tell me:
- the iteration number
- how many verified rounds are already done
- this round's atomic task
- the local done condition
- the global stop condition
- when to stop after this round
- the recent average round time and ETA if available
Log the same announcement to .codex-loop/events.jsonl.
After each round, verify it, run check_stop.py, then run report_status.py.
Do not broaden scope and do not stop early.
```

## Unattended Quick Start

Initialize unattended mode:

```bash
python /path/to/strict-agent-loop/scripts/init_state.py \
  --state /abs/path/to/repo/.codex-loop/state.json \
  --goal "Finish the queued task in strict atomic rounds without skipping work." \
  --global-stop-condition "Stop only when verify_task.py returns 0 and the required report exists." \
  --workspace-root /abs/path/to/repo \
  --operating-mode unattended \
  --success-evidence "python verify_task.py returns 0" \
  --next-task "Perform the smallest verified step that advances the task from the current repo state." \
  --stop-command "python verify_task.py" \
  --require-path output/final-report.md \
  --max-iterations 200 \
  --supervisor-max-rounds-per-invocation 5 \
  --supervisor-max-consecutive-failures 3
```

Run the supervisor:

```bash
python /path/to/strict-agent-loop/scripts/supervise.py \
  --state /abs/path/to/repo/.codex-loop/state.json \
  --skill-path /path/to/strict-agent-loop \
  --heartbeat-seconds 30 \
  --max-invocation-seconds 900 \
  --max-cycles 200 \
  --prompt-note "Keep each round atomic, write durable announcements, and stop only when the machine checks pass."
```

The supervisor will keep refreshing `latest-status.txt`, `status-history.jsonl`, `latest-stop-report.json`, and `run-summary.md` so the run does not look stuck.

## Example Prompt: Hailstone Sequence

This is a good validation task because the number of rounds is not obvious in advance and each round can be constrained to exactly one calculation.

```text
Use $strict-agent-loop for this repository.
The task is to build the hailstone sequence starting from 27.
Each round may calculate and append exactly one next number.
Persist the sequence in output/sequence.json.
Do not skip ahead and do not append more than one new number in one round.
When the sequence finally reaches 1, use one additional round to write output/report.md that includes the full sequence.
Stop only when python verify_hailstone.py returns 0.
Every round must be announced, logged, verified, and persisted with the strict-agent-loop scripts.
```

## How To Ask Codex To Use It

If you later ask Codex "how do I use `strict-agent-loop`?", the answer should at minimum give you:

- one interactive quick start
- one unattended quick start
- the durable artifact paths
- a warning that unattended success should be machine-checkable
- a concrete prompt or command, not just abstract guidance

## Designing Good Stop Checks

Good stop checks are narrow and external:

- `pytest -q`
- `ruff check .`
- `python verify_hailstone.py`
- `--require-path output/report.md`
- `--require-text "output/report.md::Sequence complete"`

Bad stop checks depend on model interpretation alone:

- "stop when it feels done"
- "stop when the code looks good"
- "stop when the repo probably works"

When possible, write one small verifier script in the target repo and make that the main stop command.

## Real-World Limits And How To Work With Them

This skill enforces a stricter protocol, not a new runtime. Actual execution is still bounded by Codex session duration, tool availability, authentication, and context length. To make long runs hold up in practice:

- Persist the `.codex-loop/` directory inside the target repository, not in a temp folder.
- Treat disk state as authoritative whenever memory and the repo disagree.
- Keep each round small enough that verification is cheap.
- Prefer one verifier script that returns `0` only when the task is truly complete.
- Keep `max_iterations` realistic. The ETA and progress bar are only heuristics unless your stop checks expose partial progress.
- In unattended mode, keep `max_rounds_per_invocation` modest so resume/recovery points are frequent.
- If nested Codex invocations can stall in your environment, set `--max-invocation-seconds` so the supervisor fails loudly and retries instead of hanging forever.
- Run `compact_state.py` every few rounds or when the transcript starts getting heavy.
- Watch `latest-status.txt`, `status-history.jsonl`, and `run-summary.md` instead of relying on the live Codex console alone.
- If a required tool disappears, record a real blocker instead of letting the run drift.

## Repository Layout

```text
strict-agent-loop/
├── SKILL.md
├── README.md
├── README_zh.md
├── agents/openai.yaml
├── scripts/
│   ├── append_event.py
│   ├── check_stop.py
│   ├── compact_state.py
│   ├── init_state.py
│   ├── report_status.py
│   ├── state_tools.py
│   ├── stop_tools.py
│   ├── supervise.py
│   └── update_state.py
└── references/
    ├── modes.md
    ├── prompt_templates.md
    ├── protocol.md
    ├── recovery.md
    ├── state_schema.md
    └── stop_checks.md
```

## Validation

- Run `python ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py /path/to/strict-agent-loop`.
- Run the lifecycle scripts directly on a temp repo.
- Forward-test it on a real task. A hailstone/Collatz sequence task is a good stress case because each round can be limited to one calculation and the final report must aggregate the whole sequence.
- GitHub Actions in [python-compat.yml](./.github/workflows/python-compat.yml) smoke-test the stdlib scripts on Python `3.7` through `3.14`.

The unattended supervisor itself is not fully CI-smoke-tested because it depends on a working local `codex` installation and valid session/auth state.
