#!/usr/bin/env python3

import subprocess
from pathlib import Path
from typing import Any, Dict, List

from state_tools import normalize_text


def trim_output(value: str, limit: int = 2000) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


def resolve_workspace_path(workspace_root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (workspace_root / raw_path).resolve()


def evaluate_command_checks(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    workspace_root = Path(state.get("workspace_root", ".")).resolve()
    checks = state.get("stop_checks", {}).get("commands", [])
    results = []
    for check in checks:
        command = check.get("command", "").strip()
        cwd_value = check.get("cwd", ".")
        timeout_seconds = int(check.get("timeout_seconds", 900))
        cwd_path = resolve_workspace_path(workspace_root, cwd_value)
        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=str(cwd_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout_seconds,
            )
            passed = completed.returncode == 0
            exit_code = completed.returncode
            stdout_tail = trim_output(completed.stdout or "")
            stderr_tail = trim_output(completed.stderr or "")
        except subprocess.TimeoutExpired as error:
            passed = False
            exit_code = -1
            stdout_tail = trim_output((error.stdout or "") if isinstance(error.stdout, str) else "")
            stderr_tail = trim_output((error.stderr or "") if isinstance(error.stderr, str) else "")
        results.append(
            {
                "type": "command",
                "description": normalize_text(check.get("description", command)),
                "command": command,
                "cwd": str(cwd_path),
                "passed": passed,
                "exit_code": exit_code,
                "stdout_tail": stdout_tail,
                "stderr_tail": stderr_tail,
            }
        )
    return results


def evaluate_path_checks(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    workspace_root = Path(state.get("workspace_root", ".")).resolve()
    checks = state.get("stop_checks", {}).get("paths_exist", [])
    results = []
    for check in checks:
        path_value = check.get("path", "")
        resolved_path = resolve_workspace_path(workspace_root, path_value)
        results.append(
            {
                "type": "path_exists",
                "description": normalize_text(check.get("description", "%s exists" % path_value)),
                "path": str(resolved_path),
                "passed": resolved_path.exists(),
            }
        )
    return results


def evaluate_text_pattern_checks(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    workspace_root = Path(state.get("workspace_root", ".")).resolve()
    checks = state.get("stop_checks", {}).get("text_patterns", [])
    results = []
    for check in checks:
        path_value = check.get("path", "")
        pattern = check.get("pattern", "")
        resolved_path = resolve_workspace_path(workspace_root, path_value)
        file_exists = resolved_path.exists()
        matched = False
        if file_exists:
            matched = pattern in resolved_path.read_text(encoding="utf-8", errors="replace")
        results.append(
            {
                "type": "text_pattern",
                "description": normalize_text(
                    check.get("description", "%s contains %s" % (path_value, pattern))
                ),
                "path": str(resolved_path),
                "pattern": pattern,
                "passed": file_exists and matched,
                "file_exists": file_exists,
            }
        )
    return results


def evaluate_stop_checks(state: Dict[str, Any]) -> Dict[str, Any]:
    command_results = evaluate_command_checks(state)
    path_results = evaluate_path_checks(state)
    text_results = evaluate_text_pattern_checks(state)
    all_results = command_results + path_results + text_results
    has_checks = len(all_results) > 0
    passed_checks = sum(1 for item in all_results if item.get("passed"))
    return {
        "has_checks": has_checks,
        "all_passed": has_checks and passed_checks == len(all_results),
        "passed_checks": passed_checks,
        "total_checks": len(all_results),
        "commands": command_results,
        "paths_exist": path_results,
        "text_patterns": text_results,
    }


def build_stop_report(state: Dict[str, Any]) -> Dict[str, Any]:
    counters = state.get("counters", {})
    limits = state.get("limits", {})
    history = state.get("history", [])
    last_entry = history[-1] if history else {}
    stop_checks = evaluate_stop_checks(state)

    status = state.get("status", "running")
    reasons = []
    should_stop = False
    success = False
    exit_code = 1

    if status in {"blocked", "failed"}:
        should_stop = True
        success = False
        exit_code = 2
        reasons.append("loop_status_%s" % status)
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
    elif stop_checks.get("has_checks"):
        if stop_checks.get("all_passed"):
            should_stop = True
            success = True
            exit_code = 0
            reasons.append("stop_checks_passed")
        else:
            reasons.append("continue")
            if status == "completed" or last_entry.get("stop_condition_met"):
                reasons.append("state_marked_completed_but_stop_checks_failed")
    elif status == "completed" or last_entry.get("stop_condition_met"):
        should_stop = True
        success = True
        exit_code = 0
        reasons.append("global_stop_condition_met")
    else:
        reasons.append("continue")

    return {
        "should_stop": should_stop,
        "success": success,
        "status": status,
        "reasons": reasons,
        "exit_code": exit_code,
        "iteration": int(counters.get("iteration", 0)),
        "no_progress_rounds": int(counters.get("no_progress_rounds", 0)),
        "next_task": state.get("next_task", ""),
        "global_stop_condition": state.get("global_stop_condition", ""),
        "stop_checks": stop_checks,
        "blocker": state.get("blocker", {}),
    }
