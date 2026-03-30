#!/usr/bin/env python3

import argparse
import json
from pathlib import Path

from state_tools import (
    append_status_snapshot,
    build_status_report,
    load_state,
    render_status_text,
    save_state,
    write_run_summary,
    write_status_text,
    write_stop_report_file,
)
from stop_tools import build_stop_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a progress-style status report for strict-agent-loop.")
    parser.add_argument("--state", required=True, help="Path to the task state file")
    parser.add_argument("--json", action="store_true", help="Print the status report as JSON")
    parser.add_argument(
        "--label",
        default="status.reported",
        help="Label stored in status-history.jsonl for this status snapshot.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_path = Path(args.state).resolve()
    state = load_state(state_path)
    stop_report = build_stop_report(state, state_path=state_path)
    report = build_status_report(state, stop_report=stop_report)
    status_path = write_status_text(state, report)
    stop_report_path = write_stop_report_file(state_path, state, stop_report)
    run_summary_path = write_run_summary(state_path, state, stop_report=stop_report, report=report)
    append_status_snapshot(state_path, state, report, label=args.label, stop_report=stop_report)
    save_state(state_path, state)

    if args.json:
        payload = dict(report)
        payload["status_text_path"] = status_path
        payload["stop_report_path"] = stop_report_path
        payload["run_summary_path"] = run_summary_path
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_status_text(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
