# Stop Checks

Machine-checkable stop rules are the main protection against early stopping.

## Prefer External Checks

Good stop rules are things the controller can re-run without trusting model judgment:

- `pytest -q`
- `ruff check .`
- `python verify_task.py`
- `--require-path docs/final-report.md`
- `--require-text "docs/final-report.md::Complete"`

If you can write one small verifier script in the target repo, do that and make it the main `--stop-command`.

## Common Patterns

### Tests

```bash
--stop-command "pytest -q"
```

### Lint plus tests

```bash
--stop-command "ruff check ."
--stop-command "pytest -q"
```

### Generated artifact must exist

```bash
--require-path output/final-report.md
```

### Generated artifact must contain specific text

```bash
--require-text "output/final-report.md::Sequence complete"
```

### One verifier script for a long-running task

```bash
--stop-command "python verify_hailstone.py"
```

This is often the best option for unattended work.

When one repo hosts several loops, remember that these checks are evaluated per task state, not globally for every task in the registry.
If a verifier needs to inspect the task state file, point it at the managed task's `state.json`. The runtime can project the completed state for final stop evaluation before the loop has formally marked itself completed.

## Why Binary Checks Need Good Limits

Some stop checks are binary. They only say "done" or "not done".
That is fine for correctness, but it means the progress bar and ETA are only heuristics until the check passes.

To get more useful progress estimates:

- choose realistic `max_iterations`
- keep rounds small
- add secondary checks when they reflect meaningful partial completion

## Anti-Patterns

Avoid rules like:

- "stop when the repo probably works"
- "stop when the change looks complete"
- "stop when enough code was written"

Those are not safe for unattended execution.
