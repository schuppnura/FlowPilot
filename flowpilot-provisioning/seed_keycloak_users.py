#!/usr/bin/env python3
"""
seed_keycloak_users.py

Create/update users in Keycloak and create personas via persona-api.
Personas are no longer stored as Keycloak attributes - they are managed via persona-api.

CSV columns: username;password;email;firstname;lastname;persona;consent;autobook_price;autobook_leadtime;autobook_risklevel
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from dataclasses import dataclass
from typing import List, Optional
import requests
import urllib3

# Disable SSL warnings for local development
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass(frozen=True)
class SeedUser:
    username: str
    password: str
    email: str
    first_name: str
    last_name: str
    persona_titles: List[str]  # List of persona titles (e.g., ["traveler", "travel-agent"])
    consent: bool  # True or False
    autobook_price: int  # Max price in EUR (e.g., 5000)
    autobook_leadtime: int  # Minimum lead time in days (e.g., 1)
    autobook_risklevel: int  # Max risk level 0-100 (e.g., 10)
    persona_status: str  # Persona status ("active", "inactive", etc.)
    persona_valid_from: str  # ISO 8601 timestamp
    persona_valid_till: str  # ISO 8601 timestamp


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed Keycloak users and create personas via persona-api."
    )
    parser.add_argument(
        "--csv",
        default="flowpilot-provisioning/users_seed.csv",
        help="Path to users CSV (default: flowpilot-provisioning/users_seed.csv)",
    )
    parser.add_argument(
        "--keycloak-url",
        default="https://localhost:8443",
        help="Keycloak base URL (default: https://localhost:8443)",
    )
    parser.add_argument(
        "--realm",
        default="flowpilot",
        help="Keycloak realm (default: flowpilot)",
    )
    parser.add_argument(
        "--admin-user",
        default="admin",
        help="Keycloak admin username (default: admin)",
    )
    parser.add_argument(
        "--admin-password",
        help="Keycloak admin password (from KEYCLOAK_ADMIN_PASSWORD env var if not provided)",
    )
    parser.add_argument(
        "--profile-api-url",
        default="http://localhost:8006",
        help="User Profile API URL (default: http://localhost:8006)",
    )
    parser.add_argument(
        "--client-id",
        default="flowpilot-desktop",
        help="Client ID for user authentication (default: flowpilot-desktop)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="If set, do not call Keycloak or persona-api; only print intended actions.",
    )
    return parser.parse_args()


def load_users_from_csv(path: str) -> List[SeedUser]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"CSV file not found: {path}")

    users: List[SeedUser] = []
    with open(path, "r", encoding="utf-8") as file_handle:
        reader = csv.DictReader(file_handle, delimiter=";")
        
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row.")
        
        for row_index, row in enumerate(reader, start=2):
            username = (row.get("username") or "").strip()
            password = (row.get("password") or "").strip()
            email = (row.get("email") or "").strip()
            first_name = (row.get("firstname") or "").strip()
            last_name = (row.get("lastname") or "").strip()
            
            # Parse persona titles (comma-separated list)
            persona_raw = (row.get("persona") or "").strip()
            persona_titles = [p.strip() for p in persona_raw.split(",") if p.strip()] if persona_raw else ["traveler"]
            
            consent_raw = (row.get("consent") or "Yes").strip()
            autobook_price_raw = (row.get("autobook_price") or "1500").strip()
            autobook_leadtime_raw = (row.get("autobook_leadtime") or "7").strip()
            autobook_risklevel_raw = (row.get("autobook_risklevel") or "2").strip()
            
            # Parse persona metadata
            persona_status = (row.get("persona_status") or "active").strip()
            persona_valid_from = (row.get("persona_valid_from") or "").strip()
            persona_valid_till = (row.get("persona_valid_till") or "").strip()
            
            # If temporal fields not provided, default to empty (will be set by API)
            if not persona_valid_from:
                from datetime import datetime, timezone
                persona_valid_from = datetime.now(timezone.utc).isoformat()
            if not persona_valid_till:
                from datetime import datetime, timezone, timedelta
                persona_valid_till = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()

            if not username:
                continue  # Skip empty rows
            if not password:
                raise ValueError(f"Row {row_index}: password is empty.")
            if not email:
                raise ValueError(f"Row {row_index}: email is empty.")
            
            # Parse consent as boolean
            consent_bool = consent_raw.lower() in ("yes", "true", "1")
            
            # Parse numeric values
            try:
                price_int = int(autobook_price_raw)
                leadtime_int = int(autobook_leadtime_raw)
                risklevel_int = int(autobook_risklevel_raw)
            except ValueError as e:
                raise ValueError(f"Row {row_index}: Invalid numeric value - {e}")

            users.append(
                SeedUser(
                    username=username,
                    password=password,
                    email=email,
                    first_name=first_name or "",
                    last_name=last_name or "",
                    persona_titles=persona_titles,
                    consent=consent_bool,
                    autobook_price=price_int,
                    autobook_leadtime=leadtime_int,
                    autobook_risklevel=risklevel_int,
                    persona_status=persona_status,
                    persona_valid_from=persona_valid_from,
                    persona_valid_till=persona_valid_till,
                )
            )

    return users


def get_admin_token(base_url: str, admin_user: str, admin_password: str) -> str:
    """Get admin access token from Keycloak."""
    url = f"{base_url}/realms/master/protocol/openid-connect/token"
    data = {
        "username": admin_user,
        "password": admin_password,
        "grant_type": "password",
        "client_id": "admin-cli",
    }
    
    response = requests.post(url, data=data, verify=False)
    response.raise_for_status()
    return response.json()["access_token"]


def get_user_by_username(base_url: str, realm: str, token: str, username: str) -> Optional[dict]:
    """Get existing user by username."""
    url = f"{base_url}/admin/realms/{realm}/users"
    params = {"username": username, "exact": "true"}
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(url, params=params, headers=headers, verify=False)
    response.raise_for_status()
    
    users = response.json()
    return users[0] if users else None


def create_keycloak_user(base_url: str, realm: str, token: str, user: SeedUser) -> str:
    """Create a new user in Keycloak (authentication only, no persona attributes)."""
    url = f"{base_url}/admin/realms/{realm}/users"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    # No attributes stored in Keycloak - personas managed via persona-api
    payload = {
        "username": user.username,
        "email": user.email,
        "firstName": user.first_name,
        "lastName": user.last_name,
        "enabled": True,
        "emailVerified": True,
        "credentials": [{
            "type": "password",
            "value": user.password,
            "temporary": False,
        }],
    }
    
    response = requests.post(url, json=payload, headers=headers, verify=False)
    response.raise_for_status()
    
    # Get user ID from Location header
    location = response.headers.get("Location", "")
    user_id = location.split("/")[-1] if location else None
    
    if not user_id:
        # Fallback: query for the user
        created_user = get_user_by_username(base_url, realm, token, user.username)
        user_id = created_user["id"] if created_user else None
    
    return user_id


def update_keycloak_user(base_url: str, realm: str, token: str, user_id: str, user: SeedUser) -> None:
    """Update existing user in Keycloak (authentication only, no persona attributes)."""
    url = f"{base_url}/admin/realms/{realm}/users/{user_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    # No attributes stored in Keycloak - personas managed via persona-api
    payload = {
        "email": user.email,
        "firstName": user.first_name,
        "lastName": user.last_name,
        "enabled": True,
        "emailVerified": True,
    }
    
    response = requests.put(url, json=payload, headers=headers, verify=False)
    response.raise_for_status()
    
    # Update password separately
    reset_url = f"{base_url}/admin/realms/{realm}/users/{user_id}/reset-password"
    password_payload = {
        "type": "password",
        "value": user.password,
        "temporary": False,
    }
    response = requests.put(reset_url, json=password_payload, headers=headers, verify=False)
    response.raise_for_status()


def get_service_token(keycloak_url: str, realm: str, client_id: str, client_secret: str) -> str:
    """Get service account token for calling persona-api."""
    url = f"{keycloak_url}/realms/{realm}/protocol/openid-connect/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    
    response = requests.post(url, data=data, verify=False)
    response.raise_for_status()
    return response.json()["access_token"]


def create_persona_via_api(persona_title: str, user: SeedUser, profile_api_url: str, token: str) -> None:
    """Create a single persona for user via persona-api."""
    url = f"{profile_api_url.rstrip('/')}/v1/personas"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "title": persona_title,
        "consent": user.consent,
        "autobook_price": user.autobook_price,
        "autobook_leadtime": user.autobook_leadtime,
        "autobook_risklevel": user.autobook_risklevel,
        "valid_from": user.persona_valid_from,
        "valid_till": user.persona_valid_till,
    }
    
    # Note: status is set to 'active' by default in persona_core.py
    # The CSV persona_status field is for future use if we want to create inactive personas
    
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()


def get_user_token(base_url: str, realm: str, username: str, password: str, client_id: str) -> str:
    """Get access token for a user."""
    url = f"{base_url}/realms/{realm}/protocol/openid-connect/token"
    data = {
        "username": username,
        "password": password,
        "grant_type": "password",
        "client_id": client_id,
    }
    
    response = requests.post(url, data=data, verify=False)
    response.raise_for_status()
    return response.json()["access_token"]


def seed_users_keycloak(
    users: List[SeedUser],
    base_url: str,
    realm: str,
    admin_user: str,
    admin_password: str,
    profile_api_url: str,
    client_id: str,
    is_dry_run: bool
) -> None:
    if is_dry_run:
        print("DRY RUN: No calls will be made to Keycloak or persona-api.")
        for user in users:
            personas_str = ", ".join(user.persona_titles)
            print(f"- Would create/update user '{user.email}' (username: {user.username})")
            print(f"  Personas: [{personas_str}]")
            print(f"  Status: {user.persona_status}, Valid: {user.persona_valid_from} to {user.persona_valid_till}")
        return

    # Get admin token
    try:
        token = get_admin_token(base_url, admin_user, admin_password)
    except Exception as e:
        print(f"ERROR: Failed to authenticate as admin: {e}")
        sys.exit(1)
    
    created_count = 0
    updated_count = 0
    persona_count = 0

    for user in users:
        try:
            # Step 1: Create/update user in Keycloak
            existing_user = get_user_by_username(base_url, realm, token, user.username)
            
            if existing_user:
                user_id = existing_user["id"]
                update_keycloak_user(base_url, realm, token, user_id, user)
                print(f"OK (Keycloak): {user.email} (updated, id={user_id})")
                updated_count += 1
            else:
                user_id = create_keycloak_user(base_url, realm, token, user)
                print(f"OK (Keycloak): {user.email} (created, id={user_id})")
                created_count += 1
            
            # Step 2: Get user token
            user_token = get_user_token(base_url, realm, user.username, user.password, client_id)
            
            # Step 3: Create all personas for this user via persona-api
            for persona_title in user.persona_titles:
                create_persona_via_api(persona_title, user, profile_api_url, user_token)
                print(f"OK (Persona):  {user.email} -> '{persona_title}'")
                persona_count += 1
            
        except Exception as exc:
            print(f"ERROR: Failed to process {user.email}: {exc}")
            continue

    print("")
    print("Summary")
    print(f"Users created: {created_count}")
    print(f"Users updated: {updated_count}")
    print(f"Personas created: {persona_count}")
    print(f"Total users: {len(users)}")


def main() -> int:
    args = parse_arguments()
    
    # Get admin password from args or environment
    admin_password = args.admin_password or os.environ.get("KEYCLOAK_ADMIN_PASSWORD")
    if not admin_password:
        print("ERROR: Admin password required. Provide via --admin-password or KEYCLOAK_ADMIN_PASSWORD env var.")
        return 1
    
    users = load_users_from_csv(args.csv)
    seed_users_keycloak(
        users,
        base_url=args.keycloak_url,
        realm=args.realm,
        admin_user=args.admin_user,
        admin_password=admin_password,
        profile_api_url=args.profile_api_url,
        client_id=args.client_id,
        is_dry_run=bool(args.dry_run),
    )
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
