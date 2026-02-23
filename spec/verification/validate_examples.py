#!/usr/bin/env python3
"""
validate_examples.py — TWFF Schema Validator
spec/validate_examples.py

Validates all example TWFF process-log.json files against the published
JSON Schema. Run before any release or PR merge.

Usage:
    python spec/validate_examples.py           # validate all examples
    python spec/validate_examples.py --verbose # detailed output per event
    python spec/validate_examples.py --fix     # also compute and add _hash chains

Exit codes:
    0  — all examples valid
    1  — one or more validation failures
    2  — missing dependency (jsonschema not installed)

Requirements:
    pip install jsonschema
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

# ── Locate project root

SCRIPT_DIR  = Path(__file__).parent
REPO_ROOT   = SCRIPT_DIR.parent
SPEC_DIR    = REPO_ROOT / "spec"
SCHEMA_FILE = SPEC_DIR  / "process-log.schema.json"
EXAMPLES_DIRS = [
    REPO_ROOT / "spec" / "v0.1",
    REPO_ROOT / "examples",
]


# ── Colours for terminal output ───

class C:
    GREEN  = "\033[32m"
    RED    = "\033[31m"
    YELLOW = "\033[33m"
    CYAN   = "\033[36m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"

def ok(msg: str)   -> str: return f"{C.GREEN}✓{C.RESET} {msg}"
def fail(msg: str) -> str: return f"{C.RED}✗{C.RESET} {msg}"
def warn(msg: str) -> str: return f"{C.YELLOW}⚠{C.RESET} {msg}"
def head(msg: str) -> str: return f"\n{C.BOLD}{C.CYAN}{msg}{C.RESET}"


# ── Hash chain utilities ──

def compute_event_hash(event: dict, previous_hash: str, session_id: str) -> str:
    """
    Compute _hash for one event (excluding the _hash field itself).
    See SPEC §5.2 for the full specification.
    """
    payload = {k: v for k, v in event.items() if k != "_hash"}
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    hash_input   = payload_json + "|" + previous_hash + "|" + session_id
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


def verify_hash_chain(log: dict, verbose: bool = False) -> tuple[bool, list[str]]:
    """
    Verify the per-event hash chain in a process-log dict.
    Returns (all_ok, list_of_messages).
    """
    session_id = log.get("session_id", "")
    events     = log.get("events", [])
    messages   = []
    prev_hash  = ""
    all_ok     = True

    for i, event in enumerate(events):
        stored   = event.get("_hash", "")
        expected = compute_event_hash(event, prev_hash, session_id)

        if not stored:
            messages.append(warn(f"  Event {i} ({event.get('type')!r}): no _hash field"))
        elif stored != expected:
            all_ok = False
            messages.append(fail(
                f"  Event {i} ({event.get('type')!r}): hash mismatch\n"
                f"    expected: {expected}\n"
                f"    stored:   {stored}"
            ))
        elif verbose:
            messages.append(ok(f"  Event {i} ({event.get('type')!r}): {stored[:16]}…"))

        prev_hash = stored or expected

    # Check top-level _integrity
    integrity = log.get("_integrity", {})
    head_hash = integrity.get("head_hash", "")
    if head_hash:
        if head_hash != prev_hash:
            all_ok = False
            messages.append(fail(
                f"  _integrity.head_hash mismatch\n"
                f"    expected: {prev_hash}\n"
                f"    stored:   {head_hash}"
            ))
        elif verbose:
            messages.append(ok(f"  _integrity.head_hash: {head_hash[:16]}…"))
    else:
        messages.append(warn("  No _integrity.head_hash — chain not anchored"))

    return all_ok, messages


def add_hash_chain(log: dict) -> dict:
    """
    Compute and add _hash fields to every event in a process-log dict.
    Also sets _integrity block. Returns the modified log (in-place).
    """
    session_id = log.get("session_id", "")
    events     = log.get("events", [])
    prev_hash  = ""

    for event in events:
        h = compute_event_hash(event, prev_hash, session_id)
        event["_hash"] = h
        prev_hash      = h

    log["_integrity"] = {
        "algorithm":    "SHA-256-CHAIN",
        "chain_length": len(events),
        "head_hash":    prev_hash,
        "session_id":   session_id,
        "note":         "Per-event chained hash. Verify using spec §5.2.",
    }
    return log


# ── JSON Schema validation

def load_schema() -> dict:
    if not SCHEMA_FILE.exists():
        print(fail(f"Schema not found: {SCHEMA_FILE}"))
        sys.exit(1)
    with open(SCHEMA_FILE) as f:
        return json.load(f)


def validate_against_schema(
    instance: dict,
    schema: dict,
    filename: str,
) -> tuple[bool, list[str]]:
    try:
        import jsonschema
    except ImportError:
        print(fail("jsonschema not installed. Run: pip install jsonschema"))
        sys.exit(2)

    validator = jsonschema.Draft7Validator(schema)
    errors    = sorted(validator.iter_errors(instance), key=lambda e: e.path)
    messages  = []

    for err in errors:
        path = " → ".join(str(p) for p in err.absolute_path) or "(root)"
        messages.append(fail(f"  [{path}] {err.message}"))

    return (len(errors) == 0), messages


# ── File discovery

def find_example_logs() -> list[Path]:
    """Find all process-log.json files in known example directories."""
    found = []
    for d in EXAMPLES_DIRS:
        if d.exists():
            found.extend(d.rglob("process-log.json"))
    return sorted(found)


# ── Main ──

def main() -> int:
    parser = argparse.ArgumentParser(description="TWFF schema + hash-chain validator")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show per-event hash verification")
    parser.add_argument("--fix", action="store_true",
                        help="Add/recompute _hash chain in-place and write back")
    parser.add_argument("files", nargs="*",
                        help="Specific files to validate (default: auto-discover)")
    args = parser.parse_args()

    schema   = load_schema()
    examples = [Path(f) for f in args.files] if args.files else find_example_logs()

    if not examples:
        print(warn("No process-log.json files found. "
                   "Check EXAMPLES_DIRS in this script or pass files explicitly."))
        return 0

    print(head(f"TWFF Validator — {len(examples)} file(s)"))
    print(f"  Schema: {SCHEMA_FILE.relative_to(REPO_ROOT)}")

    total_files  = len(examples)
    passed_files = 0
    all_messages = []

    for path in examples:
        rel = path.relative_to(REPO_ROOT) if REPO_ROOT in path.parents else path
        print(f"\n{'─'*60}")
        print(f"{C.BOLD}{rel}{C.RESET}")

        try:
            with open(path) as f:
                log = json.load(f)
        except json.JSONDecodeError as e:
            print(fail(f"  Invalid JSON: {e}"))
            all_messages.append(f"FAIL {rel}: invalid JSON")
            continue

        # ── 1. JSON Schema validation
        schema_ok, schema_msgs = validate_against_schema(log, schema, str(rel))
        for m in schema_msgs:
            print(m)
        if schema_ok:
            print(ok(f"  JSON Schema: valid"))
        else:
            print(fail(f"  JSON Schema: {len(schema_msgs)} error(s)"))

        # ── 2. Hash chain verification
        chain_ok, chain_msgs = verify_hash_chain(log, verbose=args.verbose)
        for m in chain_msgs:
            print(m)
        if chain_ok:
            print(ok(f"  Hash chain: intact ({len(log.get('events',[]))} events)"))

        # ── 3. Structural sanity checks
        events = log.get("events", [])
        sanity_ok = True
        if not events:
            print(warn("  No events in log"))
        else:
            if events[0].get("type") != "session_start":
                print(warn("  First event is not session_start"))
                sanity_ok = False
            if events[-1].get("type") != "session_end":
                print(warn("  Last event is not session_end"))
                sanity_ok = False
            # Check chronological ordering
            timestamps = [e.get("timestamp", "") for e in events]
            if timestamps != sorted(timestamps):
                print(fail("  Events are not in chronological order"))
                sanity_ok = False
            elif args.verbose:
                print(ok(f"  Timestamps: chronological"))

        file_ok = schema_ok and chain_ok and sanity_ok
        if file_ok:
            passed_files += 1
            all_messages.append(f"PASS {rel}")
        else:
            all_messages.append(f"FAIL {rel}")

        # ── 4. --fix mode: write hash chain back
        if args.fix:
            log = add_hash_chain(log)
            with open(path, "w") as f:
                json.dump(log, f, indent=2)
            print(f"{C.CYAN}  → Hash chain written to {rel}{C.RESET}")

    # ── Summary ──
    print(f"\n{'═'*60}")
    print(head("Summary"))
    for m in all_messages:
        colour = C.GREEN if m.startswith("PASS") else C.RED
        print(f"  {colour}{m}{C.RESET}")
    print()

    if passed_files == total_files:
        print(ok(f"{passed_files}/{total_files} files passed all checks."))
        return 0
    else:
        failed = total_files - passed_files
        print(fail(f"{failed}/{total_files} files failed. See above for details."))
        return 1


if __name__ == "__main__":
    sys.exit(main())
