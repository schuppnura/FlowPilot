# Firebase / Firestore Infrastructure

This directory contains Firebase and Firestore configuration files for GCP Cloud Run deployment.

## Files

### firestore.indexes.json
Defines composite indexes for Firestore collections.

**Purpose:**
- Enables efficient queries on the `personas` collection
- Required for queries filtering by `user_sub`, `status`, and `created_at`
- Without these indexes, queries will fail in production

**Deploying indexes:**

```bash
# Option 1: Using Firebase CLI (recommended)
firebase deploy --only firestore:indexes

# Option 2: Using gcloud CLI
gcloud firestore indexes composite create \
  --collection-group=personas \
  --query-scope=COLLECTION \
  --field-config field-path=user_sub,order=ascending \
  --field-config field-path=status,order=ascending \
  --field-config field-path=created_at,order=descending

gcloud firestore indexes composite create \
  --collection-group=personas \
  --query-scope=COLLECTION \
  --field-config field-path=user_sub,order=ascending \
  --field-config field-path=created_at,order=descending
```

**Checking index status:**
```bash
# List all indexes
gcloud firestore indexes composite list

# Or via Firebase Console:
# https://console.firebase.google.com/project/YOUR_PROJECT/firestore/indexes
```

## Related Documentation

- [User Profile API Documentation](../../docs/api/user-profile.md)
- [Persona Management Guide](../../docs/development/personas.md)
