#!/usr/bin/env python3

import argparse
import pathlib
import sys
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class ReplacementResult:
    file_path: pathlib.Path
    changed: bool
    replacements: List[Tuple[str, str, int]]  # (old, new, count)


def parse_arguments() -> argparse.Namespace:
    # Parse CLI arguments; why: keep usage explicit and support dry-run vs apply.
    parser = argparse.ArgumentParser(description="Rename Cumbaya tokens in Python code to FlowPilot tokens.")
    parser.add_argument("--root", default=".", help="Repo root (default: current directory).")
    parser.add_argument("--apply", action="store_true", help="Apply changes in-place. Default is dry-run.")
    parser.add_argument("--include-root-utils", action="store_true", help="Also process ./utils.py if present.")
    return parser.parse_args()


def build_replacements() -> List[Tuple[str, str]]:
    # Define replacements; why: keep mapping deterministic and easy to audit/change.
    # Assumptions: you want to eliminate 'cumbaya' branding from Python code.
    # Side effects: none (data only).
    return [
        # Case-aware generic rename
        ("cumbaya", "flowpilot"),
        ("Cumbaya", "FlowPilot"),
        ("CUMBAYA", "FLOWPILOT"),

        # Common demo identifiers
        ("agent_cumbaya_1", "agent_flowpilot_1"),
        ("cumbaya-agent", "flowpilot-agent"),

        # Keycloak realm path fragments often embedded in URLs
        ("/realms/cumbaya/", "/realms/flowpilot/"),
        ("/realms/cumbaya", "/realms/flowpilot"),

        # If any code still references the old docker hostname (adjust if you chose different service keys)
        ("http://cumbaya-api:", "http://flowpilot-services-api:"),
        ("http://cumbaya-api", "http://flowpilot-services-api"),

        # If any code references authz-api hostname and you renamed the service (adjust if needed)
        ("http://authz-api:", "http://flowpilot-authz-api:"),
        ("http://authz-api", "http://flowpilot-authz-api"),
    ]


def list_python_files(repo_root: pathlib.Path, include_root_utils: bool) -> List[pathlib.Path]:
    # Discover Python files; why: ensure we only touch .py, not yaml/json/swift.
    # Assumptions: Python lives under ./services plus optional repo-root utils.py.
    file_paths: List[pathlib.Path] = []
    services_dir = repo_root / "services"
    if services_dir.exists():
        file_paths.extend(sorted(services_dir.rglob("*.py")))

    if include_root_utils:
        root_utils = repo_root / "utils.py"
        if root_utils.exists():
            file_paths.append(root_utils)

    return file_paths


def replace_in_text(original_text: str, replacements: List[Tuple[str, str]]) -> Tuple[str, List[Tuple[str, str, int]]]:
    # Apply replacement mapping in-order; why: stable output for review and reproducibility.
    updated_text = original_text
    applied: List[Tuple[str, str, int]] = []
    for old, new in replacements:
        count = updated_text.count(old)
        if count > 0:
            updated_text = updated_text.replace(old, new)
            applied.append((old, new, count))
    return updated_text, applied


def process_file(file_path: pathlib.Path, replacements: List[Tuple[str, str]], apply: bool) -> ReplacementResult:
    # Process one file; why: isolate IO per file and keep error handling clear.
    # Side effects: writes file only if apply=True and content changed.
    original_text = file_path.read_text(encoding="utf-8")
    updated_text, applied = replace_in_text(original_text, replacements)
    changed = updated_text != original_text

    if apply and changed:
        file_path.write_text(updated_text, encoding="utf-8")

    return ReplacementResult(file_path=file_path, changed=changed, replacements=applied)


def print_summary(results: List[ReplacementResult], apply: bool) -> None:
    # Print a human-auditable summary; why: you can verify before rebuilding containers.
    mode = "APPLIED" if apply else "DRY-RUN"
    print(f"{mode}: processed {len(results)} file(s)")

    changed_files = [r for r in results if r.changed]
    print(f"{mode}: changed {len(changed_files)} file(s)")

    for result in changed_files:
        print(f"- {result.file_path}")
        for old, new, count in result.replacements:
            print(f"  - {old} -> {new} (x{count})")


def main() -> int:
    # Orchestrate the rename run; why: single entry point with explicit exit codes.
    args = parse_arguments()
    repo_root = pathlib.Path(args.root).resolve()

    if not repo_root.exists():
        print(f"ERROR: root does not exist: {repo_root}", file=sys.stderr)
        return 2

    replacements = build_replacements()
    file_paths = list_python_files(repo_root=repo_root, include_root_utils=args.include_root_utils)

    results: List[ReplacementResult] = []
    for file_path in file_paths:
        try:
            results.append(process_file(file_path=file_path, replacements=replacements, apply=bool(args.apply)))
        except UnicodeDecodeError as exception:
            print(f"ERROR: failed to read UTF-8: {file_path}: {exception}", file=sys.stderr)
            return 3

    print_summary(results=results, apply=bool(args.apply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())