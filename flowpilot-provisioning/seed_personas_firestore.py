#!/usr/bin/env python3
"""Direct Firestore persona provisioning - bypasses persona-api JWT issues"""

import os, sys, uuid, csv
from datetime import datetime, timezone, timedelta
import firebase_admin
from firebase_admin import credentials, firestore, auth

# Initialize Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate(os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        "../flowpilot-testing/firebase-admin-key.json"
    ))
    firebase_admin.initialize_app(cred)

db = firestore.client()

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

for user_data in USERS:
    user = auth.get_user_by_email(user_data["email"])
    persona_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    db.collection("personas").document(persona_id).set({
        "persona_id": persona_id,
        "user_sub": user.uid,
        "title": user_data["persona"],
        "scope": ["read", "execute"],
        "valid_from": now,
        "valid_till": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "consent": user_data["consent"],
        "autobook_price": user_data["autobook_price"],
        "autobook_leadtime": user_data["autobook_leadtime"],
        "autobook_risklevel": user_data["autobook_risklevel"],
    })
    print(f"✓ {user_data['email']} → {user_data['persona']} (persona_id={persona_id})")

print(f"\nCreated {len(USERS)} personas in Firestore")
