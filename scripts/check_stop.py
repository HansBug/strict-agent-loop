#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path
from typing import List

from state_tools import load_state


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate whether a strict-agent-loop should stop.")
    parser.add_argument("--state", required=True, help="Path to .codex-loop/state.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state = load_state(Path(args.state).resolve())
    counters = state.get("counters", {})
    limits = state.get("limits", {})
    history = state.get("history", [])
    last_entry = history[-1] if history else {}

    status = state.get("status", "running")
    reasons = []  # type: List[str]
    should_stop = False
    success = False
    exit_code = 1

    if status == "completed" or last_entry.get("stop_condition_met"):
        should_stop = True
        success = True
        exit_code = 0
        reasons.append("global_stop_condition_met")
    elif status in {"blocked", "failed"}:
        should_stop = True
        success = False
        exit_code = 2
        reasons.append(f"loop_status_{status}")
    elif int(counters.get("iteration", 0)) >= int(limits.get("max_iterations", 200)):
        should_stop = True
        success = False
        exit_code = 2
        reasons.append("max_iterations_reached")
    elif int(counters.get("no_progress_rounds", 0)) >= int(limits.get("max_no_progress_rounds", 8)):
        should_stop = True
        success = False
        exit_code = 2
        reasons.append("max_no_progress_rounds_reached")
    else:
        reasons.append("continue")

    payload = {
        "should_stop": should_stop,
        "success": success,
        "status": status,
        "reasons": reasons,
        "iteration": int(counters.get("iteration", 0)),
        "no_progress_rounds": int(counters.get("no_progress_rounds", 0)),
        "next_task": state.get("next_task", ""),
        "global_stop_condition": state.get("global_stop_condition", ""),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
