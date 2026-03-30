# strict-agent-loop

English | [简体中文](./README_zh.md)

`strict-agent-loop` is a Codex skill for forcing disciplined, stepwise execution on tasks that are easy to shortcut. It combines a persistent executor agent, a controller loop in the current agent, and a disk-backed state ledger so the work can continue round by round until a clear stopping rule is met.

## What It Enforces

- One atomic task per iteration.
- An explicit user-facing announcement before each round.
- A persistent executor agent that inherits the current context on the first round.
- A disk state file at `.codex-loop/state.json`.
- Verification and stop-condition checks after every round.
- Recovery from agent loss by using a compact snapshot instead of restarting from scratch.

## Repository Layout

```text
strict-agent-loop/
├── SKILL.md
├── README.md
├── README_zh.md
├── agents/openai.yaml
├── scripts/
│   ├── init_state.py
│   ├── update_state.py
│   ├── check_stop.py
│   ├── compact_state.py
│   └── state_tools.py
└── references/
    ├── protocol.md
    ├── prompt_templates.md
    ├── state_schema.md
    └── recovery.md
```

## Install

### Option 1: Install for automatic discovery

Clone the repository into your Codex skills directory:

```bash
git clone https://github.com/HansBug/strict-agent-loop "${CODEX_HOME:-$HOME/.codex}/skills/strict-agent-loop"
```

After that, Codex can invoke it as `$strict-agent-loop`.

### Option 2: Keep it anywhere and reference the path explicitly

Clone the repository anywhere you want:

```bash
git clone https://github.com/HansBug/strict-agent-loop /path/to/strict-agent-loop
```

Invoke it with an explicit path:

```text
Use $strict-agent-loop at /path/to/strict-agent-loop to help with this task.
```

## Invocation Pattern

Use the skill when you need Codex to keep looping through small, verified tasks until a global stop condition is satisfied.

Example:

```text
Use $strict-agent-loop to refactor this repository in strict atomic steps.
Before each round, tell me the exact task, the local done condition, and the global stop condition.
Create and maintain .codex-loop/state.json in the repo root.
Keep using one persistent executor agent.
Stop only when pytest passes, lint passes, and the requested refactor is complete.
```

Another example with an explicit path:

```text
Use $strict-agent-loop at /abs/path/to/strict-agent-loop to fix the bug in this repo.
Do one atomic task per round.
Inherit the current context into the first executor agent.
Keep looping until the failing test is fixed and a regression test is added.
```

## Helper Scripts

Initialize the state ledger:

```bash
python scripts/init_state.py \
  --state /abs/path/to/repo/.codex-loop/state.json \
  --goal "Fix the reported bug safely" \
  --global-stop-condition "Stop only when the bug is fixed, a regression test exists, and pytest passes." \
  --workspace-root /abs/path/to/repo \
  --success-evidence "pytest passes"
```

Append one verified iteration:

```bash
python scripts/update_state.py \
  --state /abs/path/to/repo/.codex-loop/state.json \
  --task "Patch the parser for empty input" \
  --local-done-condition "The parser rejects empty input with the expected error" \
  --result-summary "Parser now raises ValueError for empty input" \
  --verification-summary "Verified by targeted pytest for parser edge cases" \
  --next-task "Add regression coverage for CLI entrypoint"
```

If the current executor was newly spawned from the current context, add `--executor-inherited-context`.
If you had to replace a dead executor, add `--agent-id <new_id> --recovery`.

Check whether the loop should stop:

```bash
python scripts/check_stop.py --state /abs/path/to/repo/.codex-loop/state.json
```

Compact long history for recovery:

```bash
python scripts/compact_state.py --state /abs/path/to/repo/.codex-loop/state.json
```

## Expected Control Flow

1. The current agent acts as controller.
2. The controller defines the goal and global stop condition.
3. The controller initializes `.codex-loop/state.json`.
4. The controller spawns one executor agent with inherited context.
5. Each round does exactly one atomic task.
6. The controller verifies the outcome, updates state, and checks whether to stop.
7. If the executor is lost, the controller recovers from the compact snapshot and continues.

## Limits

This skill enforces a stricter protocol, not a new runtime. It makes shortcutting harder, but it cannot guarantee a mathematically infinite loop because actual execution is still bounded by the Codex session, tool availability, and model context limits.

## Practical Advice For Real Sessions

To make the loop hold up better in practice:

- Keep the global stop condition concrete and externally checkable. Good examples are `pytest passes`, `a specific file is updated`, or `a regression test exists`.
- Keep each iteration small enough that one round can be verified quickly. If one step sounds like a milestone, split it again.
- Write state into the target repository, not into a temporary directory. That makes interruption and recovery much cheaper.
- Run `compact_state.py` periodically, especially after several rounds or after a large diff, so the controller can recover from a short context window.
- Decide in advance what counts as a real blocker and what counts as a missing tool. If a required tool is unavailable, record it explicitly instead of letting the loop drift.
- Prefer success evidence that the controller can rerun directly, such as `pytest -q`, `npm test`, `ruff check`, or a short file diff inspection.
- If the task is large, state hard limits up front, such as `max_iterations` or `max_no_progress_rounds`, so the loop fails loudly instead of silently degrading.

If you expect a long session, a good default is:

- persist `.codex-loop/state.json` in the repo root
- compact every 5 to 10 verified rounds
- keep one executor agent per active task
- treat the disk state as authoritative whenever memory and repo state disagree

## Local Validation

This repository is designed to be validated in two ways:

- run `python ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py /path/to/strict-agent-loop`
- forward-test it on a separate toy repository with a real Codex task
