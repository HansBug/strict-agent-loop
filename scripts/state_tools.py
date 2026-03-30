#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_state(path: str | Path) -> dict[str, Any]:
    state_path = Path(path).resolve()
    with state_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_state(path: str | Path, state: dict[str, Any]) -> None:
    state_path = Path(path).resolve()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = utc_now()
    with state_path.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")


def normalize_text(value: str) -> str:
    return " ".join(value.split())


def format_list(items: Iterable[str]) -> list[str]:
    return [normalize_text(item) for item in items if item and item.strip()]


def build_state(
    goal: str,
    global_stop_condition: str,
    workspace_root: str | Path,
    success_evidence: list[str],
    blocker_definition: str,
    max_iterations: int,
    max_no_progress_rounds: int,
    max_context_chars: int,
    executor_agent_id: str = "",
) -> dict[str, Any]:
    now = utc_now()
    return {
        "schema_version": 1,
        "skill_name": "strict-agent-loop",
        "created_at": now,
        "updated_at": now,
        "goal": normalize_text(goal),
        "global_stop_condition": normalize_text(global_stop_condition),
        "workspace_root": str(Path(workspace_root).resolve()),
        "success_evidence": format_list(success_evidence),
        "blocker_definition": normalize_text(blocker_definition),
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
        "next_task": "",
        "context_snapshot": "",
        "archive_summary": "",
        "history": [],
    }


def summarize_entry(entry: dict[str, Any]) -> str:
    task = normalize_text(entry.get("task", ""))
    result_summary = normalize_text(entry.get("result_summary", ""))
    verification = normalize_text(entry.get("verification_summary", ""))
    stop_flag = "yes" if entry.get("stop_condition_met") else "no"
    return (
        f"Iter {entry.get('iteration', '?')}: task={task}; result={result_summary}; "
        f"verified={verification}; stop_met={stop_flag}"
    )


def build_context_snapshot(state: dict[str, Any], keep_last: int = 5) -> str:
    history = state.get("history", [])
    recent = history[-keep_last:]
    lines = [
        f"Goal: {normalize_text(state.get('goal', ''))}",
        f"Global stop condition: {normalize_text(state.get('global_stop_condition', ''))}",
        f"Workspace root: {normalize_text(state.get('workspace_root', ''))}",
        f"Status: {normalize_text(state.get('status', ''))}",
        f"Total recorded iterations: {state.get('counters', {}).get('iteration', 0)}",
        f"No-progress rounds: {state.get('counters', {}).get('no_progress_rounds', 0)}",
    ]
    success_evidence = format_list(state.get("success_evidence", []))
    if success_evidence:
        lines.append("Success evidence: " + "; ".join(success_evidence))
    blocker_definition = normalize_text(state.get("blocker_definition", ""))
    if blocker_definition:
        lines.append(f"Blocker definition: {blocker_definition}")
    archive_summary = normalize_text(state.get("archive_summary", ""))
    if archive_summary:
        lines.append(f"Archived summary: {archive_summary}")
    if recent:
        lines.append("Recent history:")
        lines.extend(f"- {summarize_entry(entry)}" for entry in recent)
    next_task = normalize_text(state.get("next_task", ""))
    if next_task:
        lines.append(f"Next task: {next_task}")
    snapshot = "\n".join(lines)
    max_chars = int(state.get("limits", {}).get("max_context_chars", 12000))
    return snapshot[:max_chars]


def merge_archive_summary(existing: str, new_digest: str, max_chars: int) -> str:
    parts = [part for part in [normalize_text(existing), normalize_text(new_digest)] if part]
    merged = " ".join(parts)
    if len(merged) <= max_chars:
        return merged
    return merged[-max_chars:]
