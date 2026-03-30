#!/usr/bin/env python3

import argparse
import json
from pathlib import Path

from state_tools import (
    append_iteration_record,
    append_event_record,
    build_context_snapshot,
    clear_blocker,
    format_list,
    load_state,
    normalize_text,
    save_state,
    seconds_between_timestamps,
    set_blocker,
    utc_now,
    write_round_summary,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Append one verified iteration to the strict loop state.")
    parser.add_argument("--state", required=True, help="Path to the task state file")
    parser.add_argument("--task", required=True, help="Atomic task for this iteration")
    parser.add_argument("--local-done-condition", required=True, help="Completion condition for this iteration")
    parser.add_argument("--result-summary", required=True, help="Short verified summary of the result")
    parser.add_argument("--verification-summary", required=True, help="Evidence used to verify the result")
    parser.add_argument(
        "--announcement",
        default="",
        help="Round announcement that was shown to the user or written to the unattended event log before execution.",
    )
    parser.add_argument(
        "--progress",
        choices=["made", "none"],
        default="made",
        help="Whether this iteration made objective progress",
    )
    parser.add_argument(
        "--status",
        choices=["running", "completed", "blocked", "failed"],
        default="running",
        help="Loop status after recording this iteration",
    )
    parser.add_argument("--stop-met", action="store_true", help="Mark the global stop condition as met")
    parser.add_argument("--stop-reason", default="", help="Why the loop completed, blocked, or failed")
    parser.add_argument("--needs-human-input", action="store_true", help="Mark that a blocker needs human input")
    parser.add_argument("--next-task", default="", help="Planned next atomic task")
    parser.add_argument("--agent-id", default="", help="Persist the current executor agent id")
    parser.add_argument(
        "--executor-inherited-context",
        action="store_true",
        help="Mark that the current executor was created with inherited context",
    )
    parser.add_argument(
        "--recovery",
        action="store_true",
        help="Increment recovery_count because a replacement executor was created",
    )
    parser.add_argument("--evidence", action="append", default=[], help="File path or artifact used as evidence")
    parser.add_argument("--artifact", action="append", default=[], help="Generated artifact path")
    parser.add_argument("--context-snapshot", default="", help="Override the compact context snapshot")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_path = Path(args.state).resolve()
    state = load_state(state_path)

    previous_history = state.get("history", [])
    previous_timestamp = previous_history[-1].get("timestamp", "") if previous_history else ""
    iteration = int(state.get("counters", {}).get("iteration", 0)) + 1
    progress_made = args.progress == "made"
    loop_status = "completed" if args.stop_met else args.status
    entry_timestamp = utc_now()
    history_entry = {
        "iteration": iteration,
        "timestamp": entry_timestamp,
        "task": normalize_text(args.task),
        "announcement": normalize_text(args.announcement),
        "local_done_condition": normalize_text(args.local_done_condition),
        "result_summary": normalize_text(args.result_summary),
        "verification_summary": normalize_text(args.verification_summary),
        "progress_made": progress_made,
        "status": loop_status,
        "stop_condition_met": bool(args.stop_met),
        "stop_reason": normalize_text(args.stop_reason),
        "needs_human_input": bool(args.needs_human_input),
        "evidence": format_list(args.evidence),
        "artifacts": format_list(args.artifact),
        "next_task": normalize_text(args.next_task),
        "elapsed_since_previous_seconds": seconds_between_timestamps(previous_timestamp, entry_timestamp),
    }

    state.setdefault("history", []).append(history_entry)
    counters = state.setdefault("counters", {})
    counters["iteration"] = iteration
    counters["no_progress_rounds"] = 0 if progress_made else int(counters.get("no_progress_rounds", 0)) + 1
    if args.recovery:
        counters["recovery_count"] = int(counters.get("recovery_count", 0)) + 1
    if args.agent_id:
        state.setdefault("agent", {})["executor_id"] = normalize_text(args.agent_id)
    if args.executor_inherited_context:
        state.setdefault("agent", {})["spawned_from_current_context"] = True

    if loop_status in {"blocked", "failed"}:
        set_blocker(
            state,
            args.stop_reason or args.result_summary,
            needs_human_input=args.needs_human_input,
        )
    else:
        clear_blocker(state)

    state["next_task"] = normalize_text(args.next_task)
    state["status"] = loop_status
    state["context_snapshot"] = (
        args.context_snapshot.strip() if args.context_snapshot.strip() else build_context_snapshot(state)
    )
    summary_path = write_round_summary(state_path, state, history_entry)
    history_entry["round_summary_path"] = summary_path
    append_iteration_record(state_path, state, history_entry)

    if loop_status == "completed":
        event_kind = "loop.completed"
    elif loop_status == "blocked":
        event_kind = "loop.blocked"
    elif loop_status == "failed":
        event_kind = "loop.failed"
    else:
        event_kind = "iteration.recorded"

    append_event_record(
        state_path,
        state,
        event_kind,
        args.result_summary,
        data={
            "iteration": iteration,
            "task": history_entry["task"],
            "status": loop_status,
            "next_task": history_entry["next_task"],
            "stop_met": history_entry["stop_condition_met"],
            "round_summary_path": summary_path,
        },
    )

    save_state(state_path, state)
    print(
        json.dumps(
            {
                "state": str(state_path),
                "iteration": iteration,
                "status": state["status"],
                "no_progress_rounds": counters["no_progress_rounds"],
                "round_summary_path": summary_path,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
