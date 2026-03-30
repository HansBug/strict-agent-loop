#!/usr/bin/env python3

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

STATE_SCHEMA_VERSION = 3
DEFAULT_MAX_CONTEXT_CHARS = 12000
DEFAULT_MAX_ARCHIVE_CHARS = 8000
DEFAULT_MANAGER_DIR_NAME = ".codex-loop"
DEFAULT_TASKS_DIR_NAME = "tasks"
DEFAULT_REGISTRY_FILENAME = "registry.json"
LEGACY_DEFAULT_STATE_RELATIVE_PATH = ".codex-loop/state.json"


def slugify_task_component(value: str, fallback: str = "task") -> str:
    lowered = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", lowered)
    normalized = normalized.strip("-")
    return normalized or fallback


def build_generated_task_id(goal: str, timestamp: str) -> str:
    stamp = re.sub(r"[^0-9]", "", timestamp)[:14]
    if not stamp:
        stamp = "task"
    slug = slugify_task_component(goal, fallback="task")
    return "%s-%s" % (stamp, slug[:32])


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_state(path: Union[str, Path]) -> Dict[str, Any]:
    state_path = Path(path).resolve()
    with state_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_state(path: Union[str, Path], state: Dict[str, Any]) -> None:
    state_path = Path(path).resolve()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = utc_now()
    with state_path.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")
    update_registry_from_state(state_path, state)


def normalize_text(value: str) -> str:
    return " ".join(value.split())


def format_list(items: Iterable[str]) -> List[str]:
    return [normalize_text(item) for item in items if item and item.strip()]


def state_dir_for(path: Union[str, Path]) -> Path:
    return Path(path).resolve().parent


def default_manager_dir_for_workspace(workspace_root: Union[str, Path]) -> Path:
    return Path(workspace_root).resolve() / DEFAULT_MANAGER_DIR_NAME


def default_registry_path_for_workspace(workspace_root: Union[str, Path]) -> Path:
    return default_manager_dir_for_workspace(workspace_root) / DEFAULT_REGISTRY_FILENAME


def default_task_root_for_workspace(workspace_root: Union[str, Path], task_id: str) -> Path:
    return default_manager_dir_for_workspace(workspace_root) / DEFAULT_TASKS_DIR_NAME / slugify_task_component(task_id)


def default_state_path_for_workspace(workspace_root: Union[str, Path], task_id: str) -> Path:
    return default_task_root_for_workspace(workspace_root, task_id) / "state.json"


def legacy_default_state_path_for_workspace(workspace_root: Union[str, Path]) -> Path:
    return Path(workspace_root).resolve() / LEGACY_DEFAULT_STATE_RELATIVE_PATH


def default_event_log_path(path: Union[str, Path]) -> Path:
    return state_dir_for(path) / "events.jsonl"


def default_iteration_log_path(path: Union[str, Path]) -> Path:
    return state_dir_for(path) / "iterations.jsonl"


def default_status_history_path(path: Union[str, Path]) -> Path:
    return state_dir_for(path) / "status-history.jsonl"


def default_round_summary_dir(path: Union[str, Path]) -> Path:
    return state_dir_for(path) / "rounds"


def default_status_text_path(path: Union[str, Path]) -> Path:
    return state_dir_for(path) / "latest-status.txt"


def default_stop_report_path(path: Union[str, Path]) -> Path:
    return state_dir_for(path) / "latest-stop-report.json"


def default_run_summary_path(path: Union[str, Path]) -> Path:
    return state_dir_for(path) / "run-summary.md"


def default_supervisor_dir(path: Union[str, Path]) -> Path:
    return state_dir_for(path) / "supervisor"


def parse_text_pattern_spec(raw_value: str) -> Dict[str, str]:
    if "::" not in raw_value:
        raise ValueError("Text pattern checks must use the format '<path>::<pattern>'.")
    path_part, pattern_part = raw_value.split("::", 1)
    path_part = normalize_text(path_part)
    pattern_part = pattern_part.strip()
    if not path_part or not pattern_part:
        raise ValueError("Text pattern checks require both a path and a pattern.")
    return {
        "path": path_part,
        "pattern": pattern_part,
        "description": "%s contains %s" % (path_part, pattern_part),
    }


def normalize_stop_commands(stop_commands: Iterable[str]) -> List[Dict[str, Any]]:
    checks = []
    for raw_command in stop_commands:
        command = raw_command.strip()
        if not command:
            continue
        checks.append(
            {
                "command": command,
                "cwd": ".",
                "timeout_seconds": 900,
                "description": command,
            }
        )
    return checks


def normalize_required_paths(required_paths: Iterable[str]) -> List[Dict[str, str]]:
    checks = []
    for raw_path in required_paths:
        path_value = normalize_text(raw_path)
        if not path_value:
            continue
        checks.append(
            {
                "path": path_value,
                "description": "%s exists" % path_value,
            }
        )
    return checks


def normalize_text_patterns(patterns: Iterable[Union[str, Dict[str, str]]]) -> List[Dict[str, str]]:
    checks = []
    for raw_pattern in patterns:
        if isinstance(raw_pattern, dict):
            path_value = normalize_text(raw_pattern.get("path", ""))
            pattern_value = raw_pattern.get("pattern", "").strip()
            description = normalize_text(raw_pattern.get("description", ""))
            if path_value and pattern_value:
                checks.append(
                    {
                        "path": path_value,
                        "pattern": pattern_value,
                        "description": description or "%s contains %s" % (path_value, pattern_value),
                    }
                )
            continue
        checks.append(parse_text_pattern_spec(raw_pattern))
    return checks


def ensure_log_directories(state: Dict[str, Any]) -> None:
    logging_state = state.setdefault("logging", {})
    for key in [
        "event_log_path",
        "iteration_log_path",
        "status_history_path",
        "status_text_path",
        "stop_report_path",
        "run_summary_path",
    ]:
        path_value = logging_state.get(key)
        if path_value:
            Path(path_value).resolve().parent.mkdir(parents=True, exist_ok=True)
    round_summary_dir = logging_state.get("round_summary_dir")
    if round_summary_dir:
        Path(round_summary_dir).resolve().mkdir(parents=True, exist_ok=True)
    supervisor_state = state.setdefault("supervisor", {})
    supervisor_dir = supervisor_state.get("log_dir")
    if supervisor_dir:
        Path(supervisor_dir).resolve().mkdir(parents=True, exist_ok=True)
    task_state = state.setdefault("task", {})
    manager_dir = task_state.get("manager_dir")
    if manager_dir:
        Path(manager_dir).resolve().mkdir(parents=True, exist_ok=True)


def infer_task_id_from_state_path(state_path: Union[str, Path]) -> str:
    resolved_state_path = Path(state_path).resolve()
    if resolved_state_path.parent.parent.name == DEFAULT_TASKS_DIR_NAME:
        return slugify_task_component(resolved_state_path.parent.name)
    if resolved_state_path.parent.name == DEFAULT_MANAGER_DIR_NAME:
        return "default"
    return slugify_task_component(resolved_state_path.parent.name or "default", fallback="default")


def registry_path_for_state(state_path: Union[str, Path], state: Optional[Dict[str, Any]] = None) -> Path:
    if state:
        manager_dir = normalize_text(state.get("task", {}).get("manager_dir", ""))
        if manager_dir:
            return Path(manager_dir).resolve() / DEFAULT_REGISTRY_FILENAME
        workspace_root = normalize_text(state.get("workspace_root", ""))
        if workspace_root:
            return default_registry_path_for_workspace(workspace_root)
    resolved_state_path = Path(state_path).resolve()
    if resolved_state_path.parent.parent.name == DEFAULT_TASKS_DIR_NAME:
        return resolved_state_path.parent.parent.parent / DEFAULT_REGISTRY_FILENAME
    if resolved_state_path.parent.name == DEFAULT_MANAGER_DIR_NAME:
        return resolved_state_path.parent / DEFAULT_REGISTRY_FILENAME
    return resolved_state_path.parent / DEFAULT_REGISTRY_FILENAME


def load_registry(path: Union[str, Path]) -> Dict[str, Any]:
    registry_path = Path(path).resolve()
    if not registry_path.exists():
        return {
            "schema_version": 1,
            "updated_at": "",
            "tasks": {},
        }
    with registry_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_registry(path: Union[str, Path], registry: Dict[str, Any]) -> None:
    registry_path = Path(path).resolve()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry["updated_at"] = utc_now()
    with registry_path.open("w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
        f.write("\n")


def build_registry_entry(state_path: Union[str, Path], state: Dict[str, Any]) -> Dict[str, Any]:
    task_state = state.get("task", {})
    logging_state = state.get("logging", {})
    blocker_state = state.get("blocker", {})
    return {
        "id": normalize_text(task_state.get("id", "")) or infer_task_id_from_state_path(state_path),
        "state_path": str(Path(state_path).resolve()),
        "task_root_dir": normalize_text(task_state.get("root_dir", "")) or str(state_dir_for(state_path)),
        "manager_dir": normalize_text(task_state.get("manager_dir", "")),
        "goal": normalize_text(state.get("goal", "")),
        "operating_mode": normalize_text(state.get("operating_mode", "")),
        "status": normalize_text(state.get("status", "")),
        "workspace_root": normalize_text(state.get("workspace_root", "")),
        "created_at": state.get("created_at", ""),
        "updated_at": state.get("updated_at", ""),
        "iteration": int(state.get("counters", {}).get("iteration", 0)),
        "next_task": normalize_text(state.get("next_task", "")),
        "last_event_at": logging_state.get("last_event_at", ""),
        "latest_status_path": normalize_text(logging_state.get("status_text_path", "")),
        "latest_stop_report_path": normalize_text(logging_state.get("stop_report_path", "")),
        "run_summary_path": normalize_text(logging_state.get("run_summary_path", "")),
        "needs_human_input": bool(blocker_state.get("needs_human_input", False)),
        "blocker_reason": normalize_text(blocker_state.get("reason", "")),
    }


def update_registry_from_state(state_path: Union[str, Path], state: Dict[str, Any]) -> None:
    registry_path = registry_path_for_state(state_path, state)
    registry = load_registry(registry_path)
    tasks = registry.setdefault("tasks", {})
    entry = build_registry_entry(state_path, state)
    tasks[entry["id"]] = entry
    save_registry(registry_path, registry)


def build_state(
    state_path: Union[str, Path],
    task_id: str,
    goal: str,
    global_stop_condition: str,
    workspace_root: Union[str, Path],
    success_evidence: List[str],
    blocker_definition: str,
    max_iterations: int,
    max_no_progress_rounds: int,
    max_context_chars: int,
    executor_agent_id: str = "",
    operating_mode: str = "interactive",
    stop_commands: Optional[List[str]] = None,
    required_paths: Optional[List[str]] = None,
    text_patterns: Optional[List[Union[str, Dict[str, str]]]] = None,
    event_log_path: str = "",
    round_summary_dir: str = "",
    supervisor_codex_bin: str = "codex",
    supervisor_model: str = "",
    supervisor_reasoning_effort: str = "",
    supervisor_sandbox: str = "workspace-write",
    supervisor_resume_existing_thread: bool = False,
    supervisor_max_rounds_per_invocation: int = 5,
    supervisor_max_consecutive_failures: int = 3,
    next_task: str = "",
) -> Dict[str, Any]:
    now = utc_now()
    resolved_state_path = Path(state_path).resolve()
    resolved_workspace = Path(workspace_root).resolve()
    normalized_task_id = slugify_task_component(task_id, fallback="default")
    resolved_event_log_path = (
        Path(event_log_path).resolve() if event_log_path else default_event_log_path(resolved_state_path)
    )
    resolved_round_summary_dir = (
        Path(round_summary_dir).resolve()
        if round_summary_dir
        else default_round_summary_dir(resolved_state_path)
    )

    state = {
        "schema_version": STATE_SCHEMA_VERSION,
        "skill_name": "strict-agent-loop",
        "created_at": now,
        "updated_at": now,
        "task": {
            "id": normalized_task_id,
            "root_dir": str(resolved_state_path.parent),
            "manager_dir": str(default_manager_dir_for_workspace(resolved_workspace)),
        },
        "goal": normalize_text(goal),
        "global_stop_condition": normalize_text(global_stop_condition),
        "workspace_root": str(resolved_workspace),
        "success_evidence": format_list(success_evidence),
        "blocker_definition": normalize_text(blocker_definition),
        "operating_mode": operating_mode,
        "status": "running",
        "limits": {
            "max_iterations": max_iterations,
            "max_no_progress_rounds": max_no_progress_rounds,
            "max_context_chars": max_context_chars,
        },
        "counters": {
            "iteration": 0,
            "no_progress_rounds": 0,
            "recovery_count": 0,
        },
        "agent": {
            "executor_id": normalize_text(executor_agent_id),
            "spawned_from_current_context": False,
        },
        "logging": {
            "event_log_path": str(resolved_event_log_path),
            "iteration_log_path": str(default_iteration_log_path(resolved_state_path)),
            "status_history_path": str(default_status_history_path(resolved_state_path)),
            "round_summary_dir": str(resolved_round_summary_dir),
            "status_text_path": str(default_status_text_path(resolved_state_path)),
            "stop_report_path": str(default_stop_report_path(resolved_state_path)),
            "run_summary_path": str(default_run_summary_path(resolved_state_path)),
            "events_written": 0,
            "iterations_persisted": 0,
            "status_snapshots_written": 0,
            "last_event_at": "",
            "last_iteration_at": "",
            "last_status_at": "",
            "last_round_summary_path": "",
            "last_stop_report_at": "",
            "last_run_summary_at": "",
        },
        "stop_checks": {
            "commands": normalize_stop_commands(stop_commands or []),
            "paths_exist": normalize_required_paths(required_paths or []),
            "text_patterns": normalize_text_patterns(text_patterns or []),
        },
        "supervisor": {
            "enabled": operating_mode == "unattended",
            "codex_bin": normalize_text(supervisor_codex_bin) or "codex",
            "model": normalize_text(supervisor_model),
            "reasoning_effort": normalize_text(supervisor_reasoning_effort),
            "sandbox": normalize_text(supervisor_sandbox) or "workspace-write",
            "thread_id": "",
            "resume_existing_thread": bool(supervisor_resume_existing_thread),
            "max_rounds_per_invocation": supervisor_max_rounds_per_invocation,
            "max_consecutive_failures": supervisor_max_consecutive_failures,
            "invocation_count": 0,
            "consecutive_failures": 0,
            "last_invoked_at": "",
            "last_completed_at": "",
            "last_exit_code": None,
            "last_prompt_path": "",
            "last_output_path": "",
            "last_jsonl_path": "",
            "log_dir": str(default_supervisor_dir(resolved_state_path)),
        },
        "blocker": {
            "needs_human_input": False,
            "reason": "",
            "updated_at": "",
        },
        "next_task": normalize_text(next_task),
        "context_snapshot": "",
        "archive_summary": "",
        "history": [],
    }
    ensure_log_directories(state)
    state["context_snapshot"] = build_context_snapshot(state)
    return state


def summarize_entry(entry: Dict[str, Any]) -> str:
    task = normalize_text(entry.get("task", ""))
    result_summary = normalize_text(entry.get("result_summary", ""))
    verification = normalize_text(entry.get("verification_summary", ""))
    stop_flag = "yes" if entry.get("stop_condition_met") else "no"
    return (
        "Iter %s: task=%s; result=%s; verified=%s; stop_met=%s"
        % (entry.get("iteration", "?"), task, result_summary, verification, stop_flag)
    )


def build_context_snapshot(state: Dict[str, Any], keep_last: int = 5) -> str:
    history = state.get("history", [])
    recent = history[-keep_last:]
    task_state = state.get("task", {})
    lines = [
        "Task id: %s" % normalize_text(task_state.get("id", "")),
        "Task root: %s" % normalize_text(task_state.get("root_dir", "")),
        "Manager dir: %s" % normalize_text(task_state.get("manager_dir", "")),
        "Goal: %s" % normalize_text(state.get("goal", "")),
        "Operating mode: %s" % normalize_text(state.get("operating_mode", "")),
        "Global stop condition: %s" % normalize_text(state.get("global_stop_condition", "")),
        "Workspace root: %s" % normalize_text(state.get("workspace_root", "")),
        "Status: %s" % normalize_text(state.get("status", "")),
        "Total recorded iterations: %s" % state.get("counters", {}).get("iteration", 0),
        "No-progress rounds: %s" % state.get("counters", {}).get("no_progress_rounds", 0),
    ]
    success_evidence = format_list(state.get("success_evidence", []))
    if success_evidence:
        lines.append("Success evidence: %s" % "; ".join(success_evidence))
    blocker_state = state.get("blocker", {})
    blocker_reason = normalize_text(blocker_state.get("reason", ""))
    if blocker_reason:
        lines.append(
            "Blocker: %s (needs_human_input=%s)"
            % (blocker_reason, blocker_state.get("needs_human_input", False))
        )
    stop_checks = state.get("stop_checks", {})
    lines.append(
        "Stop checks: commands=%s, paths_exist=%s, text_patterns=%s"
        % (
            len(stop_checks.get("commands", [])),
            len(stop_checks.get("paths_exist", [])),
            len(stop_checks.get("text_patterns", [])),
        )
    )
    logging_state = state.get("logging", {})
    event_log_path = normalize_text(logging_state.get("event_log_path", ""))
    if event_log_path:
        lines.append("Event log: %s" % event_log_path)
    iteration_log_path = normalize_text(logging_state.get("iteration_log_path", ""))
    if iteration_log_path:
        lines.append("Full iteration ledger: %s" % iteration_log_path)
    status_history_path = normalize_text(logging_state.get("status_history_path", ""))
    if status_history_path:
        lines.append("Status history: %s" % status_history_path)
    supervisor_state = state.get("supervisor", {})
    thread_id = normalize_text(supervisor_state.get("thread_id", ""))
    if thread_id:
        lines.append(
            "Supervisor thread: %s (invocations=%s)"
            % (thread_id, supervisor_state.get("invocation_count", 0))
        )
    archive_summary = normalize_text(state.get("archive_summary", ""))
    if archive_summary:
        lines.append("Archived summary: %s" % archive_summary)
    if recent:
        lines.append("Recent history:")
        lines.extend("- %s" % summarize_entry(entry) for entry in recent)
    next_task = normalize_text(state.get("next_task", ""))
    if next_task:
        lines.append("Next task: %s" % next_task)
    snapshot = "\n".join(lines)
    max_chars = int(state.get("limits", {}).get("max_context_chars", DEFAULT_MAX_CONTEXT_CHARS))
    return snapshot[:max_chars]


def merge_archive_summary(existing: str, new_digest: str, max_chars: int) -> str:
    parts = [part for part in [normalize_text(existing), normalize_text(new_digest)] if part]
    merged = " ".join(parts)
    if len(merged) <= max_chars:
        return merged
    return merged[-max_chars:]


def compact_history(
    state: Dict[str, Any],
    keep_last: int = 8,
    max_archive_chars: int = DEFAULT_MAX_ARCHIVE_CHARS,
) -> Dict[str, Any]:
    history = state.get("history", [])
    if len(history) > keep_last:
        trimmed = history[:-keep_last]
        recent = history[-keep_last:]
        digest = " ".join(summarize_entry(entry) for entry in trimmed)
        state["archive_summary"] = merge_archive_summary(
            state.get("archive_summary", ""),
            digest,
            max_archive_chars,
        )
        state["history"] = recent
    state["context_snapshot"] = build_context_snapshot(state, keep_last=keep_last)
    return state


def append_jsonl_record(path: Union[str, Path], record: Dict[str, Any]) -> None:
    resolved_path = Path(path).resolve()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    with resolved_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_event_record(
    state_path: Union[str, Path],
    state: Dict[str, Any],
    kind: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ensure_log_directories(state)
    logging_state = state.setdefault("logging", {})
    event_log_path = Path(logging_state.get("event_log_path", "")).resolve()
    next_event_id = int(logging_state.get("events_written", 0)) + 1
    event = {
        "id": next_event_id,
        "timestamp": utc_now(),
        "kind": normalize_text(kind),
        "message": normalize_text(message),
        "task_id": normalize_text(state.get("task", {}).get("id", "")),
        "state_path": str(Path(state_path).resolve()),
        "data": data or {},
    }
    append_jsonl_record(event_log_path, event)
    logging_state["events_written"] = next_event_id
    logging_state["last_event_at"] = event["timestamp"]
    return event


def append_event_to_state_file(
    state_path: Union[str, Path],
    kind: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    resolved_state_path = Path(state_path).resolve()
    state = load_state(resolved_state_path)
    event = append_event_record(resolved_state_path, state, kind, message, data=data)
    save_state(resolved_state_path, state)
    return event


def render_round_summary(state: Dict[str, Any], entry: Dict[str, Any]) -> str:
    lines = [
        "# Iteration %s" % entry.get("iteration", "?"),
        "",
        "- Status: `%s`" % entry.get("status", ""),
        "- Timestamp: `%s`" % entry.get("timestamp", ""),
        "- Operating mode: `%s`" % state.get("operating_mode", ""),
        "- Task: %s" % entry.get("task", ""),
        "- Local done condition: %s" % entry.get("local_done_condition", ""),
        "- Result summary: %s" % entry.get("result_summary", ""),
        "- Verification summary: %s" % entry.get("verification_summary", ""),
        "- Stop condition met: `%s`" % entry.get("stop_condition_met", False),
    ]
    elapsed_since_previous = entry.get("elapsed_since_previous_seconds")
    if elapsed_since_previous is not None:
        lines.append("- Elapsed since previous iteration: `%s`" % seconds_to_human(elapsed_since_previous))
    announcement = normalize_text(entry.get("announcement", ""))
    if announcement:
        lines.append("- Announcement: %s" % announcement)
    stop_reason = normalize_text(entry.get("stop_reason", ""))
    if stop_reason:
        lines.append("- Stop reason: %s" % stop_reason)
    lines.extend(
        [
            "",
            "## Evidence",
        ]
    )
    evidence = entry.get("evidence", [])
    if evidence:
        lines.extend("- %s" % item for item in evidence)
    else:
        lines.append("- None recorded")
    lines.extend(
        [
            "",
            "## Artifacts",
        ]
    )
    artifacts = entry.get("artifacts", [])
    if artifacts:
        lines.extend("- %s" % item for item in artifacts)
    else:
        lines.append("- None recorded")
    next_task = normalize_text(entry.get("next_task", ""))
    if next_task:
        lines.extend(
            [
                "",
                "## Next Task",
                "",
                next_task,
            ]
        )
    return "\n".join(lines) + "\n"


def write_round_summary(
    state_path: Union[str, Path],
    state: Dict[str, Any],
    entry: Dict[str, Any],
) -> str:
    logging_state = state.setdefault("logging", {})
    round_summary_dir = Path(logging_state.get("round_summary_dir", "")).resolve()
    round_summary_dir.mkdir(parents=True, exist_ok=True)
    filename = "iteration-%04d.md" % int(entry.get("iteration", 0))
    summary_path = round_summary_dir / filename
    summary_path.write_text(render_round_summary(state, entry), encoding="utf-8")
    logging_state["last_round_summary_path"] = str(summary_path)
    return str(summary_path)


def append_iteration_record(
    state_path: Union[str, Path],
    state: Dict[str, Any],
    entry: Dict[str, Any],
) -> Dict[str, Any]:
    ensure_log_directories(state)
    logging_state = state.setdefault("logging", {})
    iteration_log_path = Path(logging_state.get("iteration_log_path", "")).resolve()
    next_record_id = int(logging_state.get("iterations_persisted", 0)) + 1
    record = {
        "id": next_record_id,
        "recorded_at": utc_now(),
        "task_id": normalize_text(state.get("task", {}).get("id", "")),
        "state_path": str(Path(state_path).resolve()),
        "operating_mode": state.get("operating_mode", "interactive"),
        "goal": normalize_text(state.get("goal", "")),
        "global_stop_condition": normalize_text(state.get("global_stop_condition", "")),
        "entry": entry,
    }
    append_jsonl_record(iteration_log_path, record)
    logging_state["iterations_persisted"] = next_record_id
    logging_state["last_iteration_at"] = record["recorded_at"]
    return record


def parse_timestamp(value: str) -> Optional[datetime]:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def seconds_between_timestamps(previous: str, current: str) -> Optional[float]:
    previous_dt = parse_timestamp(previous)
    current_dt = parse_timestamp(current)
    if previous_dt is None or current_dt is None:
        return None
    return max(0.0, (current_dt - previous_dt).total_seconds())


def render_progress_bar(percent: float, width: int = 20) -> str:
    clamped = max(0.0, min(100.0, percent))
    filled = int(round((clamped / 100.0) * width))
    return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"


def seconds_to_human(seconds: Optional[float]) -> str:
    if seconds is None:
        return "unknown"
    total_seconds = max(0, int(round(seconds)))
    if total_seconds < 60:
        return "%ss" % total_seconds
    minutes, sec = divmod(total_seconds, 60)
    if minutes < 60:
        return "%sm %ss" % (minutes, sec)
    hours, minutes = divmod(minutes, 60)
    return "%sh %sm" % (hours, minutes)


def recent_iteration_durations(history: List[Dict[str, Any]], keep_last: int = 5) -> List[float]:
    if len(history) < 2:
        return []
    timestamps = [parse_timestamp(entry.get("timestamp", "")) for entry in history]
    durations = []
    for previous, current in zip(timestamps[:-1], timestamps[1:]):
        if previous is None or current is None:
            continue
        durations.append(max(0.0, (current - previous).total_seconds()))
    return durations[-keep_last:]


def build_status_report(
    state: Dict[str, Any],
    stop_report: Optional[Dict[str, Any]] = None,
    recent_window: int = 5,
) -> Dict[str, Any]:
    history = state.get("history", [])
    iteration_count = int(state.get("counters", {}).get("iteration", 0))
    recent_durations = recent_iteration_durations(history, keep_last=recent_window)
    average_duration = (
        sum(recent_durations) / float(len(recent_durations)) if recent_durations else None
    )

    progress_source = "state"
    completed_checks = 0
    total_checks = 0
    if stop_report:
        checks = stop_report.get("stop_checks", {})
        total_checks = int(checks.get("total_checks", 0))
        completed_checks = int(checks.get("passed_checks", 0))

    use_stop_check_progress = total_checks > 1
    if total_checks == 1 and stop_report and stop_report.get("should_stop"):
        use_stop_check_progress = True

    if use_stop_check_progress:
        progress_source = "stop-checks"
        progress_percent = (float(completed_checks) / float(total_checks)) * 100.0
    elif state.get("status") == "completed":
        progress_percent = 100.0
    else:
        progress_source = "iteration-budget"
        max_iterations = max(1, int(state.get("limits", {}).get("max_iterations", 1)))
        progress_percent = min(99.0, (float(iteration_count) / float(max_iterations)) * 100.0)

    estimated_remaining_seconds = None
    if average_duration is not None and iteration_count > 0 and 0.0 < progress_percent < 100.0:
        estimated_total_iterations = float(iteration_count) / (progress_percent / 100.0)
        remaining_iterations = max(0.0, estimated_total_iterations - float(iteration_count))
        estimated_remaining_seconds = remaining_iterations * average_duration

    created_at = parse_timestamp(state.get("created_at", ""))
    elapsed_run_seconds = None
    if created_at is not None:
        elapsed_run_seconds = max(0.0, (datetime.now(timezone.utc) - created_at).total_seconds())

    blocker_state = state.get("blocker", {})
    next_task = normalize_text(state.get("next_task", ""))
    return {
        "task_id": normalize_text(state.get("task", {}).get("id", "")),
        "status": state.get("status", "running"),
        "operating_mode": state.get("operating_mode", "interactive"),
        "iterations_completed": iteration_count,
        "no_progress_rounds": int(state.get("counters", {}).get("no_progress_rounds", 0)),
        "recovery_count": int(state.get("counters", {}).get("recovery_count", 0)),
        "progress_percent": round(progress_percent, 1),
        "progress_bar": render_progress_bar(progress_percent),
        "progress_source": progress_source,
        "stop_checks_passed": completed_checks,
        "stop_checks_total": total_checks,
        "recent_iteration_seconds": [round(item, 1) for item in recent_durations],
        "recent_iteration_human": [seconds_to_human(item) for item in recent_durations],
        "recent_average_seconds": round(average_duration, 1) if average_duration is not None else None,
        "recent_average_human": seconds_to_human(average_duration),
        "estimated_remaining_seconds": (
            round(estimated_remaining_seconds, 1)
            if estimated_remaining_seconds is not None
            else None
        ),
        "estimated_remaining_human": seconds_to_human(estimated_remaining_seconds),
        "elapsed_run_seconds": round(elapsed_run_seconds, 1) if elapsed_run_seconds is not None else None,
        "elapsed_run_human": seconds_to_human(elapsed_run_seconds),
        "next_task": next_task,
        "blocker_reason": normalize_text(blocker_state.get("reason", "")),
        "needs_human_input": bool(blocker_state.get("needs_human_input", False)),
        "supervisor_invocations": int(state.get("supervisor", {}).get("invocation_count", 0)),
    }


def render_status_text(report: Dict[str, Any]) -> str:
    recent_iteration_human = report.get("recent_iteration_human", [])
    recent_iteration_display = ", ".join(recent_iteration_human) if recent_iteration_human else "unknown"
    lines = [
        "Task: %s" % report.get("task_id", "unknown"),
        "Status: %s" % report.get("status", "unknown"),
        "Mode: %s" % report.get("operating_mode", "unknown"),
        "Iterations completed: %s" % report.get("iterations_completed", 0),
        "No-progress rounds: %s" % report.get("no_progress_rounds", 0),
        "Recoveries: %s" % report.get("recovery_count", 0),
        "Progress: %s %s%% (%s)"
        % (
            report.get("progress_bar", ""),
            report.get("progress_percent", 0),
            report.get("progress_source", "state"),
        ),
        "Stop checks: %s/%s passed"
        % (report.get("stop_checks_passed", 0), report.get("stop_checks_total", 0)),
        "Recent iteration times: %s" % recent_iteration_display,
        "Recent avg iteration time: %s" % report.get("recent_average_human", "unknown"),
        "Elapsed time: %s" % report.get("elapsed_run_human", "unknown"),
        "Estimated time remaining: %s" % report.get("estimated_remaining_human", "unknown"),
        "Supervisor invocations: %s" % report.get("supervisor_invocations", 0),
    ]
    next_task = normalize_text(report.get("next_task", ""))
    if next_task:
        lines.append("Next task: %s" % next_task)
    blocker_reason = normalize_text(report.get("blocker_reason", ""))
    if blocker_reason:
        lines.append(
            "Blocker: %s (needs_human_input=%s)"
            % (blocker_reason, report.get("needs_human_input", False))
        )
    return "\n".join(lines) + "\n"


def write_status_text(state: Dict[str, Any], report: Dict[str, Any]) -> str:
    status_path = Path(state.get("logging", {}).get("status_text_path", "")).resolve()
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(render_status_text(report), encoding="utf-8")
    return str(status_path)


def build_stop_report_summary(stop_report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not stop_report:
        return {}
    stop_checks = stop_report.get("stop_checks", {})
    return {
        "should_stop": bool(stop_report.get("should_stop", False)),
        "success": bool(stop_report.get("success", False)),
        "status": normalize_text(stop_report.get("status", "")),
        "reasons": stop_report.get("reasons", []),
        "passed_checks": int(stop_checks.get("passed_checks", 0)),
        "total_checks": int(stop_checks.get("total_checks", 0)),
    }


def append_status_snapshot(
    state_path: Union[str, Path],
    state: Dict[str, Any],
    report: Dict[str, Any],
    label: str = "",
    stop_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ensure_log_directories(state)
    logging_state = state.setdefault("logging", {})
    status_history_path = Path(logging_state.get("status_history_path", "")).resolve()
    next_snapshot_id = int(logging_state.get("status_snapshots_written", 0)) + 1
    snapshot = {
        "id": next_snapshot_id,
        "timestamp": utc_now(),
        "label": normalize_text(label),
        "task_id": normalize_text(state.get("task", {}).get("id", "")),
        "state_path": str(Path(state_path).resolve()),
        "report": report,
        "stop": build_stop_report_summary(stop_report),
    }
    append_jsonl_record(status_history_path, snapshot)
    logging_state["status_snapshots_written"] = next_snapshot_id
    logging_state["last_status_at"] = snapshot["timestamp"]
    return snapshot


def write_stop_report_file(
    state_path: Union[str, Path],
    state: Dict[str, Any],
    stop_report: Dict[str, Any],
) -> str:
    ensure_log_directories(state)
    logging_state = state.setdefault("logging", {})
    stop_report_path = Path(logging_state.get("stop_report_path", "")).resolve()
    payload = dict(stop_report)
    payload["generated_at"] = utc_now()
    payload["task_id"] = normalize_text(state.get("task", {}).get("id", ""))
    payload["state_path"] = str(Path(state_path).resolve())
    stop_report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logging_state["last_stop_report_at"] = payload["generated_at"]
    return str(stop_report_path)


def render_run_summary(
    state_path: Union[str, Path],
    state: Dict[str, Any],
    report: Optional[Dict[str, Any]] = None,
    stop_report: Optional[Dict[str, Any]] = None,
) -> str:
    if report is None:
        report = build_status_report(state, stop_report=stop_report)
    stop_summary = build_stop_report_summary(stop_report)
    logging_state = state.get("logging", {})
    supervisor_state = state.get("supervisor", {})
    task_state = state.get("task", {})
    history = state.get("history", [])
    success_evidence = format_list(state.get("success_evidence", []))
    recent_history = history[-5:]
    lines = [
        "# Strict Agent Loop Run Summary",
        "",
        "## Run",
        "",
        "- State file: %s" % Path(state_path).resolve(),
        "- Task id: `%s`" % normalize_text(task_state.get("id", "")),
        "- Task root: %s" % normalize_text(task_state.get("root_dir", "")),
        "- Manager dir: %s" % normalize_text(task_state.get("manager_dir", "")),
        "- Registry: %s" % registry_path_for_state(state_path, state),
        "- Goal: %s" % normalize_text(state.get("goal", "")),
        "- Mode: `%s`" % state.get("operating_mode", ""),
        "- Status: `%s`" % state.get("status", ""),
        "- Created at: `%s`" % state.get("created_at", ""),
        "- Updated at: `%s`" % state.get("updated_at", ""),
        "- Workspace root: %s" % state.get("workspace_root", ""),
        "- Global stop condition: %s" % normalize_text(state.get("global_stop_condition", "")),
        "- Blocker definition: %s" % normalize_text(state.get("blocker_definition", "")),
    ]
    if success_evidence:
        lines.append("- Success evidence: %s" % "; ".join(success_evidence))
    lines.extend(
        [
            "",
            "## Progress",
            "",
            "- Iterations completed: `%s`" % report.get("iterations_completed", 0),
            "- No-progress rounds: `%s`" % report.get("no_progress_rounds", 0),
            "- Recoveries: `%s`" % report.get("recovery_count", 0),
            "- Progress: `%s %s%% (%s)`"
            % (
                report.get("progress_bar", ""),
                report.get("progress_percent", 0),
                report.get("progress_source", "state"),
            ),
            "- Recent iteration times: %s"
            % (", ".join(report.get("recent_iteration_human", [])) or "unknown"),
            "- Recent avg iteration time: `%s`" % report.get("recent_average_human", "unknown"),
            "- Elapsed time: `%s`" % report.get("elapsed_run_human", "unknown"),
            "- Estimated remaining time: `%s`" % report.get("estimated_remaining_human", "unknown"),
            "- Supervisor invocations: `%s`" % report.get("supervisor_invocations", 0),
        ]
    )
    next_task = normalize_text(state.get("next_task", ""))
    if next_task:
        lines.append("- Next task: %s" % next_task)
    blocker_reason = normalize_text(state.get("blocker", {}).get("reason", ""))
    if blocker_reason:
        lines.append(
            "- Blocker: %s (needs_human_input=%s)"
            % (blocker_reason, state.get("blocker", {}).get("needs_human_input", False))
        )
    lines.extend(
        [
            "",
            "## Stop Evaluation",
            "",
            "- Should stop: `%s`" % stop_summary.get("should_stop", False),
            "- Success: `%s`" % stop_summary.get("success", False),
            "- Reasons: %s" % (", ".join(stop_summary.get("reasons", [])) or "unknown"),
            "- Stop checks passed: `%s/%s`"
            % (stop_summary.get("passed_checks", 0), stop_summary.get("total_checks", 0)),
            "",
            "## Durable Artifacts",
            "",
            "- Event log: %s" % logging_state.get("event_log_path", ""),
            "- Full iteration ledger: %s" % logging_state.get("iteration_log_path", ""),
            "- Status history: %s" % logging_state.get("status_history_path", ""),
            "- Latest status text: %s" % logging_state.get("status_text_path", ""),
            "- Latest stop report: %s" % logging_state.get("stop_report_path", ""),
            "- Run summary: %s" % logging_state.get("run_summary_path", ""),
            "- Round summaries: %s" % logging_state.get("round_summary_dir", ""),
        ]
    )
    if supervisor_state.get("enabled"):
        lines.append("- Supervisor logs: %s" % supervisor_state.get("log_dir", ""))
    lines.extend(
        [
            "",
            "## Recent Verified Iterations",
            "",
        ]
    )
    if recent_history:
        lines.extend("- %s" % summarize_entry(entry) for entry in recent_history)
    else:
        lines.append("- No verified iterations recorded yet")
    archive_summary = normalize_text(state.get("archive_summary", ""))
    if archive_summary:
        lines.extend(
            [
                "",
                "## Archived Digest",
                "",
                archive_summary,
            ]
        )
    last_round_summary = normalize_text(logging_state.get("last_round_summary_path", ""))
    if last_round_summary:
        lines.extend(
            [
                "",
                "## Latest Round Summary",
                "",
                last_round_summary,
            ]
        )
    lines.extend(
        [
            "",
            "This run summary is refreshed from disk-backed state. Full per-iteration details stay append-only in iterations.jsonl and rounds/ even if state history is compacted.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_run_summary(
    state_path: Union[str, Path],
    state: Dict[str, Any],
    stop_report: Optional[Dict[str, Any]] = None,
    report: Optional[Dict[str, Any]] = None,
) -> str:
    ensure_log_directories(state)
    logging_state = state.setdefault("logging", {})
    run_summary_path = Path(logging_state.get("run_summary_path", "")).resolve()
    run_summary_path.write_text(
        render_run_summary(state_path, state, report=report, stop_report=stop_report),
        encoding="utf-8",
    )
    logging_state["last_run_summary_at"] = utc_now()
    return str(run_summary_path)


def set_blocker(state: Dict[str, Any], reason: str, needs_human_input: bool) -> None:
    state["blocker"] = {
        "needs_human_input": needs_human_input,
        "reason": normalize_text(reason),
        "updated_at": utc_now(),
    }


def clear_blocker(state: Dict[str, Any]) -> None:
    state["blocker"] = {
        "needs_human_input": False,
        "reason": "",
        "updated_at": utc_now(),
    }
