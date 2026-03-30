#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from state_tools import build_context_snapshot, load_state, merge_archive_summary, save_state, summarize_entry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compact long strict-agent-loop history into a snapshot.")
    parser.add_argument("--state", required=True, help="Path to .codex-loop/state.json")
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
    history = state.get("history", [])

    if len(history) > args.keep_last:
        trimmed = history[:-args.keep_last]
        recent = history[-args.keep_last :]
        digest = " ".join(summarize_entry(entry) for entry in trimmed)
        state["archive_summary"] = merge_archive_summary(
            state.get("archive_summary", ""),
            digest,
            args.max_archive_chars,
        )
        state["history"] = recent

    state["context_snapshot"] = build_context_snapshot(state, keep_last=args.keep_last)
    save_state(state_path, state)
    print(
        json.dumps(
            {
                "state": str(state_path),
                "history_entries": len(state.get("history", [])),
                "snapshot_chars": len(state.get("context_snapshot", "")),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
