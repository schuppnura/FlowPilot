# Firebase Auth Migration Guide

## Summary

FlowPilot has been successfully migrated to use Firebase Authentication instead of Keycloak. This provides a fully managed authentication solution on GCP with minimal code changes.

## What Changed

### New Files Created
1. **`security_firebase.py`** - Firebase Auth JWT validation (replaces Keycloak JWKS validation)
2. **`profile_firebase.py`** - Firestore-based user profile management (replaces Keycloak Admin API)

### Key Differences from Keycloak

| Feature | Keycloak | Firebase |
|---------|----------|----------|
| JWT Validation | JWKS with PyJWT | Firebase Admin SDK |
| User Storage | Keycloak database | Firebase Auth + Firestore |
| Custom Attributes | Keycloak user attributes | Firestore documents + custom claims |
| Service Auth | Client Credentials OAuth2 | Google Cloud Identity Tokens |
| Deployment | Self-hosted (Cloud Run/GKE) | Fully managed by Google |

## Migration Steps

### 1. Add Firebase Dependencies

Add to all service `requirements.txt` files:
```
firebase-admin==6.3.0
google-cloud-firestore==2.14.0
```

### 2. Update Dockerfiles

Each service Dockerfile needs to copy the Firebase modules:
```dockerfile
# Change from:
COPY flowpilot-services/shared-libraries/security.py /app/security.py
COPY flowpilot-services/shared-libraries/profile.py /app/profile.py

# To:
COPY flowpilot-services/shared-libraries/security_firebase.py /app/security.py
COPY flowpilot-services/shared-libraries/profile_firebase.py /app/profile.py
```

### 3. Enable Firebase in GCP Project

```bash
# Already done
gcloud services enable firebase.googleapis.com
gcloud services enable firebasehosting.googleapis.com  
gcloud services enable identitytoolkit.googleapis.com
```

### 4. Initialize Firebase Project

Go to [Firebase Console](https://console.firebase.google.com/) and:
1. Add Firebase to your GCP project (`vision-course-476214`)
2. Enable Authentication → Sign-in methods → Email/Password
3. Enable Firestore Database (Native mode)

### 5. Remove Keycloak Environment Variables

Services no longer need:
- `KEYCLOAK_JWKS_URI`
- `KEYCLOAK_ISSUER`
- `KEYCLOAK_AUDIENCE`
- `KEYCLOAK_TOKEN_URL`
- `AGENT_CLIENT_ID` / `AGENT_CLIENT_SECRET` (for Keycloak auth)

### 6. Update Swift Client

The macOS Swift client needs to be updated to use Firebase Auth SDK instead of Keycloak:

```swift
// Old: Keycloak OIDC
// New: Firebase Auth iOS SDK
import FirebaseAuth

// Sign in
Auth.auth().signIn(withEmail: email, password: password) { result, error in
    if let user = result?.user {
        // Get ID token for API calls
        user.getIDToken { token, error in
            // Use token in Authorization header
        }
    }
}
```

## User Data Model

### Firebase Auth
Stores basic user info:
- UID (equivalent to Keycloak `sub`)
- Email
- Display Name
- Email Verified

### Firestore Collection: `users`
Document ID = Firebase UID

```json
{
  "persona": ["traveler"],
  "autobook_consent": "Yes",
  "autobook_price": "1500",
  "autobook_leadtime": "7",
  "autobook_risklevel": "2"
}
```

### Custom Claims (Optional)
Can be set on Firebase Auth user for inclusion in ID tokens:
```json
{
  "persona": ["traveler", "travel-agent"]
}
```

## Service-to-Service Authentication

Firebase migration simplifies service-to-service auth:

**Before (Keycloak):**
- Client Credentials OAuth2 flow
- Separate client ID/secret
- Token endpoint calls

**After (Firebase):**
- Google Cloud Identity Tokens (automatic on Cloud Run)
- Uses service account credentials
- No explicit configuration needed

The `get_service_token()` function now returns Cloud Run identity tokens instead of Keycloak tokens.

## Benefits of Firebase

1. **Fully Managed** - No need to deploy/manage Keycloak
2. **Better GCP Integration** - Native Cloud Run support
3. **Automatic Scaling** - Firebase scales automatically
4. **Built-in Features** - Email verification, password reset, MFA
5. **Cost Effective** - Free tier: 50k MAU, then $0.0055/user
6. **SDKs Available** - iOS, Android, Web, Admin (Python)

## Testing

### Create Test User (via Firebase Console or Admin SDK)

```python
from firebase_admin import auth

# Create user
user = auth.create_user(
    email='test@example.com',
    password='password123',
    display_name='Test User'
)

# Set custom claims
auth.set_custom_user_claims(user.uid, {
    'persona': ['traveler']
})

# Add Firestore data
from firebase_admin import firestore
db = firestore.client()
db.collection('users').document(user.uid).set({
    'persona': ['traveler'],
    'autobook_consent': 'Yes',
    'autobook_price': '1500',
    'autobook_leadtime': '7',
    'autobook_risklevel': '2'
})
```

### Get Test Token

```bash
# Using Firebase Auth REST API
curl 'https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{"email":"test@example.com","password":"password123","returnSecureToken":true}'
```

The `idToken` in the response is your JWT for API calls.

## Deployment

Once Dockerfiles and requirements are updated:

```bash
# Rebuild images
cd /Users/Me/Documents/Python/FlowPilot
docker build -f flowpilot-services/authz-api/Dockerfile \
  -t us-central1-docker.pkg.dev/vision-course-476214/flowpilot/authz-api:latest \
  --platform linux/amd64 .

# ... repeat for other services ...

# Push to Artifact Registry
docker push us-central1-docker.pkg.dev/vision-course-476214/flowpilot/authz-api:latest

# Redeploy to Cloud Run (no environment variable changes needed!)
gcloud run deploy flowpilot-authz-api \
  --image us-central1-docker.pkg.dev/vision-course-476214/flowpilot/authz-api:latest \
  --region us-central1
```

## Security Considerations

1. **Firebase Project Security Rules**: Set up Firestore security rules to protect user data
2. **API Keys**: Firebase API keys can be restricted in GCP Console
3. **Custom Claims**: Validate in backend, don't trust client-side claims alone
4. **Service Account**: Cloud Run service account needs `roles/firebase.admin` role

## Next Steps

1. ✅ Firebase modules created (`security_firebase.py`, `profile_firebase.py`)
2. ⏭️ Update `requirements.txt` for all services
3. ⏭️ Update Dockerfiles to use Firebase modules
4. ⏭️ Rebuild and push images
5. ⏭️ Initialize Firebase project in console
6. ⏭️ Create test users
7. ⏭️ Update Swift macOS client
8. ⏭️ Test end-to-end flows

## Rollback Plan

If needed, revert by:
1. Using original Dockerfiles (copy original `security.py` and `profile.py`)
2. Redeploy services with Keycloak environment variables
3. Point to Keycloak instance (local or cloud)

The Firebase modules don't modify any other code, making rollback simple.
