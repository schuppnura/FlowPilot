#!/usr/bin/env python3
"""
seed_keycloak_users.py

Create/update users in a Keycloak realm from a semicolon-delimited CSV file.

.env support (simple parser, no extra deps):
- Reads KEYCLOAK_ADMIN and KEYCLOAK_ADMIN_PASSWORD from .env

Precedence:
- CLI args override .env
- .env overrides process environment variables

Assumptions / expectations:
- Keycloak is reachable at config["keycloak"]["base_url"]
- Admin token is requested from the "master" realm using "admin-cli"
- CSV columns: username;password;email;firstname;lastname;autobook_consent
  (autobook_consent is optional, defaults to "Yes" if missing)

Side effects:
- Creates users in the configured target realm.
- Resets passwords for the listed users.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


@dataclass(frozen=True)
class KeycloakConfig:
    base_url: str
    target_realm: str
    verify_tls: bool


@dataclass(frozen=True)
class SeedUser:
    username: str
    password: str
    email: str
    first_name: str
    last_name: str
    autobook_consent: str  # "Yes" or "No"
    autobook_price: str  # Max price in EUR (e.g., "5000")
    autobook_leadtime: str  # Minimum lead time in days (e.g., "1")
    autobook_risklevel: str  # Max risk level (e.g., "10")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed Keycloak users into the configured realm (FlowPilot)."
    )
    parser.add_argument(
        "--config",
        default="/mnt/data/provision_config.json",
        help="Path to provision_config.json (default: /mnt/data/provision_config.json)",
    )
    parser.add_argument(
        "--csv",
        default="/mnt/data/users_seed.csv",
        help="Path to users CSV (default: /mnt/data/users_seed.csv)",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help='Path to .env file (default: ".env")',
    )
    parser.add_argument(
        "--admin-username",
        default="",
        help="Keycloak admin username (overrides .env / environment if set)",
    )
    parser.add_argument(
        "--admin-password",
        default="",
        help="Keycloak admin password (overrides .env / environment if set)",
    )
    parser.add_argument(
        "--admin-realm",
        default="master",
        help='Realm to authenticate against for admin token (default: "master")',
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="If set, do not call Keycloak; only print intended actions.",
    )
    return parser.parse_args()


def load_dotenv_file(path: str) -> Dict[str, str]:
    """
    Minimal .env parser:
    - Supports lines: KEY=VALUE
    - Ignores empty lines and comments starting with '#'
    - Strips optional surrounding single/double quotes from VALUE
    - Does not expand variables
    """
    values: Dict[str, str] = {}
    if not path or not os.path.exists(path):
        return values

    with open(path, "r", encoding="utf-8") as file_handle:
        for raw_line in file_handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]

            if key:
                values[key] = value

    return values


def resolve_admin_credentials(
    args: argparse.Namespace, dotenv_values: Dict[str, str]
) -> tuple[str, str]:
    admin_username = (args.admin_username or "").strip()
    admin_password = (args.admin_password or "").strip()

    if not admin_username:
        admin_username = (dotenv_values.get("KEYCLOAK_ADMIN") or "").strip()
    if not admin_username:
        admin_username = (dotenv_values.get("KEYCLOAK_ADMIN_USERNAME") or "").strip()
    if not admin_username:
        admin_username = (os.environ.get("KEYCLOAK_ADMIN") or "").strip()
    if not admin_username:
        admin_username = (os.environ.get("KEYCLOAK_ADMIN_USERNAME") or "").strip()

    if not admin_password:
        admin_password = (dotenv_values.get("KEYCLOAK_ADMIN_PASSWORD") or "").strip()
    if not admin_password:
        admin_password = (os.environ.get("KEYCLOAK_ADMIN_PASSWORD") or "").strip()

    return admin_username, admin_password


def load_json_with_trailing_commas(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as file_handle:
        raw_text = file_handle.read()

    sanitized_text = re.sub(r",\s*([}\]])", r"\1", raw_text)

    try:
        parsed = json.loads(sanitized_text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in config (even after sanitizing): {error}") from error

    if not isinstance(parsed, dict):
        raise ValueError("Config JSON root must be an object.")
    return parsed


def parse_keycloak_config(config_data: Dict[str, Any]) -> KeycloakConfig:
    keycloak_section = config_data.get("keycloak")
    if not isinstance(keycloak_section, dict):
        raise ValueError('Config must contain object: "keycloak".')

    base_url = str(keycloak_section.get("base_url", "")).strip().rstrip("/")
    target_realm = str(keycloak_section.get("target_realm", "")).strip()
    verify_tls = bool(keycloak_section.get("verify_tls", True))

    if not base_url:
        raise ValueError("Missing config: keycloak.base_url")
    if not target_realm:
        raise ValueError("Missing config: keycloak.target_realm")

    return KeycloakConfig(base_url=base_url, target_realm=target_realm, verify_tls=verify_tls)


def load_users_from_csv(path: str) -> List[SeedUser]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"CSV file not found: {path}")

    users: List[SeedUser] = []
    with open(path, "r", encoding="utf-8") as file_handle:
        reader = csv.DictReader(file_handle, delimiter=";")
        expected_fields = ["username", "password", "email", "firstname", "lastname"]
        optional_fields = ["autobook_consent", "autobook_price", "autobook_leadtime", "autobook_risklevel"]
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row.")
        
        # Normalize field names (strip whitespace, handle variations)
        normalized_fieldnames = {field.strip(): field for field in reader.fieldnames}
        
        # Check for required fields (case-insensitive, whitespace-tolerant)
        missing_fields = []
        for expected in expected_fields:
            found = False
            for actual in normalized_fieldnames.keys():
                if actual.lower().strip() == expected.lower():
                    found = True
                    break
            if not found:
                missing_fields.append(expected)
        
        if missing_fields:
            raise ValueError(f"CSV is missing required columns: {missing_fields}. Found columns: {list(reader.fieldnames)}")

        for row_index, row in enumerate(reader, start=2):
            # Get values with case-insensitive, whitespace-tolerant lookup
            username = _get_field_value(row, "username", normalized_fieldnames)
            password = _get_field_value(row, "password", normalized_fieldnames)
            email = _get_field_value(row, "email", normalized_fieldnames)
            first_name = _get_field_value(row, "firstname", normalized_fieldnames)
            last_name = _get_field_value(row, "lastname", normalized_fieldnames)
            autobook_consent = _get_field_value(row, "autobook_consent", normalized_fieldnames, default="Yes")
            autobook_price = _get_field_value(row, "autobook_price", normalized_fieldnames, default="1500")
            autobook_leadtime = _get_field_value(row, "autobook_leadtime", normalized_fieldnames, default="7")
            autobook_risklevel = _get_field_value(row, "autobook_risklevel", normalized_fieldnames, default="2")

            if not username:
                raise ValueError(f"Row {row_index}: username is empty.")
            if not password:
                raise ValueError(f"Row {row_index}: password is empty.")
            # Email, first_name, last_name are now optional
            # if not email:
            #     raise ValueError(f"Row {row_index}: email is empty.")
            
            # Normalize consent value
            consent_normalized = autobook_consent.strip()
            if consent_normalized.lower() not in ("yes", "no", "true", "false", "1", "0"):
                print(f"Warning: Row {row_index}: autobook_consent='{consent_normalized}' is not Yes/No, defaulting to 'Yes'")
                consent_normalized = "Yes"
            else:
                # Map to Yes/No
                if consent_normalized.lower() in ("yes", "true", "1"):
                    consent_normalized = "Yes"
                else:
                    consent_normalized = "No"

            users.append(
                SeedUser(
                    username=username,
                    password=password,
                    email=email or "",
                    first_name=first_name or "",
                    last_name=last_name or "",
                    autobook_consent=consent_normalized,
                    autobook_price=autobook_price.strip(),
                    autobook_leadtime=autobook_leadtime.strip(),
                    autobook_risklevel=autobook_risklevel.strip(),
                )
            )

    return users


def _get_field_value(
    row: Dict[str, str], 
    field_name: str, 
    normalized_fieldnames: Dict[str, str],
    default: str = ""
) -> str:
    """Get field value from CSV row with case-insensitive, whitespace-tolerant lookup."""
    # Try exact match first
    if field_name in row:
        return (row[field_name] or "").strip() or default
    
    # Try normalized lookup (case-insensitive, whitespace-tolerant)
    for normalized, original in normalized_fieldnames.items():
        if normalized.lower().strip() == field_name.lower():
            return (row.get(original) or "").strip() or default
    
    return default


def request_admin_token(
    base_url: str,
    admin_realm: str,
    admin_username: str,
    admin_password: str,
    verify_tls: bool,
) -> str:
    if not admin_username or not admin_password:
        raise ValueError(
            "Admin credentials missing. Provide --admin-username/--admin-password, "
            "or set KEYCLOAK_ADMIN and KEYCLOAK_ADMIN_PASSWORD in .env / environment."
        )

    token_url = f"{base_url}/realms/{admin_realm}/protocol/openid-connect/token"
    form_data = {
        "grant_type": "password",
        "client_id": "admin-cli",
        "username": admin_username,
        "password": admin_password,
    }

    response = requests.post(token_url, data=form_data, timeout=30, verify=verify_tls)
    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to obtain admin token ({response.status_code}). Response: {response.text}"
        )

    token_data = response.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise RuntimeError("Token response did not contain access_token.")
    return str(access_token)


def find_user_id(
    session: requests.Session,
    base_url: str,
    realm: str,
    username: str,
    verify_tls: bool,
) -> Optional[str]:
    search_url = f"{base_url}/admin/realms/{realm}/users?username={requests.utils.quote(username)}"
    response = session.get(search_url, timeout=30, verify=verify_tls)
    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to search user '{username}' ({response.status_code}): {response.text}"
        )

    items = response.json()
    if not isinstance(items, list):
        raise RuntimeError(f"Unexpected search response for '{username}': {response.text}")

    for item in items:
        if isinstance(item, dict) and item.get("username") == username and item.get("id"):
            return str(item["id"])

    return None


def create_user(
    session: requests.Session,
    base_url: str,
    realm: str,
    user: SeedUser,
    verify_tls: bool,
) -> str:
    create_url = f"{base_url}/admin/realms/{realm}/users"
    payload = {
        "username": user.username,
        "enabled": True,
    }
    # Email, firstName, lastName are optional
    if user.email:
        payload["email"] = user.email
        payload["emailVerified"] = True
    if user.first_name:
        payload["firstName"] = user.first_name
    if user.last_name:
        payload["lastName"] = user.last_name

    response = session.post(create_url, json=payload, timeout=30, verify=verify_tls)

    if response.status_code == 201:
        location = response.headers.get("Location", "")
        user_id = location.rstrip("/").split("/")[-1].strip()
        if user_id:
            return user_id
        found_id = find_user_id(session, base_url, realm, user.username, verify_tls)
        if found_id:
            return found_id
        raise RuntimeError(f"User created but could not determine id for '{user.username}'.")

    if response.status_code == 409:
        found_id = find_user_id(session, base_url, realm, user.username, verify_tls)
        if found_id:
            return found_id
        raise RuntimeError(f"User '{user.username}' already exists but id lookup failed.")

    raise RuntimeError(
        f"Failed to create user '{user.username}' ({response.status_code}): {response.text}"
    )


def update_user_profile(
    session: requests.Session,
    base_url: str,
    realm: str,
    user_id: str,
    user: SeedUser,
    verify_tls: bool,
) -> None:
    update_url = f"{base_url}/admin/realms/{realm}/users/{user_id}"
    # Fetch current user data to preserve existing attributes
    response = session.get(update_url, timeout=30, verify=verify_tls)
    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to get user data for '{user.username}' ({response.status_code}): {response.text}"
        )
    
    user_data = response.json()
    # Update only the fields we want to change, preserving attributes
    user_data["username"] = user.username
    user_data["enabled"] = True
    # Email, firstName, lastName are optional
    if user.email:
        user_data["email"] = user.email
        user_data["emailVerified"] = True
    elif "email" in user_data:
        # Keep existing email if not provided
        pass
    if user.first_name:
        user_data["firstName"] = user.first_name
    elif "firstName" in user_data:
        # Keep existing firstName if not provided
        pass
    if user.last_name:
        user_data["lastName"] = user.last_name
    elif "lastName" in user_data:
        # Keep existing lastName if not provided
        pass
    
    response = session.put(update_url, json=user_data, timeout=30, verify=verify_tls)
    if response.status_code != 204:
        raise RuntimeError(
            f"Failed to update profile for '{user.username}' ({response.status_code}): {response.text}"
        )


def reset_user_password(
    session: requests.Session,
    base_url: str,
    realm: str,
    user_id: str,
    password: str,
    verify_tls: bool,
) -> None:
    reset_url = f"{base_url}/admin/realms/{realm}/users/{user_id}/reset-password"
    payload = {"type": "password", "value": password, "temporary": False}
    response = session.put(reset_url, json=payload, timeout=30, verify=verify_tls)
    if response.status_code != 204:
        raise RuntimeError(
            f"Failed to reset password for user_id={user_id} ({response.status_code}): {response.text}"
        )


def set_user_autobook_attributes(
    session: requests.Session,
    base_url: str,
    realm: str,
    user_id: str,
    user: SeedUser,
    verify_tls: bool,
) -> None:
    """Set all autobook-related attributes for a user."""
    update_url = f"{base_url}/admin/realms/{realm}/users/{user_id}"
    # Fetch current user data first
    response = session.get(update_url, timeout=30, verify=verify_tls)
    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to get user data for user_id={user_id} ({response.status_code}): {response.text}"
        )
    
    user_data = response.json()
    # Initialize attributes if not present
    if "attributes" not in user_data or user_data["attributes"] is None:
        user_data["attributes"] = {}
    
    # Set the attributes
    user_data["attributes"]["autobook_consent"] = [user.autobook_consent]
    user_data["attributes"]["autobook_price"] = [user.autobook_price]
    user_data["attributes"]["autobook_leadtime"] = [user.autobook_leadtime]
    user_data["attributes"]["autobook_risklevel"] = [user.autobook_risklevel]
    
    # Remove read-only fields that Keycloak doesn't accept in PUT
    for field in ["access", "createdTimestamp", "totp", "disableableCredentialTypes", "requiredActions", "notBefore"]:
        user_data.pop(field, None)
    
    # Update user with new attributes
    response = session.put(update_url, json=user_data, timeout=30, verify=verify_tls)
    if response.status_code != 204:
        raise RuntimeError(
            f"Failed to set autobook attributes for user_id={user_id} ({response.status_code}): {response.text}"
        )
    
    # Verify the attributes were set
    verify_response = session.get(update_url, timeout=30, verify=verify_tls)
    if verify_response.status_code == 200:
        verified_user = verify_response.json()
        verified_attrs = verified_user.get("attributes") or {}
        if not verified_attrs.get("autobook_consent"):
            # Attributes didn't persist - this might be a Keycloak configuration issue
            print(f"Warning: Attributes for {user.username} may not have persisted. Keycloak may require 'Unmanaged Attributes' to be enabled.")


def seed_users(
    keycloak_config: KeycloakConfig,
    admin_realm: str,
    admin_username: str,
    admin_password: str,
    users: List[SeedUser],
    is_dry_run: bool,
) -> None:
    if is_dry_run:
        print("DRY RUN: No calls will be made to Keycloak.")
        print(f"Target: {keycloak_config.base_url} realm={keycloak_config.target_realm}")
        for user in users:
            print(f"- Would create/update user '{user.username}' and set password.")
        return

    access_token = request_admin_token(
        base_url=keycloak_config.base_url,
        admin_realm=admin_realm,
        admin_username=admin_username,
        admin_password=admin_password,
        verify_tls=keycloak_config.verify_tls,
    )

    session = requests.Session()
    session.headers.update(
        {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    )

    created_count = 0
    updated_count = 0

    for user in users:
        existing_id = find_user_id(
            session=session,
            base_url=keycloak_config.base_url,
            realm=keycloak_config.target_realm,
            username=user.username,
            verify_tls=keycloak_config.verify_tls,
        )

        if existing_id:
            user_id = existing_id
            update_user_profile(
                session=session,
                base_url=keycloak_config.base_url,
                realm=keycloak_config.target_realm,
                user_id=user_id,
                user=user,
                verify_tls=keycloak_config.verify_tls,
            )
            updated_count += 1
        else:
            user_id = create_user(
                session=session,
                base_url=keycloak_config.base_url,
                realm=keycloak_config.target_realm,
                user=user,
                verify_tls=keycloak_config.verify_tls,
            )
            created_count += 1

        reset_user_password(
            session=session,
            base_url=keycloak_config.base_url,
            realm=keycloak_config.target_realm,
            user_id=user_id,
            password=user.password,
            verify_tls=keycloak_config.verify_tls,
        )

        # Set all autobook-related attributes from CSV
        try:
            set_user_autobook_attributes(
                session=session,
                base_url=keycloak_config.base_url,
                realm=keycloak_config.target_realm,
                user_id=user_id,
                user=user,
                verify_tls=keycloak_config.verify_tls,
            )
        except Exception as exc:
            print(f"Warning: Failed to set autobook attributes for {user.username}: {exc}")
            # Continue anyway

        print(f"OK: {user.username} (id={user_id})")

    print("")
    print("Summary")
    print(f"Created: {created_count}")
    print(f"Updated: {updated_count}")
    print(f"Total:   {len(users)}")


def main() -> int:
    args = parse_arguments()

    dotenv_values = load_dotenv_file(args.env_file)
    admin_username, admin_password = resolve_admin_credentials(args, dotenv_values)

    config_data = load_json_with_trailing_commas(args.config)
    keycloak_config = parse_keycloak_config(config_data)
    users = load_users_from_csv(args.csv)

    seed_users(
        keycloak_config=keycloak_config,
        admin_realm=args.admin_realm,
        admin_username=admin_username,
        admin_password=admin_password,
        users=users,
        is_dry_run=bool(args.dry_run),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())