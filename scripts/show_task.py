#!/usr/bin/env python3

import argparse
import json
from pathlib import Path

from state_tools import (
    default_registry_path_for_workspace,
    default_state_path_for_workspace,
    default_task_root_for_workspace,
    load_registry,
    slugify_task_component,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show one managed strict-agent-loop task.")
    parser.add_argument("--workspace-root", required=True, help="Workspace root that owns the .codex-loop manager.")
    parser.add_argument("--task-id", required=True, help="Task id to inspect.")
    parser.add_argument("--json", action="store_true", help="Print the task details as JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace_root = Path(args.workspace_root).resolve()
    task_id = slugify_task_component(args.task_id, fallback="task")
    registry_path = default_registry_path_for_workspace(workspace_root)
    task_root_dir = default_task_root_for_workspace(workspace_root, task_id)
    state_path = default_state_path_for_workspace(workspace_root, task_id)
    registry = load_registry(registry_path)
    registry_entry = registry.get("tasks", {}).get(task_id)
    payload = {
        "registry_path": str(registry_path),
        "task_id": task_id,
        "task_root_dir": str(task_root_dir),
        "state_path": str(state_path),
        "exists": state_path.exists(),
        "registry_entry": registry_entry,
    }

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print("Registry: %s" % registry_path)
    print("Task: %s" % task_id)
    print("Task root: %s" % task_root_dir)
    print("State: %s" % state_path)
    print("Exists: %s" % ("yes" if state_path.exists() else "no"))
    if registry_entry:
        print("Status: %s" % registry_entry.get("status", "unknown"))
        print("Iterations: %s" % registry_entry.get("iteration", 0))
        updated_at = registry_entry.get("updated_at", "")
        if updated_at:
            print("Updated at: %s" % updated_at)
        next_task = registry_entry.get("next_task", "")
        if next_task:
            print("Next task: %s" % next_task)
        blocker_reason = registry_entry.get("blocker_reason", "")
        if blocker_reason:
            print("Blocker: %s" % blocker_reason)
    else:
        print("Registry entry: missing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
