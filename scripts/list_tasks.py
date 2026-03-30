#!/usr/bin/env python3

import argparse
import json
from pathlib import Path

from state_tools import default_registry_path_for_workspace, load_registry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List managed strict-agent-loop tasks for a workspace.")
    parser.add_argument(
        "--workspace-root",
        default=".",
        help="Workspace root that contains the .codex-loop manager directory. Defaults to the current directory.",
    )
    parser.add_argument("--json", action="store_true", help="Print the task registry as JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace_root = Path(args.workspace_root).resolve()
    registry_path = default_registry_path_for_workspace(workspace_root)
    registry = load_registry(registry_path)
    tasks = list(registry.get("tasks", {}).values())
    tasks.sort(key=lambda item: item.get("updated_at", ""), reverse=True)

    if args.json:
        payload = {
            "registry_path": str(registry_path),
            "tasks": tasks,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print("Registry: %s" % registry_path)
    if not tasks:
        print("No managed tasks found.")
        return 0

    for task in tasks:
        print(
            "- %s | %s | iter=%s | updated=%s | %s"
            % (
                task.get("id", "unknown"),
                task.get("status", "unknown"),
                task.get("iteration", 0),
                task.get("updated_at", "unknown"),
                task.get("goal", ""),
            )
        )
        print("  state: %s" % task.get("state_path", ""))
        next_task = task.get("next_task", "")
        if next_task:
            print("  next: %s" % next_task)
        blocker_reason = task.get("blocker_reason", "")
        if blocker_reason:
            print("  blocker: %s" % blocker_reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
