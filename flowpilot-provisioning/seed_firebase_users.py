#!/usr/bin/env python3
"""
seed_firebase_users.py

Create/update users in Firebase Authentication and create personas via persona-api.
Personas are no longer stored as Firebase custom claims - they are managed via persona-api.

CSV columns: username;password;email;firstname;lastname;persona;consent;autobook_price;autobook_leadtime;autobook_risklevel;persona_status;persona_valid_from;persona_valid_till
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import json
from dataclasses import dataclass
from typing import List

import requests
import firebase_admin
from firebase_admin import auth, credentials


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
        description="Seed Firebase users from CSV (FlowPilot)."
    )
    parser.add_argument(
        "--csv",
        default="flowpilot-provisioning/users_seed.csv",
        help="Path to users CSV (default: flowpilot-provisioning/users_seed.csv)",
    )
    parser.add_argument(
        "--project-id",
        default="vision-course-476214",
        help="Firebase project ID (default: vision-course-476214)",
    )
    parser.add_argument(
        "--profile-api-url",
        default="http://localhost:8006",
        help="User Profile API base URL (default: http://localhost:8006)",
    )
    parser.add_argument(
        "--authz-api-url",
        default="http://localhost:8002",
        help="AuthZ API base URL for token exchange (default: http://localhost:8002)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="If set, do not call Firebase; only print intended actions.",
    )
    parser.add_argument(
        "--service-account-key",
        default="../flowpilot-testing/firebase-admin-key.json",
        help="Path to Firebase service account key JSON (default: ../flowpilot-testing/firebase-admin-key.json)",
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
            
            # Parse persona titles - comma-separated values
            persona_raw = (row.get("persona") or "").strip()
            persona_list = [p.strip() for p in persona_raw.split(",") if p.strip()] if persona_raw else []
            
            consent_str = (row.get("consent") or "Yes").strip()
            autobook_price_str = (row.get("autobook_price") or "1500").strip()
            autobook_leadtime_str = (row.get("autobook_leadtime") or "7").strip()
            autobook_risklevel_str = (row.get("autobook_risklevel") or "2").strip()
            
            persona_status = (row.get("persona_status") or "active").strip()
            persona_valid_from = (row.get("persona_valid_from") or "2024-01-01T00:00:00Z").strip()
            persona_valid_till = (row.get("persona_valid_till") or "2026-12-31T23:59:59Z").strip()

            if not username:
                continue  # Skip empty rows
            if not password:
                raise ValueError(f"Row {row_index}: password is empty.")
            if not email:
                raise ValueError(f"Row {row_index}: email is empty.")
            
            # Convert consent to boolean
            consent_bool = consent_str.lower() in ("yes", "true", "1")

            users.append(
                SeedUser(
                    username=username,
                    password=password,
                    email=email,
                    first_name=first_name or "",
                    last_name=last_name or "",
                    persona_titles=persona_list if persona_list else ["traveler"],
                    consent=consent_bool,
                    autobook_price=int(autobook_price_str),
                    autobook_leadtime=int(autobook_leadtime_str),
                    autobook_risklevel=int(autobook_risklevel_str),
                    persona_status=persona_status,
                    persona_valid_from=persona_valid_from,
                    persona_valid_till=persona_valid_till,
                )
            )

    return users


def get_firebase_user_token(user_email: str, user_password: str, firebase_api_key: str, authz_api_url: str) -> str:
    """
    Authenticate a Firebase user and exchange for FlowPilot access token.
    Uses Firebase REST API for sign-in and then exchanges for access token.
    """
    # Step 1: Get Firebase ID token
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={firebase_api_key}"
    payload = {
        "email": user_email,
        "password": user_password,
        "returnSecureToken": True,
    }
    
    response = requests.post(url, json=payload)
    if response.status_code != 200:
        raise RuntimeError(f"Failed to authenticate user {user_email}: {response.text}")
    
    firebase_token = response.json()["idToken"]
    
    # Step 2: Exchange for FlowPilot access token
    exchange_url = f"{authz_api_url}/v1/token/exchange"
    exchange_response = requests.post(
        exchange_url,
        headers={"Authorization": f"Bearer {firebase_token}"}
    )
    if exchange_response.status_code != 200:
        raise RuntimeError(f"Failed to exchange token for user {user_email}: {exchange_response.text}")
    
    return exchange_response.json()["access_token"]




def create_persona_via_api(
    profile_api_url: str,
    user_token: str,
    persona_title: str,
    consent: bool,
    autobook_price: int,
    autobook_leadtime: int,
    autobook_risklevel: int,
    persona_status: str,
    persona_valid_from: str,
    persona_valid_till: str,
) -> dict:
    """
    Create a persona via persona-api POST /v1/personas.
    
    The API is fully idempotent - if persona already exists, it returns the existing persona (201).
    This allows the seed script to be run multiple times safely.
    """
    url = f"{profile_api_url}/v1/personas"
    payload = {
        "title": persona_title,
        "scope": ["read", "execute"],
        "valid_from": persona_valid_from,
        "valid_till": persona_valid_till,
        "status": persona_status,
        "consent": consent,
        "autobook_price": autobook_price,
        "autobook_leadtime": autobook_leadtime,
        "autobook_risklevel": autobook_risklevel,
    }
    headers = {"Authorization": f"Bearer {user_token}"}
    
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 201:
        return response.json()
    else:
        raise RuntimeError(f"Failed to create persona: {response.status_code} {response.text}")


def seed_users_firebase(users: List[SeedUser], profile_api_url: str, authz_api_url: str, firebase_api_key: str, service_account_key_path: str, is_dry_run: bool) -> None:
    if is_dry_run:
        print("DRY RUN: No calls will be made to Firebase.")
        for user in users:
            persona_str = ", ".join(user.persona_titles)
            print(f"- Would create/update user '{user.email}' (username: {user.username}) with personas=[{persona_str}]")
        return

    # Initialize Firebase Admin SDK using service account key
    try:
        firebase_admin.get_app()
    except ValueError:
        cred = credentials.Certificate(service_account_key_path)
        firebase_admin.initialize_app(cred)
    
    created_count = 0
    updated_count = 0
    persona_created_count = 0

    for user in users:
        try:
            # Step 1: Create/update user in Firebase Authentication
            existing_user = None
            try:
                existing_user = auth.get_user_by_email(user.email)
            except auth.UserNotFoundError:
                pass
            
            display_name = f"{user.first_name} {user.last_name}".strip()
            
            if existing_user:
                # Update existing user (authentication only, no custom claims)
                user_uid = existing_user.uid
                auth.update_user(
                    user_uid,
                    email=user.email,
                    password=user.password,
                    display_name=display_name or None,
                    email_verified=True,
                )
                updated_count += 1
                print(f"Updated user: {user.email} (uid={user_uid})")
            else:
                # Create new user
                user_record = auth.create_user(
                    email=user.email,
                    password=user.password,
                    display_name=display_name or None,
                    email_verified=True,
                )
                user_uid = user_record.uid
                created_count += 1
                print(f"Created user: {user.email} (uid={user_uid})")
            
            # Step 2: Get user access token for persona creation
            user_token = get_firebase_user_token(user.email, user.password, firebase_api_key, authz_api_url)
            
            # Step 3: Create personas via persona-api (API is idempotent - handles duplicates automatically)
            for persona_title in user.persona_titles:
                persona_response = create_persona_via_api(
                    profile_api_url=profile_api_url,
                    user_token=user_token,
                    persona_title=persona_title,
                    consent=user.consent,
                    autobook_price=user.autobook_price,
                    autobook_leadtime=user.autobook_leadtime,
                    autobook_risklevel=user.autobook_risklevel,
                    persona_status=user.persona_status,
                    persona_valid_from=user.persona_valid_from,
                    persona_valid_till=user.persona_valid_till,
                )
                
                # Check if this was a new persona or existing one by looking at created_at vs updated_at
                # For now, we'll just count all as created since API returns 201 for both new and existing
                persona_created_count += 1
                print(f"  Created/retrieved persona '{persona_title}' with ID {persona_response['persona_id']}")
            
            print(f"✓ {user.email}")
            
        except Exception as exc:
            print(f"✗ ERROR: Failed to process {user.email}: {exc}")
            continue

    print("")
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Users created:        {created_count}")
    print(f"Users updated:        {updated_count}")
    print(f"Personas created/retrieved: {persona_created_count}")
    print(f"Total users:          {len(users)}")
    print("=" * 70)


def main() -> int:
    args = parse_arguments()
    
    # Get Firebase API key from environment
    firebase_api_key = os.getenv("FIREBASE_API_KEY")
    if not firebase_api_key and not args.dry_run:
        print("ERROR: FIREBASE_API_KEY environment variable is required")
        return 1
    
    users = load_users_from_csv(args.csv)
    seed_users_firebase(
        users,
        profile_api_url=args.profile_api_url,
        authz_api_url=args.authz_api_url,
        firebase_api_key=firebase_api_key,
        service_account_key_path=args.service_account_key,
        is_dry_run=bool(args.dry_run),
    )
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
