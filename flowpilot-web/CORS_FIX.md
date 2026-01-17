# CORS Issue Fix

## Problem
The web app was getting "Network error: Network Error" when trying to make API requests to the GCP Cloud Run services. This is a CORS (Cross-Origin Resource Sharing) issue - browsers block requests from one origin (localhost:5173) to another (GCP Cloud Run) unless the server explicitly allows it.

## Solution Implemented

### Development (Vite Dev Server)
Added a proxy configuration in `vite.config.ts` that routes API requests through the Vite dev server, which then forwards them to the GCP services. This bypasses CORS during development.

**How it works:**
- Web app makes requests to `/api/domain-services/*`, `/api/delegation/*`, etc.
- Vite dev server proxies these to the actual GCP Cloud Run URLs
- Since the request appears to come from the same origin (localhost:5173), CORS is not enforced

### Production
For production deployment, you have two options:

1. **Add CORS middleware to backend services** (Recommended)
   - Add FastAPI CORS middleware to all services
   - Allow your production domain in CORS configuration

2. **Use a reverse proxy** (Alternative)
   - Deploy the web app behind a reverse proxy (nginx, Cloud Run, etc.)
   - Proxy API requests through the same domain

## Backend CORS Fix (For Production)

To properly fix CORS for production, add this to each FastAPI service:

```python
from fastapi.middleware.cors import CORSMiddleware

# In create_app() function, after creating the FastAPI app:
api.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Dev
        "http://localhost:3000",  # Alternative dev port
        "https://your-production-domain.com",  # Production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

This should be added to:
- `flowpilot-services/domain-services-api/domain_services_main.py`
- `flowpilot-services/delegation-api/delegation_main.py`
- `flowpilot-services/ai-agent-api/ai_agent_main.py`
- `flowpilot-services/authz-api/authz_main.py`

## Testing

After restarting the dev server (`npm run dev`), the API requests should work without CORS errors.
