#!/usr/bin/env python3

import argparse
import json
from pathlib import Path

from state_tools import (
    append_event_record,
    build_status_report,
    clear_blocker,
    load_state,
    save_state,
    write_run_summary,
    write_stop_report_file,
)
from stop_tools import build_stop_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate whether a strict-agent-loop should stop.")
    parser.add_argument("--state", required=True, help="Path to the task state file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_path = Path(args.state).resolve()
    state = load_state(state_path)
    report = build_stop_report(state, state_path=state_path)
    if report.get("should_stop") and report.get("success") and state.get("status") != "completed":
        state["status"] = "completed"
        state["next_task"] = "Stop condition met; exit."
        clear_blocker(state)
        append_event_record(
            state_path,
            state,
            "loop.completed.by-check-stop",
            "Marked the loop completed after machine-checkable stop conditions passed.",
            data={
                "iteration": report.get("iteration", 0),
                "passed_checks": report.get("stop_checks", {}).get("passed_checks", 0),
                "total_checks": report.get("stop_checks", {}).get("total_checks", 0),
            },
        )
        save_state(state_path, state)
        state = load_state(state_path)
        report = build_stop_report(state, state_path=state_path)
    status_report = build_status_report(state, stop_report=report)
    write_stop_report_file(state_path, state, report)
    write_run_summary(state_path, state, stop_report=report, report=status_report)
    save_state(state_path, state)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return int(report.get("exit_code", 1))


if __name__ == "__main__":
    raise SystemExit(main())
