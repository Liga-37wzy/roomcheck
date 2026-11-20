"""Run with: python -m roomcheck examples/physical.json"""

import argparse
import json
from pathlib import Path
import sys

from .core import ModelError, check, parse_model


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ModelError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def load_model(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(1_048_577)
    if len(raw) > 1_048_576:
        raise ModelError("Input exceeds 1 MiB")
    return parse_model(json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_keys))


def main(argv=None):
    # Stable UTF-8 output when redirected on Windows as well as on Unix.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Check escape-room and digital-puzzle logic offline.")
    parser.add_argument("model", help="UTF-8 JSON model path")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable report")
    parser.add_argument("--max-states", type=int, default=20000, help="1-100000; default 20000")
    args = parser.parse_args(argv)
    try:
        model = load_model(args.model)
        result = check(model, args.max_states)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        if args.json:
            print(json.dumps({"status": "invalid", "error": str(exc)}, ensure_ascii=True))
        else:
            print(f"Invalid input: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=True, indent=2))
    else:
        print(f"{result['title']}: {result['status'].upper()}")
        print(f"States: {result['states']} | Complete: {result['complete']} | Solvable: {result['solvable']}")
        print(f"Every reachable state can still win: {result['all_states_can_win']}")
        if result["solution"] is not None:
            print("Winning path: " + (" -> ".join(result["solution"]) or "(already won at start)"))
        for issue in result["issues"]:
            print(f"[{issue['severity']}] {issue['code']}: {issue['message']}")
            if "trace" in issue:
                print("  Trace: " + (" -> ".join(issue["trace"]) or "(initial state)"))
                print("  Inventory: " + ", ".join(issue["inventory"]))
            if "actions" in issue:
                print("  Actions: " + ", ".join(issue["actions"]))
            if "skipped" in issue:
                print("  Skipped: " + ", ".join(issue["skipped"]))
    if result["status"] == "issues":
        return 1
    return 0 if result["complete"] else 3


if __name__ == "__main__":
    sys.exit(main())
