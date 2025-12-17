#!/usr/bin/env python3

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class ReplacementRule:
    name: str
    pattern: str
    replacement: str
    flags: int = 0


def parse_arguments() -> argparse.Namespace:
    # Parse CLI flags; why: allow dry-run by default and a deliberate --apply for writes.
    parser = argparse.ArgumentParser(
        prog="rename_flowpilot_authz_vocab",
        description="Rename legacy AuthZ vocabulary (itinerary/can_book) to workflow/can_execute within flowpilot-authz-api.",
    )
    parser.add_argument(
        "--path",
        default="services/flowpilot-authz-api",
        help="Root directory to scan (default: services/flowpilot-authz-api).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to disk. If omitted, runs in dry-run mode.",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="When used with --apply, write <file>.bak before overwriting.",
    )
    parser.add_argument(
        "--include",
        default=r"\.py$",
        help="Regex for file names to include (default: \\.py$).",
    )
    parser.add_argument(
        "--exclude",
        default=r"(__pycache__|\.venv|\.git|\.pytest_cache)",
        help="Regex for paths to exclude.",
    )
    return parser.parse_args()


def collect_target_files(root_path: Path, include_regex: str, exclude_regex: str) -> List[Path]:
    # Collect files to modify; why: keep the script predictable and scoped to intended sources only.
    include_pattern = re.compile(include_regex)
    exclude_pattern = re.compile(exclude_regex)

    if not root_path.exists():
        raise ValueError(f"Target path does not exist: {root_path}")

    target_files: List[Path] = []
    for path in root_path.rglob("*"):
        if not path.is_file():
            continue
        string_path = str(path)
        if exclude_pattern.search(string_path):
            continue
        if include_pattern.search(path.name):
            target_files.append(path)

    return sorted(target_files)


def read_text_file(file_path: Path) -> str:
    # Read file content; why: apply transformations in-memory and write only when needed.
    return file_path.read_text(encoding="utf-8")


def write_text_file(file_path: Path, content: str) -> None:
    # Write file content; side effect: overwrites file on disk.
    file_path.write_text(content, encoding="utf-8")


def build_replacement_rules() -> List[ReplacementRule]:
    # Define replacement rules; why: keep changes explicit, reviewable, and easy to extend.
    return [
        ReplacementRule(
            name="***REMOVED*** object_type string itinerary_item -> workflow_item",
            pattern=r'(["\']object_type["\']\s*:\s*["\'])itinerary_item(["\'])',
            replacement=r"\1workflow_item\2",
        ),
        ReplacementRule(
            name="***REMOVED*** object_type kwarg itinerary_item -> workflow_item",
            pattern=r'(object_type\s*=\s*["\'])itinerary_item(["\'])',
            replacement=r"\1workflow_item\2",
        ),
        ReplacementRule(
            name="Standalone type string itinerary_item -> workflow_item",
            pattern=r'(["\'])itinerary_item(["\'])',
            replacement=r"\1workflow_item\2",
        ),
        ReplacementRule(
            name="can_book -> can_execute (quoted)",
            pattern=r'(["\'])can_book(["\'])',
            replacement=r"\1can_execute\2",
        ),
        ReplacementRule(
            name="Legacy field itinerary_item_id -> workflow_item_id (quoted)",
            pattern=r'(["\'])itinerary_item_id(["\'])',
            replacement=r"\1workflow_item_id\2",
        ),
        ReplacementRule(
            name="Manifest path trip->owner->delegate -> workflow->owner->delegate",
            pattern=r"trip->owner->delegate",
            replacement="workflow->owner->delegate",
        ),
    ]


def normalize_workflow_item_id_property_names(text: str) -> Tuple[str, int]:
    # Normalize ID property names list; why: replacements can create duplicates and we want deterministic config.
    # This targets the specific config line:
    # "workflow_item_id_property_names": ["workflow_item_id", "itinerary_item_id", "item_id"],
    pattern = re.compile(
        r'("workflow_item_id_property_names"\s*:\s*)\[(.*?)\]',
        flags=re.DOTALL,
    )

    match = pattern.search(text)
    if not match:
        return text, 0

    prefix = match.group(1)
    inside = match.group(2)

    # Extract quoted strings in order and dedupe while preserving order.
    candidates = re.findall(r'["\']([^"\']+)["\']', inside)
    deduped: List[str] = []
    seen: set = set()
    for value in candidates:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)

    # Enforce the intended modern set/order for this project.
    intended = ["workflow_item_id", "item_id"]
    for value in deduped:
        if value not in intended and value.endswith("_id"):
            # Keep any extra id-like fields after the intended ones if present.
            intended.append(value)
        if value not in intended and not value.endswith("_id"):
            intended.append(value)

    normalized = prefix + "[" + ", ".join([f'"{value}"' for value in intended]) + "]"
    new_text = text[: match.start()] + normalized + text[match.end() :]

    return new_text, 1


def apply_rules_to_text(text: str, rules: List[ReplacementRule]) -> Tuple[str, Dict[str, int]]:
    # Apply all rules; why: provide a per-rule count so you can verify exactly what changed.
    counts: Dict[str, int] = {}
    updated = text

    for rule in rules:
        updated, count = re.subn(rule.pattern, rule.replacement, updated, flags=rule.flags)
        counts[rule.name] = count

    updated, normalized_count = normalize_workflow_item_id_property_names(updated)
    counts["Normalize workflow_item_id_property_names list"] = normalized_count

    return updated, counts


def format_counts(counts: Dict[str, int]) -> str:
    # Format counts for logging; why: make it easy to review in terminal output.
    lines: List[str] = []
    total = 0
    for name in sorted(counts.keys()):
        count = counts[name]
        total += count
        if count > 0:
            lines.append(f"  - {name}: {count}")
    if total == 0:
        return "  - no matches"
    return "\n".join(lines)


def process_files(files: List[Path], rules: List[ReplacementRule], apply: bool, backup: bool) -> int:
    # Process all files; side effect: writes changes when apply=True.
    changed_files = 0

    for file_path in files:
        original = read_text_file(file_path)
        updated, counts = apply_rules_to_text(original, rules)

        if updated == original:
            continue

        changed_files += 1
        print(f"\nFILE: {file_path}")
        print(format_counts(counts))

        if apply:
            if backup:
                backup_path = file_path.with_suffix(file_path.suffix + ".bak")
                write_text_file(backup_path, original)
            write_text_file(file_path, updated)

    return changed_files


def main() -> int:
    # Orchestrate the rename operation; why: centralizes validation, reporting, and exit codes.
    args = parse_arguments()

    root_path = Path(args.path).resolve()
    files = collect_target_files(
        root_path=root_path,
        include_regex=args.include,
        exclude_regex=args.exclude,
    )

    rules = build_replacement_rules()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"Mode: {mode}")
    print(f"Target path: {root_path}")
    print(f"Files matched: {len(files)}")

    changed_files = process_files(files=files, rules=rules, apply=args.apply, backup=args.backup)

    print(f"\nChanged files: {changed_files}")
    if not args.apply:
        print("Dry-run complete. Re-run with --apply to write changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())