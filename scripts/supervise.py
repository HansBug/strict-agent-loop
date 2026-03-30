#!/usr/bin/env python3

import argparse
import json
import os
import selectors
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from state_tools import (
    append_event_record,
    append_status_snapshot,
    build_status_report,
    clear_blocker,
    load_state,
    normalize_text,
    render_status_text,
    save_state,
    set_blocker,
    utc_now,
    write_run_summary,
    write_status_text,
    write_stop_report_file,
)
from stop_tools import build_stop_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run strict-agent-loop in unattended supervisor mode.")
    parser.add_argument("--state", required=True, help="Path to the task state file")
    parser.add_argument("--skill-path", required=True, help="Path to the strict-agent-loop skill repository")
    parser.add_argument("--max-cycles", type=int, default=200, help="Maximum outer supervisor cycles")
    parser.add_argument("--sleep-seconds", type=int, default=0, help="Seconds to sleep between cycles")
    parser.add_argument(
        "--heartbeat-seconds",
        type=int,
        default=30,
        help="Emit unattended progress broadcasts at this interval while codex is still running",
    )
    parser.add_argument(
        "--prompt-note",
        default="",
        help="Optional extra instructions appended to each unattended codex invocation prompt",
    )
    parser.add_argument(
        "--max-rounds-per-invocation",
        type=int,
        default=0,
        help="Optional override for supervisor.max_rounds_per_invocation in the state file",
    )
    parser.add_argument(
        "--max-invocation-seconds",
        type=int,
        default=0,
        help="Optional hard timeout for one unattended codex invocation. Zero disables the timeout.",
    )
    parser.add_argument("--codex-bin", default="", help="Optional override for the codex binary path")
    parser.add_argument("--model", default="", help="Optional model override for codex exec")
    parser.add_argument(
        "--sandbox",
        choices=["read-only", "workspace-write", "danger-full-access"],
        default="",
        help="Optional sandbox override for new non-interactive codex sessions",
    )
    return parser.parse_args()


def lock_path_for(state_path: Path) -> Path:
    return state_path.parent / "supervisor.lock"


def acquire_lock(lock_path: Path) -> int:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    fd = os.open(str(lock_path), flags, 0o644)
    os.write(fd, ("%s\n" % os.getpid()).encode("utf-8"))
    return fd


def release_lock(fd: Optional[int], lock_path: Path) -> None:
    if fd is not None:
        os.close(fd)
    if lock_path.exists():
        lock_path.unlink()


def build_invocation_prompt(
    state: Dict[str, Any],
    state_path: Path,
    skill_path: Path,
    rounds_per_invocation: int,
    prompt_note: str,
) -> str:
    workspace_root = Path(state.get("workspace_root", ".")).resolve()
    skill_scripts = skill_path / "scripts"
    next_task = normalize_text(state.get("next_task", ""))
    lines = [
        "Use $strict-agent-loop at %s to continue the existing strict loop." % skill_path,
        "Target workspace: %s" % workspace_root,
        "Authoritative state file: %s" % state_path,
        "Operating mode: unattended",
        "This invocation must complete at most %s verified iterations unless the stop condition is met or a blocker is reached sooner."
        % rounds_per_invocation,
        "Startup rules for this invocation:",
        "- read the state file first",
        "- if TASK.md exists in the workspace, read it",
        "- read only the files directly needed for the next atomic round",
        "- do not start with a broad repo survey or a full skill-repository scan",
        "- read the skill protocol or recovery references only if the state is unclear or recovery is actually needed",
        "- if state.next_task is set, treat it as the authoritative starting task for this invocation",
        "Mandatory behavior for this invocation:",
        "- before each atomic round, append a round.started event by running %s"
        % (skill_scripts / "append_event.py"),
        "- the round.started event must include iteration, task, local_done_condition, global_stop_condition, and stop_after_this_round",
        "- because no human is present, the event log is the primary announcement channel",
        "- after each round, verify, record progress with %s, run %s, and refresh %s"
        % (
            skill_scripts / "update_state.py",
            skill_scripts / "check_stop.py",
            skill_scripts / "report_status.py",
        ),
        "- persist at least one verified round or a clear blocker before spending the whole invocation on analysis",
        "- if you need human input, record blocked status with a clear reason and exit this invocation",
        "- if you finish the round budget without meeting the stop condition, exit cleanly so the supervisor can resume",
        "Return a concise summary for this invocation only.",
    ]
    if next_task:
        lines.extend(["Current next_task from state:", next_task])
    if prompt_note.strip():
        lines.extend(["", "Additional operator note:", prompt_note.strip()])
    return "\n".join(lines) + "\n"


def emit_progress_broadcast(
    state_path: Path,
    state: Dict[str, Any],
    label: str,
    stop_report: Optional[Dict[str, Any]] = None,
    record_event: bool = False,
) -> None:
    actual_stop_report = stop_report or build_stop_report(state)
    report = build_status_report(state, stop_report=actual_stop_report)
    status_path = write_status_text(state, report)
    write_stop_report_file(state_path, state, actual_stop_report)
    write_run_summary(state_path, state, stop_report=actual_stop_report, report=report)
    append_status_snapshot(state_path, state, report, label=label, stop_report=actual_stop_report)
    save_state(state_path, state)
    print("%s" % label)
    print(render_status_text(report), end="")
    print("Status file: %s" % status_path)
    if record_event:
        append_event_record(
            state_path,
            state,
            "supervisor.broadcast",
            label,
            data={
                "progress_percent": report.get("progress_percent"),
                "iterations_completed": report.get("iterations_completed"),
                "estimated_remaining_human": report.get("estimated_remaining_human"),
                "recent_average_human": report.get("recent_average_human"),
            },
        )


def parse_event_line(raw_line: str) -> Optional[Dict[str, Any]]:
    stripped = raw_line.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


def build_exec_command(
    state: Dict[str, Any],
    state_path: Path,
    skill_path: Path,
    prompt_path: Path,
    output_path: Path,
    args: argparse.Namespace,
) -> List[str]:
    supervisor_state = state.get("supervisor", {})
    codex_bin = args.codex_bin or supervisor_state.get("codex_bin") or "codex"
    model = args.model or supervisor_state.get("model", "")
    sandbox = args.sandbox or supervisor_state.get("sandbox", "workspace-write")
    thread_id = normalize_text(supervisor_state.get("thread_id", ""))
    resume_existing_thread = bool(supervisor_state.get("resume_existing_thread", True))
    workspace_root = Path(state.get("workspace_root", ".")).resolve()

    if thread_id and resume_existing_thread:
        cmd = [codex_bin, "exec", "resume", "--json", "-o", str(output_path)]
        if model:
            cmd.extend(["-m", model])
        cmd.extend([thread_id, "-"])
        return cmd

    cmd = [
        codex_bin,
        "exec",
        "--json",
        "-o",
        str(output_path),
        "-s",
        sandbox,
        "-C",
        str(workspace_root),
        "--add-dir",
        str(skill_path),
        "-",
    ]
    if model:
        cmd.extend(["-m", model])
    return cmd


def run_codex_invocation(
    state_path: Path,
    skill_path: Path,
    args: argparse.Namespace,
) -> int:
    state = load_state(state_path)
    workspace_root = Path(state.get("workspace_root", ".")).resolve()
    supervisor_state = state.setdefault("supervisor", {})
    rounds_per_invocation = args.max_rounds_per_invocation or int(
        supervisor_state.get("max_rounds_per_invocation", 5)
    )
    invocation_index = int(supervisor_state.get("invocation_count", 0)) + 1
    supervisor_dir = Path(supervisor_state.get("log_dir", state_path.parent / "supervisor")).resolve()
    supervisor_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = supervisor_dir / ("invocation-%04d.prompt.txt" % invocation_index)
    jsonl_path = supervisor_dir / ("invocation-%04d.jsonl" % invocation_index)
    output_path = supervisor_dir / ("invocation-%04d.last.txt" % invocation_index)

    prompt = build_invocation_prompt(state, state_path, skill_path, rounds_per_invocation, args.prompt_note)
    prompt_path.write_text(prompt, encoding="utf-8")

    supervisor_state["invocation_count"] = invocation_index
    supervisor_state["last_invoked_at"] = utc_now()
    supervisor_state["last_prompt_path"] = str(prompt_path)
    supervisor_state["last_output_path"] = str(output_path)
    supervisor_state["last_jsonl_path"] = str(jsonl_path)
    append_event_record(
        state_path,
        state,
        "supervisor.invocation.started",
        "Started unattended codex invocation.",
        data={
            "invocation": invocation_index,
            "thread_id": supervisor_state.get("thread_id", ""),
            "round_budget": rounds_per_invocation,
        },
    )
    emit_progress_broadcast(
        state_path,
        state,
        "Supervisor starting invocation %04d" % invocation_index,
        record_event=False,
    )
    save_state(state_path, state)

    cmd = build_exec_command(state, state_path, skill_path, prompt_path, output_path, args)
    used_resume = "resume" in cmd[2:4] or "resume" in cmd
    process = subprocess.Popen(
        cmd,
        cwd=str(workspace_root),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdin is not None
    process.stdin.write(prompt)
    process.stdin.close()

    selector = selectors.DefaultSelector()
    assert process.stdout is not None
    selector.register(process.stdout, selectors.EVENT_READ)
    thread_id = normalize_text(supervisor_state.get("thread_id", ""))
    invocation_started_at = time.time()
    timed_out = False

    with jsonl_path.open("w", encoding="utf-8") as jsonl_file:
        while True:
            if args.max_invocation_seconds > 0:
                elapsed = time.time() - invocation_started_at
                if elapsed >= args.max_invocation_seconds:
                    timed_out = True
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    break
            events = selector.select(timeout=args.heartbeat_seconds)
            if not events:
                heartbeat_state = load_state(state_path)
                emit_progress_broadcast(
                    state_path,
                    heartbeat_state,
                    "Supervisor heartbeat: invocation %04d still running" % invocation_index,
                    record_event=False,
                )
                if process.poll() is not None:
                    break
                continue

            for key, _mask in events:
                line = key.fileobj.readline()
                if not line:
                    continue
                jsonl_file.write(line)
                parsed = parse_event_line(line)
                if parsed and parsed.get("type") == "thread.started":
                    thread_id = parsed.get("thread_id", thread_id)

            if process.poll() is not None:
                remaining = process.stdout.read()
                if remaining:
                    jsonl_file.write(remaining)
                    for raw_line in remaining.splitlines():
                        parsed = parse_event_line(raw_line)
                        if parsed and parsed.get("type") == "thread.started":
                            thread_id = parsed.get("thread_id", thread_id)
                break

    selector.close()
    exit_code = process.wait()
    if timed_out and exit_code == 0:
        exit_code = 124

    state = load_state(state_path)
    supervisor_state = state.setdefault("supervisor", {})
    supervisor_state["last_completed_at"] = utc_now()
    supervisor_state["last_exit_code"] = exit_code
    if thread_id:
        supervisor_state["thread_id"] = thread_id

    if exit_code == 0:
        supervisor_state["consecutive_failures"] = 0
        append_event_record(
            state_path,
            state,
            "supervisor.invocation.finished",
            "Unattended codex invocation finished successfully.",
            data={
                "invocation": invocation_index,
                "thread_id": supervisor_state.get("thread_id", ""),
                "exit_code": exit_code,
            },
        )
    else:
        supervisor_state["consecutive_failures"] = int(supervisor_state.get("consecutive_failures", 0)) + 1
        failure_message = "Unattended codex invocation exited with a non-zero status."
        if timed_out:
            failure_message = "Unattended codex invocation hit the configured timeout."
        append_event_record(
            state_path,
            state,
            "supervisor.invocation.failed",
            failure_message,
            data={
                "invocation": invocation_index,
                "thread_id": supervisor_state.get("thread_id", ""),
                "exit_code": exit_code,
                "consecutive_failures": supervisor_state.get("consecutive_failures", 0),
                "timed_out": timed_out,
            },
        )
        if used_resume and supervisor_state.get("thread_id"):
            supervisor_state["thread_id"] = ""
            append_event_record(
                state_path,
                state,
                "supervisor.thread.reset",
                "Cleared the stored codex thread id after a failed resume so the next cycle can recover from disk state.",
                data={"invocation": invocation_index},
            )

    save_state(state_path, state)
    return exit_code


def maybe_finalize_from_stop_report(state_path: Path, state: Dict[str, Any], stop_report: Dict[str, Any]) -> None:
    if stop_report.get("should_stop") and stop_report.get("success") and state.get("status") != "completed":
        state["status"] = "completed"
        clear_blocker(state)
        append_event_record(
            state_path,
            state,
            "loop.completed.by-supervisor",
            "Marked the loop completed after machine-checkable stop conditions passed.",
            data={
                "iteration": stop_report.get("iteration", 0),
                "passed_checks": stop_report.get("stop_checks", {}).get("passed_checks", 0),
                "total_checks": stop_report.get("stop_checks", {}).get("total_checks", 0),
            },
        )
        save_state(state_path, state)


def main() -> int:
    args = parse_args()
    state_path = Path(args.state).resolve()
    skill_path = Path(args.skill_path).resolve()
    if not state_path.exists():
        print("State file does not exist: %s" % state_path, file=sys.stderr)
        return 1
    if not skill_path.exists():
        print("Skill path does not exist: %s" % skill_path, file=sys.stderr)
        return 1

    state = load_state(state_path)
    if state.get("operating_mode") != "unattended":
        print(
            "The state file is in %s mode. Re-initialize it with --operating-mode unattended first."
            % state.get("operating_mode"),
            file=sys.stderr,
        )
        return 1

    lock_path = lock_path_for(state_path)
    lock_fd = None
    try:
        lock_fd = acquire_lock(lock_path)
    except FileExistsError:
        print("Another supervisor appears to be running: %s" % lock_path, file=sys.stderr)
        return 2

    try:
        for _cycle in range(args.max_cycles):
            state = load_state(state_path)
            stop_report = build_stop_report(state)
            maybe_finalize_from_stop_report(state_path, state, stop_report)
            state = load_state(state_path)
            stop_report = build_stop_report(state)
            emit_progress_broadcast(
                state_path,
                state,
                "Supervisor status check",
                stop_report=stop_report,
                record_event=False,
            )

            if stop_report.get("should_stop"):
                print(json.dumps(stop_report, indent=2, ensure_ascii=False))
                return 0 if stop_report.get("success") else 2

            exit_code = run_codex_invocation(state_path, skill_path, args)
            state = load_state(state_path)
            stop_report = build_stop_report(state)
            maybe_finalize_from_stop_report(state_path, state, stop_report)
            state = load_state(state_path)
            stop_report = build_stop_report(state)
            emit_progress_broadcast(
                state_path,
                state,
                "Supervisor completed an invocation",
                stop_report=stop_report,
                record_event=True,
            )
            save_state(state_path, state)

            if stop_report.get("should_stop"):
                print(json.dumps(stop_report, indent=2, ensure_ascii=False))
                return 0 if stop_report.get("success") else 2

            if exit_code != 0:
                supervisor_state = state.get("supervisor", {})
                max_failures = int(supervisor_state.get("max_consecutive_failures", 3))
                current_failures = int(supervisor_state.get("consecutive_failures", 0))
                if current_failures >= max_failures:
                    state["status"] = "failed"
                    set_blocker(
                        state,
                        "The unattended supervisor hit %s consecutive codex invocation failures."
                        % current_failures,
                        needs_human_input=True,
                    )
                    append_event_record(
                        state_path,
                        state,
                        "loop.failed.by-supervisor",
                        "Marked the unattended loop failed after too many codex invocation failures.",
                        data={
                            "consecutive_failures": current_failures,
                            "max_consecutive_failures": max_failures,
                        },
                    )
                    save_state(state_path, state)
                    print(json.dumps(build_stop_report(state), indent=2, ensure_ascii=False))
                    return 2

            if args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)

        state = load_state(state_path)
        state["status"] = "failed"
        set_blocker(
            state,
            "The unattended supervisor reached max_cycles=%s before the loop stopped." % args.max_cycles,
            needs_human_input=True,
        )
        append_event_record(
            state_path,
            state,
            "loop.failed.by-supervisor",
            "Marked the unattended loop failed after reaching the supervisor cycle limit.",
            data={"max_cycles": args.max_cycles},
        )
        save_state(state_path, state)
        print(json.dumps(build_stop_report(state), indent=2, ensure_ascii=False))
        return 2
    finally:
        release_lock(lock_fd, lock_path)


if __name__ == "__main__":
    raise SystemExit(main())
