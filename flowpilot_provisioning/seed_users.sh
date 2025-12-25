#!/bin/bash
# Helper script to seed Keycloak users

cd "$(dirname "$0")"

python3 seed_keycloak_users.py \
  --config provision_config.json \
  --csv users_seed.csv \
  --env-file ../.env \
  "$@"


