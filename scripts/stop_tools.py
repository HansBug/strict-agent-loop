#!/usr/bin/env python3

import copy
import json
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

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


def build_completed_projection(state: Dict[str, Any]) -> Dict[str, Any]:
    projected_state = copy.deepcopy(state)
    projected_state["status"] = "completed"
    projected_state["next_task"] = "Stop condition met; exit."
    blocker = projected_state.setdefault("blocker", {})
    blocker["needs_human_input"] = False
    blocker["reason"] = ""
    history = projected_state.get("history", [])
    if history:
        history[-1]["status"] = "completed"
        history[-1]["stop_condition_met"] = True
    return projected_state


@contextmanager
def projected_state_file(
    state_path: Path,
    projected_state: Dict[str, Any],
) -> Iterator[Path]:
    temp_handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=".stop-check-projection-",
        suffix=".json",
        dir=str(state_path.parent),
        delete=False,
    )
    temp_path = Path(temp_handle.name).resolve()
    try:
        with temp_handle:
            json.dump(projected_state, temp_handle, indent=2, ensure_ascii=False)
            temp_handle.write("\n")
        yield temp_path
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def rewrite_command_state_path(
    command: str,
    original_state_path: Optional[Path],
    replacement_state_path: Optional[Path],
    cwd_path: Path,
) -> str:
    if not original_state_path or not replacement_state_path:
        return command

    original_state_path = original_state_path.resolve()
    replacement_state_path = replacement_state_path.resolve()

    replacements = {
        str(original_state_path): str(replacement_state_path),
    }
    try:
        relative_original = str(original_state_path.relative_to(cwd_path))
        replacements[relative_original] = str(replacement_state_path)
        if not relative_original.startswith("./"):
            replacements["./%s" % relative_original] = str(replacement_state_path)
    except ValueError:
        pass

    rewritten = command
    for source, target in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        rewritten = rewritten.replace(source, target)
    return rewritten


def evaluate_command_checks(
    state: Dict[str, Any],
    state_path: Optional[Path] = None,
    replacement_state_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    workspace_root = Path(state.get("workspace_root", ".")).resolve()
    checks = state.get("stop_checks", {}).get("commands", [])
    results = []
    for check in checks:
        command = check.get("command", "").strip()
        cwd_value = check.get("cwd", ".")
        timeout_seconds = int(check.get("timeout_seconds", 900))
        cwd_path = resolve_workspace_path(workspace_root, cwd_value)
        executed_command = rewrite_command_state_path(
            command,
            original_state_path=state_path,
            replacement_state_path=replacement_state_path,
            cwd_path=cwd_path,
        )
        try:
            completed = subprocess.run(
                executed_command,
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
                "executed_command": executed_command,
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


def evaluate_stop_checks(
    state: Dict[str, Any],
    state_path: Optional[Path] = None,
    replacement_state_path: Optional[Path] = None,
) -> Dict[str, Any]:
    command_results = evaluate_command_checks(
        state,
        state_path=state_path,
        replacement_state_path=replacement_state_path,
    )
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


def build_stop_report(state: Dict[str, Any], state_path: Optional[Path] = None) -> Dict[str, Any]:
    counters = state.get("counters", {})
    limits = state.get("limits", {})
    history = state.get("history", [])
    last_entry = history[-1] if history else {}
    current_stop_checks = evaluate_stop_checks(state, state_path=state_path)
    stop_checks = current_stop_checks
    completion_projection = {
        "used": False,
        "projected_status": "completed",
        "stop_checks_passed": False,
    }

    should_try_projection = (
        state_path is not None
        and state.get("status") not in {"completed", "blocked", "failed"}
        and bool(state.get("stop_checks", {}).get("commands", []))
        and current_stop_checks.get("has_checks")
        and not current_stop_checks.get("all_passed")
    )
    if should_try_projection:
        projected_state = build_completed_projection(state)
        completion_projection["used"] = True
        with projected_state_file(state_path.resolve(), projected_state) as projection_path:
            projected_stop_checks = evaluate_stop_checks(
                projected_state,
                state_path=state_path,
                replacement_state_path=projection_path,
            )
        completion_projection["projected_stop_checks"] = projected_stop_checks
        if projected_stop_checks.get("all_passed"):
            completion_projection["stop_checks_passed"] = True
            stop_checks = projected_stop_checks

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
    elif stop_checks.get("has_checks") and stop_checks.get("all_passed"):
        should_stop = True
        success = True
        exit_code = 0
        if completion_projection.get("stop_checks_passed"):
            reasons.append("stop_checks_passed_after_completion_projection")
        else:
            reasons.append("stop_checks_passed")
    elif status == "completed" or last_entry.get("stop_condition_met"):
        should_stop = True
        success = True
        exit_code = 0
        reasons.append("global_stop_condition_met")
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

    report = {
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
    if completion_projection.get("used"):
        report["completion_projection"] = completion_projection
    return report
