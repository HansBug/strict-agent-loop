#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read dotted paths from a JSON file.")
    parser.add_argument("json_path", help="Path to the JSON file")
    parser.add_argument("paths", nargs="+", help="One or more dotted lookup paths")
    parser.add_argument(
        "--as-json",
        action="store_true",
        help="Print a single JSON object mapping lookup paths to values instead of one line per path.",
    )
    return parser.parse_args()


def lookup_path(payload, dotted_path):
    value = payload
    for part in dotted_path.split("."):
        if isinstance(value, list):
            try:
                index = int(part)
            except ValueError:
                raise KeyError(dotted_path)
            try:
                value = value[index]
            except IndexError:
                raise KeyError(dotted_path)
            continue
        if not isinstance(value, dict) or part not in value:
            raise KeyError(dotted_path)
        value = value[part]
    return value


def main() -> int:
    args = parse_args()
    payload = json.loads(Path(args.json_path).read_text(encoding="utf-8"))
    values = {}
    for dotted_path in args.paths:
        try:
            values[dotted_path] = lookup_path(payload, dotted_path)
        except KeyError:
            print("Missing JSON path: %s" % dotted_path, file=sys.stderr)
            return 1

    if args.as_json:
        print(json.dumps(values, ensure_ascii=False, indent=2))
        return 0

    for dotted_path in args.paths:
        print(values[dotted_path])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
