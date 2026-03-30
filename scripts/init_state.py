#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

from state_tools import build_state, save_state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize a strict-agent-loop state file.")
    parser.add_argument("--state", required=True, help="Path to .codex-loop/state.json")
    parser.add_argument("--goal", required=True, help="Overall goal of the loop")
    parser.add_argument(
        "--global-stop-condition",
        required=True,
        help="Condition that must be satisfied before the loop may stop successfully",
    )
    parser.add_argument("--workspace-root", required=True, help="Target workspace root")
    parser.add_argument(
        "--success-evidence",
        action="append",
        default=[],
        help="Evidence that should exist at successful completion. Repeat as needed.",
    )
    parser.add_argument(
        "--blocker-definition",
        default="Stop only for a real blocker that prevents further safe progress.",
        help="What counts as a blocker for this loop",
    )
    parser.add_argument("--max-iterations", type=int, default=200)
    parser.add_argument("--max-no-progress-rounds", type=int, default=8)
    parser.add_argument("--max-context-chars", type=int, default=12000)
    parser.add_argument("--executor-agent-id", default="", help="Optional existing executor agent id")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing state file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_path = Path(args.state).resolve()
    if state_path.exists() and not args.force:
        print(f"State file already exists: {state_path}", file=sys.stderr)
        return 1

    state = build_state(
        goal=args.goal,
        global_stop_condition=args.global_stop_condition,
        workspace_root=args.workspace_root,
        success_evidence=args.success_evidence,
        blocker_definition=args.blocker_definition,
        max_iterations=args.max_iterations,
        max_no_progress_rounds=args.max_no_progress_rounds,
        max_context_chars=args.max_context_chars,
        executor_agent_id=args.executor_agent_id,
    )
    save_state(state_path, state)
    print(json.dumps({"state": str(state_path), "status": state["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
