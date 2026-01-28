# FlowPilot Services API - Template Loader
#
# Template loading and validation utilities for the domain backend.
# Loads workflow templates from JSON files and validates their structure.
#
# This is domain-specific code for the travel demo. Other domains would have
# different template structures and validation rules.

from __future__ import annotations

import json
import os
from typing import Any, Dict, List


def load_json_file(file_path: str) -> dict[str, Any]:
    # Load a JSON file and return it as an object.
    # Assumptions: file contains UTF-8 JSON
    # root is an object.
    # Side effects: reads filesystem.
    try:
        with open(file_path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exception:
        raise ValueError(f"Template file not found: {file_path}") from exception
    except json.JSONDecodeError as exception:
        raise ValueError(f"Template file is not valid JSON: {file_path}") from exception

    if not isinstance(data, dict):
        raise ValueError(f"Template file root must be a JSON object: {file_path}")

    return data


def list_template_files(template_directory: str) -> list[str]:
    # List template JSON files in a directory in deterministic order.
    # Assumptions: template_directory exists.
    # Side effects: reads directory entries.
    entries = os.listdir(template_directory)
    json_files: list[str] = []
    for entry in entries:
        if entry.lower().endswith(".json"):
            json_files.append(os.path.join(template_directory, entry))
    json_files.sort()
    return json_files


def validate_money(money: Any, context: str) -> None:
    # Validate a minimal money object with currency and amount.
    # Assumptions: currency conversion is out of scope.
    # Side effects: none.
    if not isinstance(money, dict):
        raise ValueError(f"{context}: planned_price must be an object")

    currency = money.get("currency")
    amount = money.get("amount")

    if not isinstance(currency, str) or len(currency) != 3:
        raise ValueError(f"{context}: planned_price.currency must be a 3-letter string")

    if not isinstance(amount, (int, float)) or float(amount) < 0.0:
        raise ValueError(
            f"{context}: planned_price.amount must be a non-negative number"
        )


def validate_template_item(item: Any, index: int, file_path: str) -> None:
    # Validate a single item in a template to protect against rogue inputs.
    # Assumptions: each item needs a type and a planned_price.
    # Side effects: none.
    if not isinstance(item, dict):
        raise ValueError(f"{file_path}: items[{index}] must be an object")

    item_type = item.get("type")
    if not isinstance(item_type, str) or not item_type.strip():
        raise ValueError(f"{file_path}: items[{index}].type must be a non-empty string")

    planned_price = item.get("planned_price")
    validate_money(planned_price, context=f"{file_path}: items[{index}]")


def validate_template(template: dict[str, Any], domain: str, file_path: str) -> None:
    # Validate a template structure and enforce the domain constraint.
    # Assumptions: template domain must equal service domain to keep demos isolated.
    # Side effects: none.
    template_id = template.get("template_id")
    template_domain = template.get("domain")
    name = template.get("name")
    items = template.get("items")

    if not isinstance(template_id, str) or not template_id.strip():
        raise ValueError(f"{file_path}: template_id must be a non-empty string")

    if template_domain != domain:
        raise ValueError(
            f"{file_path}: domain mismatch: got '{template_domain}', expected '{domain}'"
        )

    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{file_path}: name must be a non-empty string")

    if not isinstance(items, list) or len(items) == 0:
        raise ValueError(f"{file_path}: items must be a non-empty array")

    for index, item in enumerate(items):
        validate_template_item(item=item, index=index, file_path=file_path)


def load_workflow_templates_from_directory(
    template_directory: str, domain: str
) -> dict[str, dict[str, Any]]:
    # Load and validate templates from a directory into a dict keyed by template_id.
    # Assumptions: template_directory exists and contains at least one .json file.
    # Side effects: reads filesystem.
    if not os.path.isdir(template_directory):
        raise ValueError(
            f"Template directory does not exist or is not a directory: {template_directory}"
        )

    templates: dict[str, dict[str, Any]] = {}
    template_files = list_template_files(template_directory)

    if len(template_files) == 0:
        raise ValueError(
            f"No .json template files found in directory: {template_directory}"
        )

    for file_path in template_files:
        template = load_json_file(file_path)
        validate_template(template=template, domain=domain, file_path=file_path)

        template_id = str(template["template_id"])
        if template_id in templates:
            raise ValueError(
                f"Duplicate template_id '{template_id}' found (file: {file_path})"
            )

        templates[template_id] = template

    return templates


def resolve_template_directory(
    default_directory: str, override_directory: str | None
) -> str:
    # Resolve the template directory where CLI override takes precedence over defaults.
    # Assumptions: override_directory may be None or empty.
    # Side effects: none.
    if override_directory is not None and override_directory.strip():
        return override_directory.strip()
    return default_directory
