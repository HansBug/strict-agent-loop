# Management

Use this note when one workspace may host multiple strict loops.

## Managed Layout

The default layout is:

- manager registry: `.codex-loop/registry.json`
- per-task root: `.codex-loop/tasks/<task-id>/`
- per-task state: `.codex-loop/tasks/<task-id>/state.json`

All durable task artifacts stay under the task root.
Actual deliverables should usually stay under the workspace root, not inside `.codex-loop/tasks/<task-id>/`.

## Choosing A Task Id

Use one stable `task-id` per long-running objective.

Good task ids:

- `parser-fix`
- `nightly-release-docs`
- `hailstone-27`

Bad task ids:

- `task`
- `new`
- `temp`

If the user does not provide one and a new task is being created, `init_state.py` may generate it from the goal and timestamp.

## Default Management Commands

Create a task:

```bash
python scripts/init_state.py --workspace-root /repo --task-id parser-fix ...
```

List tasks:

```bash
python scripts/list_tasks.py --workspace-root /repo
```

Inspect one task:

```bash
python scripts/show_task.py --workspace-root /repo --task-id parser-fix
```

Mutate one task:

```bash
python scripts/update_state.py --state /repo/.codex-loop/tasks/parser-fix/state.json ...
```

This split is intentional:

- creation may derive the default path automatically
- later mutations require an explicit `--state`
- explicit task-local mutation avoids writing to the wrong loop when several tasks coexist

## Resume Rules

When resuming:

- prefer a user-supplied `task-id`
- otherwise read `registry.json`
- if only one plausible running task exists, continue it
- if several plausible tasks exist, ask the user which one to resume

Do not silently choose a random task in a busy repo.

## Cleanup

Completed task roots are useful as audit trails.
Do not delete them automatically.

If operators want cleanup later, they can archive or remove old task directories deliberately after they no longer need the durable trail.
