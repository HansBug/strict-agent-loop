#!/usr/bin/env python3

import argparse
import json
from pathlib import Path

from state_tools import (
    append_event_record,
    build_status_report,
    compact_history,
    load_state,
    save_state,
    write_run_summary,
    write_status_text,
    write_stop_report_file,
)
from stop_tools import build_stop_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compact long strict-agent-loop history into a snapshot.")
    parser.add_argument("--state", required=True, help="Path to the task state file")
    parser.add_argument("--keep-last", type=int, default=8, help="Retain this many recent history entries")
    parser.add_argument(
        "--max-archive-chars",
        type=int,
        default=8000,
        help="Maximum number of characters to keep in archive_summary",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_path = Path(args.state).resolve()
    state = load_state(state_path)
    before_count = len(state.get("history", []))
    compact_history(state, keep_last=args.keep_last, max_archive_chars=args.max_archive_chars)
    after_count = len(state.get("history", []))
    append_event_record(
        state_path,
        state,
        "state.compacted",
        "Compacted loop history for recovery.",
        data={
            "history_entries_before": before_count,
            "history_entries_after": after_count,
            "keep_last": args.keep_last,
        },
    )
    stop_report = build_stop_report(state, state_path=state_path)
    report = build_status_report(state, stop_report=stop_report)
    write_status_text(state, report)
    write_stop_report_file(state_path, state, stop_report)
    write_run_summary(state_path, state, stop_report=stop_report, report=report)
    save_state(state_path, state)
    print(
        json.dumps(
            {
                "state": str(state_path),
                "history_entries": after_count,
                "snapshot_chars": len(state.get("context_snapshot", "")),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
