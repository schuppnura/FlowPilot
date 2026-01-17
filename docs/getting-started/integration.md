# Integration Guide

Add FlowPilot authorization to your web or mobile application.

## Overview

FlowPilot is a **managed authorization service** for demo purposes. It illustrates:

- Multi-persona authorization (user as traveler vs. agent vs. admin)
- Delegation management (user delegates to AI agent or another user)
- Policy evaluation (consent checks, risk thresholds, custom rules)
- Audit trails and explainable decisions

## Service Endpoints

**Production API Base URL:**  
`https://flowpilot-domain-services-api-737191827545.us-central1.run.app`

All APIs require bearer access tokens.

### Available APIs

| API | Purpose | Endpoint |
|-----|---------|----------|
| **Domain Services** | Manage workflows and workflow items | `/v1/workflows` |
| **AuthZ** | Authorization decisions | `/v1/evaluate` |
| **Delegation** | Manage delegations | `/v1/delegations` |
| **User Profile** | User personas and preferences | `/v1/profile` |
| **AI Agent** | Execute workflows via agent | `/v1/workflow-runs` |

## Prerequisites

1. **Firebase Project** - Sign up at [firebase.google.com](https://firebase.google.com)
2. **FlowPilot Account** - Contact us to get your project configured
3. **User Profile Storage** - Set up Firestore to store user personas and preferences

## Step 1: Authenticate Your Users

FlowPilot uses **Firebase Authentication** for user identity. Integrate Firebase Auth in your app:

=== "Web (JavaScript)"

    ```javascript
    import { getAuth, signInWithEmailAndPassword } from 'firebase/auth';

    const auth = getAuth();
    const userCredential = await signInWithEmailAndPassword(
      auth, 
      email, 
      password
    );
    
    // Get ID token to pass to FlowPilot
    const idToken = await userCredential.user.getIdToken();
    ```

=== "iOS (Swift)"

    ```swift
    import FirebaseAuth

    Auth.auth().signIn(withEmail: email, password: password) { result, error in
        guard let user = result?.user else { return }
        
        user.getIDToken { token, error in
            // Use token with FlowPilot APIs
            let idToken = token
        }
    }
    ```

=== "Android (Kotlin)"

    ```kotlin
    import com.google.firebase.auth.FirebaseAuth

    val auth = FirebaseAuth.getInstance()
    auth.signInWithEmailAndPassword(email, password)
        .addOnCompleteListener { task ->
            if (task.isSuccessful) {
                val user = auth.currentUser
                user?.getIdToken(true)?.addOnCompleteListener { tokenTask ->
                    val idToken = tokenTask.result?.token
                    // Use token with FlowPilot APIs
                }
            }
        }
    ```

## Step 2: Manage User Profiles

FlowPilot provides a User Profile API to manage user personas and preferences. No Firebase SDK required.

### Get User Profile

```javascript
const response = await fetch(
  'https://flowpilot-persona-api-737191827545.us-central1.run.app/v1/profile',
  {
    headers: {
      'Authorization': `Bearer ${idToken}`
    }
  }
);

const profile = await response.json();
console.log('User persona:', profile.personas);
```

### Update User Profile

```javascript
const response = await fetch(
  'https://flowpilot-persona-api-737191827545.us-central1.run.app/v1/profile',
  {
    method: 'PUT',
    headers: {
      'Authorization': `Bearer ${idToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      personas: ["traveler"],
      autobook_consent: true,
      autobook_price: 500,
      autobook_leadtime: 30,
      autobook_risklevel: 50
    })
  }
);

const updatedProfile = await response.json();
```

### Find Users by Persona

Find delegation candidates (e.g., travel agents):

```javascript
const response = await fetch(
  'https://flowpilot-persona-api-737191827545.us-central1.run.app/v1/users?persona=travel-agent',
  {
    headers: {
      'Authorization': `Bearer ${idToken}`
    }
  }
);

const { users } = await response.json();
console.log('Available agents:', users);
```

### Profile Fields

| Field | Type | Description |
|-------|------|-------------|
| `sub` | string | User UUID (from Firebase Auth) |
| `personas` | string[] | List of personas: `["traveler", "travel-agent", "admin"]` |
| `autobook_consent` | boolean | Consent for AI agent execution |
| `autobook_price` | number | Max price agent can book |
| `autobook_leadtime` | number | Max days in advance |
| `autobook_risklevel` | number | Risk tolerance (0-100) |

For more details about personas, see the [Personas Guide](../development/personas.md).

## Step 3: Create Workflows

Call the Domain Services API to create a workflow (e.g., a travel booking):

```javascript
const response = await fetch(
  'https://flowpilot-domain-services-api-737191827545.us-central1.run.app/v1/workflows',
  {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${idToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      template_id: 'trip-to-milan',
      principal_sub: user.uid,
      start_date: '2026-02-01',
      persona: 'traveler'
    })
  }
);

const workflow = await response.json();
console.log('Created workflow:', workflow.workflow_id);
```

## Step 4: Delegate to AI Agent

Allow the AI agent to execute workflows on the user's behalf:

```javascript
const delegationResponse = await fetch(
  'https://flowpilot-delegation-api-737191827545.us-central1.run.app/v1/delegations',
  {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${idToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      principal_id: user.uid,
      delegate_id: 'agent-runner',  // FlowPilot's AI agent ID
      workflow_id: workflow.workflow_id,
      scope: ['execute'],
      expires_in_days: 7
    })
  }
);
```

## Step 5: Execute Workflow via Agent

Trigger the AI agent to execute the workflow:

```javascript
const runResponse = await fetch(
  'https://flowpilot-ai-agent-api-737191827545.us-central1.run.app/v1/workflow-runs',
  {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${idToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      workflow_id: workflow.workflow_id,
      principal_sub: user.uid,
      dry_run: false,
      persona: 'traveler'
    })
  }
);

const runResult = await runResponse.json();

// Check results
runResult.results.forEach(item => {
  console.log(`Item ${item.workflow_item_id}: ${item.decision}`);
  if (item.decision === 'deny') {
    console.log('Reason:', item.reason_codes);
  }
});
```

## Step 6: Handle Authorization Decisions

The agent returns structured authorization decisions:

```javascript
{
  "decision": "deny",
  "reason_codes": ["rego.deny.consent_required"],
  "advice": [
    {
      "type": "deny",
      "message": "User consent not provided for auto-booking"
    }
  ]
}
```

### Common Reason Codes

| Reason Code | Meaning |
|-------------|---------|
| `rego.deny.consent_required` | User hasn't consented to auto-booking |
| `rego.deny.price_exceeded` | Item price exceeds user's threshold |
| `rego.deny.leadtime_exceeded` | Booking too far in advance |
| `rego.deny.risk_exceeded` | Risk level too high for user |
| `delegation.not_found` | No delegation exists |
| `delegation.expired` | Delegation has expired |

## Complete Example

Here's a complete workflow in JavaScript:

```javascript
import { initializeApp } from 'firebase/app';
import { getAuth, signInWithEmailAndPassword } from 'firebase/auth';

// 1. Initialize Firebase
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);

// 2. Sign in user
const userCredential = await signInWithEmailAndPassword(auth, email, password);
const idToken = await userCredential.user.getIdToken();

// 3. Create workflow
const workflowResponse = await fetch(
  'https://flowpilot-domain-services-api-737191827545.us-central1.run.app/v1/workflows',
  {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${idToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      template_id: 'trip-to-milan',
      principal_sub: userCredential.user.uid,
      start_date: '2026-02-01',
      persona: 'traveler'
    })
  }
);
const workflow = await workflowResponse.json();

// 4. Delegate to agent
await fetch(
  'https://flowpilot-delegation-api-737191827545.us-central1.run.app/v1/delegations',
  {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${idToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      principal_id: userCredential.user.uid,
      delegate_id: 'agent-runner',
      workflow_id: workflow.workflow_id,
      expires_in_days: 7
    })
  }
);

// 5. Execute via agent
const runResponse = await fetch(
  'https://flowpilot-ai-agent-api-737191827545.us-central1.run.app/v1/workflow-runs',
  {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${idToken}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      workflow_id: workflow.workflow_id,
      principal_sub: userCredential.user.uid,
      dry_run: false
    })
  }
);
const result = await runResponse.json();

console.log('Execution results:', result);
```

## SDK Support

Currently, FlowPilot provides REST APIs. SDKs are planned for:

- JavaScript/TypeScript (coming soon)
- Swift/iOS (coming soon)
- Kotlin/Android (coming soon)
- Python (coming soon)

For now, use standard HTTP clients in your language of choice.

## Rate Limits

- **Development**: 100 requests/minute
- **Production**: 1000 requests/minute
- **Enterprise**: Custom limits

Contact us for higher limits.

## Support

- **Documentation**: [API Reference](../api/authz.md)
- **Email**: support@flowpilot.dev
- **Discord**: [Join our community](https://discord.gg/flowpilot)

## Next Steps

- [Understand Personas](../development/personas.md) - Learn about multi-persona authorization
- [Writing Custom Policies](../development/policies.md) - Create policies for your use case
- [API Reference](../api/authz.md) - Explore all available APIs
