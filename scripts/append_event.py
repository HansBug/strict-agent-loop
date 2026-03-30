#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
from typing import Dict

from state_tools import append_event_record, load_state, save_state


def parse_key_value(raw_value: str) -> Dict[str, str]:
    if "=" not in raw_value:
        raise ValueError("Event data must use the format key=value.")
    key, value = raw_value.split("=", 1)
    key = key.strip()
    if not key:
        raise ValueError("Event data keys must not be empty.")
    return {key: value}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Append an event to .codex-loop/events.jsonl.")
    parser.add_argument("--state", required=True, help="Path to the task state file")
    parser.add_argument("--kind", required=True, help="Structured event kind, such as round.started")
    parser.add_argument("--message", required=True, help="Human-readable event message")
    parser.add_argument("--data", action="append", default=[], help="Optional key=value data. Repeat as needed.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state_path = Path(args.state).resolve()
    state = load_state(state_path)
    data = {}
    for raw_item in args.data:
        data.update(parse_key_value(raw_item))
    event = append_event_record(state_path, state, args.kind, args.message, data=data)
    save_state(state_path, state)
    print(json.dumps(event, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
