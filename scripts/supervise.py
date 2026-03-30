#!/usr/bin/env python3

import argparse
import json
import os
import selectors
import signal
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

INTERRUPT_EXIT_CODE = 130
_INTERRUPT_STATE = {
    "requested": False,
    "signal_name": "",
}


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
        "--reasoning-effort",
        default="",
        choices=["", "low", "medium", "high", "xhigh"],
        help="Optional reasoning effort override for codex exec.",
    )
    parser.add_argument(
        "--sandbox",
        choices=["read-only", "workspace-write", "danger-full-access"],
        default="",
        help="Optional sandbox override for new non-interactive codex sessions",
    )
    return parser.parse_args()


def interrupt_requested() -> bool:
    return bool(_INTERRUPT_STATE.get("requested", False))


def current_signal_name() -> str:
    return _INTERRUPT_STATE.get("signal_name", "") or "SIGINT"


def request_interrupt(signum: int, _frame: Any) -> None:
    _INTERRUPT_STATE["requested"] = True
    try:
        _INTERRUPT_STATE["signal_name"] = signal.Signals(signum).name
    except Exception:
        _INTERRUPT_STATE["signal_name"] = str(signum)


def install_signal_handlers() -> Dict[int, Any]:
    previous_handlers = {}
    for handled_signal in [signal.SIGINT, signal.SIGTERM]:
        previous_handlers[handled_signal] = signal.getsignal(handled_signal)
        signal.signal(handled_signal, request_interrupt)
    return previous_handlers


def restore_signal_handlers(previous_handlers: Dict[int, Any]) -> None:
    for handled_signal, previous_handler in previous_handlers.items():
        signal.signal(handled_signal, previous_handler)


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
    sandbox_mode = normalize_text(state.get("supervisor", {}).get("sandbox", "workspace-write")) or "workspace-write"
    reasoning_effort = normalize_text(state.get("supervisor", {}).get("reasoning_effort", ""))
    resume_existing_thread = bool(state.get("supervisor", {}).get("resume_existing_thread", False))
    append_event_cmd = (
        "python {script} --state {state} --kind round.started --message "
        "\"<announcement>\" --data iteration=<n> --data task=\"<task>\" "
        "--data local_done_condition=\"<done>\" --data global_stop_condition=\"<global-stop>\" "
        "--data stop_after_this_round=\"<stop-after>\""
    ).format(script=skill_scripts / "append_event.py", state=state_path)
    update_state_cmd = (
        "python {script} --state {state} --task \"<task>\" --local-done-condition \"<done>\" "
        "--result-summary \"<result>\" --verification-summary \"<verification>\" "
        "--announcement \"<announcement>\" --next-task \"<next-task>\" "
        "[--evidence <path>] [--artifact <path>] [--stop-met]"
    ).format(script=skill_scripts / "update_state.py", state=state_path)
    check_stop_cmd = "python %s --state %s" % (skill_scripts / "check_stop.py", state_path)
    report_status_cmd = "python %s --state %s --label unattended.round" % (
        skill_scripts / "report_status.py",
        state_path,
    )
    json_get_cmd = "python %s %s counters.iteration status next_task" % (
        skill_scripts / "json_get.py",
        state_path,
    )
    lines = [
        "Continue the existing strict-agent-loop task using the runtime at %s." % skill_path,
        "Target workspace: %s" % workspace_root,
        "Authoritative state file: %s" % state_path,
        "Keep actual work artifacts under the workspace root (for example src/, docs/, or output/).",
        "Keep loop bookkeeping under %s only; do not treat that task directory as the deliverable output area unless the task explicitly says so."
        % state_path.parent,
        "Use the global completed-round count from state.counters.iteration.",
        "Use the next round number as state.counters.iteration + 1; do not invent a separate per-invocation iteration counter.",
        "If you inspect the JSON with ad-hoc scripts, read nested keys exactly: state['counters']['iteration'], state['status'], and state['next_task'].",
        "Operating mode: unattended",
        "Sandbox mode for this invocation: %s" % sandbox_mode,
        "Reasoning effort for this invocation: %s" % (reasoning_effort or "config default"),
        "Thread resume policy: %s"
        % (
            "resume the same Codex thread when available"
            if resume_existing_thread
            else "start a fresh Codex invocation and recover strictly from disk artifacts"
        ),
        "This invocation must complete at most %s verified iterations unless the stop condition is met or a blocker is reached sooner."
        % rounds_per_invocation,
        "Startup rules for this invocation:",
        "- read the state file first",
        "- if TASK.md exists in the workspace, read it",
        "- read only the files directly needed for the next atomic round",
        "- do not start with a broad repo survey or a full skill-repository scan",
        "- do not open SKILL.md or the reference docs unless a required runtime command fails or the prompt conflicts with disk state",
        "- this invocation is not read-only unless a real write command fails; do not invent a sandbox blocker without an actual failed write attempt",
        "- inspect the task-local artifacts directly relevant to the next round before trusting a stale plan line",
        "- if state.next_task disagrees with disk reality, reconcile in favor of the actual workspace artifacts and persist the corrected plan",
        "- if state.next_task is accurate, use it as the starting task for this invocation",
        "- when thread resume is disabled, do not assume any prior conversational memory beyond disk artifacts",
        "- after the initial recovery read, do not keep re-reading full TASK.md or full state.json every round unless recovery is actually needed; use the freshly persisted state plus minimal disk checks such as the sequence tail and report existence",
        "- prefer targeted reads over full-file dumps; only inspect the smallest artifact slice needed to decide the next atomic step",
        "- once state, TASK.md, and the directly relevant artifacts are clear, start the first round immediately",
        "Mandatory behavior for this invocation:",
        "- do not open an interactive shell, REPL, here-doc session, or long-lived helper process; every work, verification, and persistence action must be a direct one-shot command so the supervisor can relay it",
        "- do not hide multiple substeps inside a single `bash` session; each atomic action and each bookkeeping command must stay externally visible as its own command execution",
        "- run commands strictly sequentially; never start a second shell command before the previous command has completed and you have inspected its exit code",
        "- the required command order inside one round is: inspect relevant artifact -> append_event.py -> one work command -> verifier -> update_state.py -> check_stop.py -> report_status.py",
        "- never overlap update_state.py, check_stop.py, report_status.py, or any other bookkeeping commands",
        "- before each atomic round, emit a short visible progress message in the Codex output that includes iteration, completed rounds, the atomic task, the local done condition, and when this loop may stop",
        "- before each atomic round, append a round.started event by running %s"
        % (skill_scripts / "append_event.py"),
        "- the round.started event must include iteration, task, local_done_condition, global_stop_condition, and stop_after_this_round",
        "- the event log is mandatory, but the visible Codex output must also stay informative because operators may watch the supervisor stdout",
        "- after each round, verify, record progress with %s, run %s, and refresh %s"
        % (
            skill_scripts / "update_state.py",
            skill_scripts / "check_stop.py",
            skill_scripts / "report_status.py",
        ),
        "- after each verified round, emit a short visible progress update with the new iteration count, recent status, and next task",
        "- persist at least one verified round or a clear blocker before spending the whole invocation on analysis",
        "- if you need human input, record blocked status with a clear reason and exit this invocation",
        "- if you finish the round budget without meeting the stop condition, exit cleanly so the supervisor can resume",
        "Use these command shapes directly instead of spending time on `--help` lookups unless a command unexpectedly fails:",
        "- targeted state read: %s" % json_get_cmd,
        "- round announcement: %s" % append_event_cmd,
        "- verified update: %s" % update_state_cmd,
        "- stop check: %s" % check_stop_cmd,
        "- status refresh: %s" % report_status_cmd,
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
    persist_state: bool = True,
) -> None:
    actual_stop_report = stop_report or build_stop_report(state, state_path=state_path)
    report = build_status_report(state, stop_report=actual_stop_report)
    status_path = write_status_text(state, report)
    write_stop_report_file(state_path, state, actual_stop_report)
    write_run_summary(state_path, state, stop_report=actual_stop_report, report=report)
    append_status_snapshot(state_path, state, report, label=label, stop_report=actual_stop_report)
    if persist_state:
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
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def normalize_multiline_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def print_prefixed_block(prefix: str, text: str) -> None:
    normalized = normalize_multiline_text(text)
    if not normalized:
        return
    lines = normalized.splitlines()
    print("%s %s" % (prefix, lines[0]))
    for line in lines[1:]:
        print("  %s" % line)


def trim_block(value: str, max_chars: int = 600) -> str:
    normalized = normalize_multiline_text(value)
    if len(normalized) <= max_chars:
        return normalized
    return normalized[-max_chars:]


def build_progress_signature(state: Dict[str, Any]) -> tuple:
    counters = state.get("counters", {})
    return (
        int(counters.get("iteration", 0)),
        int(counters.get("no_progress_rounds", 0)),
        int(counters.get("recovery_count", 0)),
        normalize_text(state.get("status", "")),
        normalize_text(state.get("next_task", "")),
    )


def should_emit_live_progress_after_event(parsed: Dict[str, Any]) -> bool:
    if parsed.get("type") != "item.completed":
        return False
    item = parsed.get("item", {})
    if not isinstance(item, dict):
        return False
    if item.get("type") != "command_execution":
        return False
    if item.get("exit_code") != 0:
        return False
    command = normalize_text(item.get("command", ""))
    return any(
        marker in command
        for marker in [
            " update_state.py",
            "/update_state.py",
            " report_status.py",
            "/report_status.py",
        ]
    )


def command_failed_due_to_readonly_filesystem(parsed: Dict[str, Any]) -> bool:
    if parsed.get("type") != "item.completed":
        return False
    item = parsed.get("item", {})
    if not isinstance(item, dict):
        return False
    if item.get("type") != "command_execution":
        return False
    if item.get("exit_code") in {None, 0}:
        return False
    output = normalize_multiline_text(item.get("aggregated_output", "")).lower()
    return "read-only file system" in output or "errno 30" in output


def emit_inner_codex_event(parsed: Dict[str, Any]) -> None:
    event_type = parsed.get("type", "")
    if event_type not in {"item.started", "item.completed", "error"}:
        return

    if event_type == "error":
        print_prefixed_block("Inner Codex error:", parsed.get("message", "Unknown error"))
        return

    item = parsed.get("item", {})
    if not isinstance(item, dict):
        return

    item_type = item.get("type", "")
    if item_type == "agent_message" and event_type == "item.completed":
        print_prefixed_block("Inner Codex:", item.get("text", ""))
        return

    if item_type != "command_execution":
        return

    command = normalize_text(item.get("command", ""))
    if event_type == "item.started":
        if command:
            print("Inner command started: %s" % command)
        return

    exit_code = item.get("exit_code")
    if command:
        print("Inner command completed (exit=%s): %s" % (exit_code, command))
    aggregated_output = trim_block(item.get("aggregated_output", ""))
    if aggregated_output and exit_code not in {None, 0}:
        print_prefixed_block("Inner command output:", aggregated_output)


def command_event_details(parsed: Dict[str, Any]) -> Optional[Dict[str, str]]:
    event_type = parsed.get("type", "")
    if event_type not in {"item.started", "item.completed"}:
        return None
    item = parsed.get("item", {})
    if not isinstance(item, dict):
        return None
    if item.get("type") != "command_execution":
        return None
    command = normalize_text(item.get("command", ""))
    if not command:
        return None
    return {
        "event_type": event_type,
        "command": command,
    }


def update_active_commands(
    parsed: Dict[str, Any],
    active_commands: List[str],
    parallel_samples: List[Dict[str, Any]],
) -> bool:
    details = command_event_details(parsed)
    if not details:
        return False

    if details["event_type"] == "item.started":
        if active_commands:
            sample = {
                "started_command": details["command"],
                "already_running": list(active_commands),
            }
            parallel_samples.append(sample)
            print_prefixed_block(
                "Supervisor warning:",
                "Inner Codex started an overlapping command. strict-agent-loop commands must be serialized.",
            )
            print_prefixed_block("Supervisor warning detail:", json.dumps(sample, ensure_ascii=False, indent=2))
            active_commands.append(details["command"])
            return True
        active_commands.append(details["command"])
        return False

    try:
        active_commands.remove(details["command"])
    except ValueError:
        if active_commands:
            active_commands.pop(0)
    return False


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
    reasoning_effort = args.reasoning_effort or supervisor_state.get("reasoning_effort", "")
    sandbox = args.sandbox or supervisor_state.get("sandbox", "workspace-write")
    thread_id = normalize_text(supervisor_state.get("thread_id", ""))
    resume_existing_thread = bool(supervisor_state.get("resume_existing_thread", True))
    workspace_root = Path(state.get("workspace_root", ".")).resolve()

    if thread_id and resume_existing_thread:
        cmd = [
            codex_bin,
            "exec",
            "resume",
            "--json",
            "--skip-git-repo-check",
            "-o",
            str(output_path),
        ]
        if model:
            cmd.extend(["-m", model])
        if reasoning_effort:
            cmd.extend(["-c", 'model_reasoning_effort="%s"' % reasoning_effort])
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
        "--skip-git-repo-check",
        "-C",
        str(workspace_root),
        "--add-dir",
        str(skill_path),
        "-",
    ]
    if model:
        cmd.extend(["-m", model])
    if reasoning_effort:
        cmd.extend(["-c", 'model_reasoning_effort="%s"' % reasoning_effort])
    return cmd


def run_codex_invocation(
    state_path: Path,
    skill_path: Path,
    args: argparse.Namespace,
) -> Dict[str, Any]:
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
    interrupted = False
    initial_progress_signature = build_progress_signature(state)
    observed_progress_signature = initial_progress_signature
    readonly_write_failure_detected = False
    active_commands = []
    parallel_command_samples = []

    with jsonl_path.open("w", encoding="utf-8") as jsonl_file:
        while True:
            if interrupt_requested():
                interrupted = True
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                break
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
                heartbeat_signature = build_progress_signature(heartbeat_state)
                label = "Supervisor heartbeat: invocation %04d still running" % invocation_index
                if heartbeat_signature != observed_progress_signature:
                    label = "Supervisor observed new persisted progress during invocation %04d" % invocation_index
                    observed_progress_signature = heartbeat_signature
                emit_progress_broadcast(
                    state_path,
                    heartbeat_state,
                    label,
                    record_event=False,
                    persist_state=False,
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
                if parsed:
                    emit_inner_codex_event(parsed)
                    update_active_commands(parsed, active_commands, parallel_command_samples)
                    if parsed.get("type") == "thread.started":
                        thread_id = parsed.get("thread_id", thread_id)
                    if command_failed_due_to_readonly_filesystem(parsed):
                        readonly_write_failure_detected = True
                    if should_emit_live_progress_after_event(parsed):
                        live_state = load_state(state_path)
                        live_signature = build_progress_signature(live_state)
                        if live_signature != observed_progress_signature:
                            emit_progress_broadcast(
                                state_path,
                                live_state,
                                "Supervisor observed verified progress during invocation %04d" % invocation_index,
                                record_event=False,
                                persist_state=False,
                            )
                            observed_progress_signature = live_signature

            if process.poll() is not None:
                remaining = process.stdout.read()
                if remaining:
                    jsonl_file.write(remaining)
                    for raw_line in remaining.splitlines():
                        parsed = parse_event_line(raw_line)
                        if parsed:
                            emit_inner_codex_event(parsed)
                            update_active_commands(parsed, active_commands, parallel_command_samples)
                            if parsed.get("type") == "thread.started":
                                thread_id = parsed.get("thread_id", thread_id)
                            if command_failed_due_to_readonly_filesystem(parsed):
                                readonly_write_failure_detected = True
                            if should_emit_live_progress_after_event(parsed):
                                live_state = load_state(state_path)
                                live_signature = build_progress_signature(live_state)
                                if live_signature != observed_progress_signature:
                                    emit_progress_broadcast(
                                        state_path,
                                        live_state,
                                        "Supervisor observed verified progress during invocation %04d"
                                        % invocation_index,
                                        record_event=False,
                                        persist_state=False,
                                    )
                                    observed_progress_signature = live_signature
                break

    selector.close()
    exit_code = process.wait()
    if interrupted:
        exit_code = INTERRUPT_EXIT_CODE
    if timed_out and exit_code == 0:
        exit_code = 124

    state = load_state(state_path)
    supervisor_state = state.setdefault("supervisor", {})
    final_progress_signature = build_progress_signature(state)
    progress_made_during_invocation = final_progress_signature != initial_progress_signature
    supervisor_state["last_completed_at"] = utc_now()
    supervisor_state["last_exit_code"] = exit_code
    if thread_id:
        supervisor_state["thread_id"] = thread_id
    if readonly_write_failure_detected:
        supervisor_state["thread_id"] = ""
        supervisor_state["resume_existing_thread"] = False
        append_event_record(
            state_path,
            state,
            "supervisor.resume.disabled",
            "Disabled Codex thread resume after inner write commands hit a read-only filesystem error.",
            data={"invocation": invocation_index},
        )
    if parallel_command_samples:
        append_event_record(
            state_path,
            state,
            "supervisor.protocol.parallel-commands",
            "Detected overlapping inner command executions during an unattended invocation.",
            data={
                "invocation": invocation_index,
                "samples": parallel_command_samples[:5],
            },
        )

    if interrupted:
        append_event_record(
            state_path,
            state,
            "supervisor.invocation.interrupted",
            "Unattended codex invocation was interrupted by an operator signal.",
            data={
                "invocation": invocation_index,
                "thread_id": supervisor_state.get("thread_id", ""),
                "signal": current_signal_name(),
                "exit_code": exit_code,
            },
        )
    elif exit_code == 0:
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
        if progress_made_during_invocation:
            supervisor_state["consecutive_failures"] = 0
            progress_message = "Unattended codex invocation exited non-zero after persisting verified progress."
            if timed_out:
                progress_message = (
                    "Unattended codex invocation hit the configured timeout after persisting verified progress."
                )
            append_event_record(
                state_path,
                state,
                "supervisor.invocation.progressed",
                progress_message,
                data={
                    "invocation": invocation_index,
                    "thread_id": supervisor_state.get("thread_id", ""),
                    "exit_code": exit_code,
                    "timed_out": timed_out,
                    "initial_progress_signature": initial_progress_signature,
                    "final_progress_signature": final_progress_signature,
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
    return {
        "exit_code": exit_code,
        "timed_out": timed_out,
        "interrupted": interrupted,
        "progressed": progress_made_during_invocation,
    }


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

    previous_handlers = install_signal_handlers()
    try:
        for _cycle in range(args.max_cycles):
            if interrupt_requested():
                print("Supervisor interrupted by %s. State was saved for later recovery." % current_signal_name())
                return INTERRUPT_EXIT_CODE
            state = load_state(state_path)
            stop_report = build_stop_report(state, state_path=state_path)
            maybe_finalize_from_stop_report(state_path, state, stop_report)
            state = load_state(state_path)
            stop_report = build_stop_report(state, state_path=state_path)
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

            result = run_codex_invocation(state_path, skill_path, args)
            exit_code = int(result.get("exit_code", 1))
            state = load_state(state_path)
            stop_report = build_stop_report(state, state_path=state_path)
            maybe_finalize_from_stop_report(state_path, state, stop_report)
            state = load_state(state_path)
            stop_report = build_stop_report(state, state_path=state_path)
            emit_progress_broadcast(
                state_path,
                state,
                "Supervisor completed an invocation",
                stop_report=stop_report,
                record_event=True,
            )
            save_state(state_path, state)

            if result.get("interrupted"):
                print("Supervisor interrupted by %s. State was saved for later recovery." % current_signal_name())
                return INTERRUPT_EXIT_CODE

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
                    print(json.dumps(build_stop_report(state, state_path=state_path), indent=2, ensure_ascii=False))
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
        print(json.dumps(build_stop_report(state, state_path=state_path), indent=2, ensure_ascii=False))
        return 2
    finally:
        release_lock(lock_fd, lock_path)
        restore_signal_handlers(previous_handlers)


if __name__ == "__main__":
    raise SystemExit(main())
