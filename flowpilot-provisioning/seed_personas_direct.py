#!/usr/bin/env python3
"""
Create personas directly in Firestore (bypassing persona-api).
Useful when JWT validation is causing issues during provisioning.
"""

import os
import sys
import uuid
import csv
from datetime import datetime, timezone, timedelta

import firebase_admin
from firebase_admin import credentials, firestore, auth

# Initialize Firebase Admin SDK
if not firebase_admin._apps:
    service_account_path = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        "../flowpilot-testing/firebase-admin-key.json"
    )
    
    if not os.path.exists(service_account_path):
        print(f"ERROR: Service account key not found at {service_account_path}")
        sys.exit(1)
    
    cred = credentials.Certificate(service_account_path)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Load user data from users_seed.csv
def load_users_from_csv():
    """Load users and personas from users_seed.csv"""
    users = []
    with open('users_seed.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            email = row['email']
            # Parse multiple personas (comma-separated)
            personas_str = row['persona']
            personas = [p.strip() for p in personas_str.split(',')]
            # Parse consent as boolean
            consent = row['consent'].lower() in ('yes', 'true', '1')
            
            for persona in personas:
                users.append({
                    "email": email,
                    "persona": persona,
                    "consent": consent,
                    "autobook_price": int(row['autobook_price']),
                    "autobook_leadtime": int(row['autobook_leadtime']),
                    "autobook_risklevel": int(row['autobook_risklevel']),
                })
    return users

USERS = load_users_from_csv()

def create_persona(user_sub, persona_title, consent, autobook_price, autobook_leadtime, autobook_risklevel):
    """Create a persona directly in Firestore."""
    persona_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    valid_till = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    
    persona_data = {
        "persona_id": persona_id,
        "user_sub": user_sub,
        "title": persona_title,
        "scope": ["read", "execute"],
        "valid_from": now,
        "valid_till": valid_till,
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "consent": consent,
        "autobook_price": autobook_price,
        "autobook_leadtime": autobook_leadtime,
        "autobook_risklevel": autobook_risklevel,
    }
    
    db.collection("personas").document(persona_id).set(persona_data)
    return persona_id

def main():
    print("=" * 70)
    print("Direct Firestore Persona Provisioning")
    print("=" * 70)
    print()
    
    persona_count = 0
    
    for user_data in USERS:
        try:
            # Get user UID from email
            user = auth.get_user_by_email(user_data["email"])
            user_sub = user.uid
            
            # Create persona
            persona_id = create_persona(
                user_sub=user_sub,
                persona_title=user_data["persona"],
                consent=user_data["consent"],
                autobook_price=user_data["autobook_price"],
                autobook_leadtime=user_data["autobook_leadtime"],
                autobook_risklevel=user_data["autobook_risklevel"],
            )
            
            print(f"✓ Created persona {user_data['persona']} for {user_data['email']} (persona_id={persona_id})")
            persona_count += 1
            
        except Exception as e:
            print(f"✗ Failed to create persona for {user_data['email']}: {e}")
            continue
    
    print()
    print(f"Created {persona_count}/{len(USERS)} personas")

if __name__ == "__main__":
    main()
