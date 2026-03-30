#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

from state_tools import (
    append_event_record,
    append_status_snapshot,
    build_state,
    build_status_report,
    save_state,
    write_run_summary,
    write_status_text,
    write_stop_report_file,
)
from stop_tools import build_stop_report


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
    parser.add_argument("--next-task", default="", help="Optional initial atomic task for iteration 1")
    parser.add_argument(
        "--operating-mode",
        choices=["interactive", "unattended"],
        default="interactive",
        help="Choose interactive mode for a human-in-the-loop session or unattended mode for supervisor-driven execution.",
    )
    parser.add_argument("--max-iterations", type=int, default=200)
    parser.add_argument("--max-no-progress-rounds", type=int, default=8)
    parser.add_argument("--max-context-chars", type=int, default=12000)
    parser.add_argument("--executor-agent-id", default="", help="Optional existing executor agent id")
    parser.add_argument(
        "--stop-command",
        action="append",
        default=[],
        help="Machine-checkable stop command, such as 'pytest -q'. Repeat as needed.",
    )
    parser.add_argument(
        "--require-path",
        action="append",
        default=[],
        help="Path that must exist before the loop may stop successfully. Repeat as needed.",
    )
    parser.add_argument(
        "--require-text",
        action="append",
        default=[],
        help="Literal text check in the format '<path>::<pattern>'. Repeat as needed.",
    )
    parser.add_argument("--event-log", default="", help="Optional custom path for events.jsonl")
    parser.add_argument("--round-summary-dir", default="", help="Optional custom directory for round summaries")
    parser.add_argument(
        "--supervisor-codex-bin",
        default="codex",
        help="Codex binary used by unattended supervision",
    )
    parser.add_argument("--supervisor-model", default="", help="Optional model override for unattended supervision")
    parser.add_argument(
        "--supervisor-sandbox",
        default="workspace-write",
        choices=["read-only", "workspace-write", "danger-full-access"],
        help="Sandbox mode for unattended codex exec invocations",
    )
    parser.add_argument(
        "--supervisor-max-rounds-per-invocation",
        type=int,
        default=5,
        help="Maximum verified iterations one unattended codex invocation should complete before returning control to the supervisor.",
    )
    parser.add_argument(
        "--supervisor-max-consecutive-failures",
        type=int,
        default=3,
        help="How many non-zero unattended codex exits to tolerate before marking the loop failed.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing state file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_path = Path(args.state).resolve()
    if state_path.exists() and not args.force:
        print("State file already exists: %s" % state_path, file=sys.stderr)
        return 1

    state = build_state(
        state_path=state_path,
        goal=args.goal,
        global_stop_condition=args.global_stop_condition,
        workspace_root=args.workspace_root,
        success_evidence=args.success_evidence,
        blocker_definition=args.blocker_definition,
        max_iterations=args.max_iterations,
        max_no_progress_rounds=args.max_no_progress_rounds,
        max_context_chars=args.max_context_chars,
        executor_agent_id=args.executor_agent_id,
        operating_mode=args.operating_mode,
        stop_commands=args.stop_command,
        required_paths=args.require_path,
        text_patterns=args.require_text,
        event_log_path=args.event_log,
        round_summary_dir=args.round_summary_dir,
        supervisor_codex_bin=args.supervisor_codex_bin,
        supervisor_model=args.supervisor_model,
        supervisor_sandbox=args.supervisor_sandbox,
        supervisor_max_rounds_per_invocation=args.supervisor_max_rounds_per_invocation,
        supervisor_max_consecutive_failures=args.supervisor_max_consecutive_failures,
        next_task=args.next_task,
    )
    append_event_record(
        state_path,
        state,
        "loop.initialized",
        "Initialized strict-agent-loop state.",
        data={
            "operating_mode": args.operating_mode,
            "stop_commands": len(args.stop_command),
            "required_paths": len(args.require_path),
            "required_text_checks": len(args.require_text),
        },
    )
    stop_report = build_stop_report(state)
    report = build_status_report(state, stop_report=stop_report)
    write_status_text(state, report)
    write_stop_report_file(state_path, state, stop_report)
    write_run_summary(state_path, state, stop_report=stop_report, report=report)
    append_status_snapshot(
        state_path,
        state,
        report,
        label="loop.initialized",
        stop_report=stop_report,
    )
    save_state(state_path, state)
    print(
        json.dumps(
            {
                "state": str(state_path),
                "status": state["status"],
                "operating_mode": state["operating_mode"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
