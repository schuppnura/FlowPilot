# Web App Development Plan

## Overview

This document outlines the plan for building a web application that mirrors the functionality of the existing Swift macOS app. The web app will integrate with the FlowPilot platform deployed on GCP and use Firebase Authentication for user management.

## Architecture

### Technology Stack

**Frontend Framework:**
- **React** with **TypeScript** (recommended for type safety and modern development)
- Alternative: **Vue.js** or **Svelte** (if preferred)

**UI Framework:**
- **Tailwind CSS** for styling (matches modern, clean aesthetic)
- **React Router** for navigation between panels

**Firebase Integration:**
- **Firebase SDK v9+** (modular SDK) for authentication
- Firebase Auth methods: `signInWithEmailAndPassword`, `createUserWithEmailAndPassword`, `signOut`

**HTTP Client:**
- **Axios** or **fetch API** for REST API calls to FlowPilot services

**State Management:**
- **React Context API** or **Zustand** for global state (similar to AppState in Swift)
- Manage: authentication state, workflows, personas, delegations, invitations

### Project Structure

```
flowpilot-web/
├── public/
│   ├── images/
│   │   └── nura-home.jpg          # Welcome panel background
│   └── index.html
├── src/
│   ├── components/
│   │   ├── panels/
│   │   │   ├── WelcomePanel.tsx
│   │   │   ├── MyAccountPanel.tsx
│   │   │   ├── MyTripPanel.tsx
│   │   │   ├── InvitePanel.tsx
│   │   │   └── DelegatePanel.tsx
│   │   ├── common/
│   │   │   ├── SignInForm.tsx
│   │   │   ├── SignUpForm.tsx
│   │   │   ├── WorkflowItemCard.tsx
│   │   │   └── StatusBadge.tsx
│   │   └── layout/
│   │       ├── AppLayout.tsx
│   │       └── Navigation.tsx
│   ├── services/
│   │   ├── firebase/
│   │   │   ├── auth.ts            # Firebase auth wrapper
│   │   │   └── config.ts           # Firebase config
│   │   ├── api/
│   │   │   ├── domainServices.ts  # Workflow API client
│   │   │   ├── delegation.ts      # Delegation API client
│   │   │   ├── aiAgent.ts         # AI Agent API client
│   │   │   └── authz.ts           # AuthZ API client
│   │   └── tokenProvider.ts       # Token refresh logic
│   ├── state/
│   │   ├── AuthContext.tsx        # Authentication state
│   │   ├── AppStateContext.tsx    # Main app state (workflows, personas, etc.)
│   │   └── useAppState.ts         # Custom hook for app state
│   ├── types/
│   │   ├── models.ts              # TypeScript interfaces (Workflow, WorkflowItem, etc.)
│   │   └── api.ts                 # API response types
│   ├── utils/
│   │   ├── jwt.ts                 # JWT decoding utilities
│   │   └── dateFormatting.ts
│   ├── App.tsx
│   └── main.tsx
├── package.json
├── tsconfig.json
├── tailwind.config.js
└── vite.config.ts (or webpack.config.js)
```

## Panel Specifications

### 1. Welcome Panel

**Purpose:** Landing page with background image and primary action buttons

**Layout:**
- Full-screen or large hero section
- Background: `images/nura-home.jpg` (cover image, centered)
- Overlay: Semi-transparent dark overlay for text readability
- Content:
  - FlowPilot logo/branding (top-left or centered)
  - Welcome message
  - Two primary buttons:
    - **"Create New Trip"** (orange/primary color)
    - **"Manage My Trip"** (secondary/outline style)

**Behavior:**
- If user is not logged in: clicking either button redirects to My-Account panel
- If user is logged in:
  - "Create New Trip" → navigates to My-Trip panel with create workflow flow
  - "Manage My Trip" → navigates to My-Trip panel with workflow selection

**Implementation:**
```tsx
// WelcomePanel.tsx structure
- Hero section with background image
- Conditional rendering based on auth state
- Navigation handlers
```

### 2. My-Account Panel

**Purpose:** User registration, login, and account management

**Layout:**
- Card-based layout (similar to Swift app's identity panel)
- Two states:
  - **Not Logged In:**
    - Sign-in form (email/password)
    - Sign-up form (email/password, confirm password)
    - Toggle between sign-in and sign-up
    - Error messages display
  - **Logged In:**
    - User info display (email, user ID/sub)
    - Persona selector (if multiple personas available)
    - Sign-out button

**Features:**
- Firebase Authentication integration:
  - `createUserWithEmailAndPassword` for registration
  - `signInWithEmailAndPassword` for login
  - `signOut` for logout
- Token management:
  - Get ID token after authentication
  - Store token in state/context
  - Handle token refresh
- Persona extraction:
  - Decode JWT to extract persona claims
  - Display persona selector if multiple personas exist
  - Auto-select if only one persona

**Implementation:**
```tsx
// MyAccountPanel.tsx
- Conditional rendering: SignInForm vs UserInfo
- Firebase auth methods
- Token extraction and storage
- Persona extraction from JWT
```

### 3. My-Trip Panel

**Purpose:** Display trip details, select trips, and view workflow items

**Layout:**
- Card-based layout (similar to Swift app's workflows panel)
- Sections:
  1. **Trip Selection:**
     - Dropdown/picker to select existing trip
     - "Create New Trip" button (if templates available)
  2. **Trip Details:**
     - Trip ID (monospace font, selectable)
     - Departure date
     - Item count
     - Owner info (if delegated)
  3. **Workflow Items List:**
     - Scrollable list of workflow items
     - Each item shows:
       - Kind (hotel, flight, restaurant, etc.) - bold
       - Title
       - Details (type, city, rating, airports, etc.)
       - Status badge (planned, executed, denied, error)
     - Color-coded status indicators

**Features:**
- Load workflows on mount (if authenticated)
- Select workflow → load workflow items
- Create workflow from template:
  - Template selector
  - Date picker for start date
  - Create button
- Display workflow items with proper formatting
- Status badges with color coding

**API Integration:**
- `GET /v1/workflows` - List all workflows
- `GET /v1/workflows/{workflow_id}/items` - Get workflow items
- `POST /v1/workflows` - Create workflow from template
- `GET /v1/templates` - List available templates

**Implementation:**
```tsx
// MyTripPanel.tsx
- Workflow selection dropdown
- Workflow details display
- Workflow items list component
- Create workflow form/modal
```

### 4. Invite Panel

**Purpose:** Invite users to view trip (read-only access)

**Layout:**
- Card-based layout (similar to Swift app's invitations panel)
- Form elements:
  - User selector (dropdown/picker)
  - Expiration days stepper (default: 30 days)
  - "Invite to View" button
  - Helper text: "Invites users with the same persona to view your trip (read-only)"

**Features:**
- Load invitees (users with same persona, excluding self)
- Filter by selected persona
- Create delegation with scope: `["read"]`
- Success/error feedback

**API Integration:**
- `GET /v1/users?persona={persona}` - List users by persona
- `POST /v1/delegations` - Create read-only delegation

**Implementation:**
```tsx
// InvitePanel.tsx
- User selector dropdown
- Expiration stepper
- Create invitation handler
- Loading states
```

### 5. Delegate Panel

**Purpose:** Delegate trip execution to travel agents

**Layout:**
- Card-based layout (similar to Swift app's delegation panel)
- Form elements:
  - Travel agent selector (dropdown/picker)
  - Expiration days stepper (default: 7 days)
  - "Delegate Trip" button

**Features:**
- Load travel agents (users with persona "travel-agent")
- Create delegation with scope: `["execute"]`
- Success/error feedback
- Clear selection after successful delegation

**API Integration:**
- `GET /v1/users?persona=travel-agent` - List travel agents
- `POST /v1/delegations` - Create execute delegation

**Implementation:**
```tsx
// DelegatePanel.tsx
- Travel agent selector dropdown
- Expiration stepper
- Create delegation handler
- Loading states
```

## State Management

### Authentication State (AuthContext)

```typescript
interface AuthState {
  user: User | null;
  idToken: string | null;
  refreshToken: string | null;
  loading: boolean;
  error: string | null;
}

// Methods:
- signIn(email, password)
- signUp(email, password)
- signOut()
- refreshToken()
- getCurrentToken() // Returns current ID token
```

### Application State (AppStateContext)

```typescript
interface AppState {
  // User info
  principalSub: string | null;
  username: string | null;
  personas: string[];
  selectedPersona: string | null;
  
  // Workflows
  workflows: Workflow[];
  selectedWorkflowId: string | null;
  workflowItems: WorkflowItem[];
  workflowTemplates: WorkflowTemplate[];
  selectedWorkflowTemplateId: string | null;
  workflowStartDate: Date;
  
  // Delegations
  travelAgents: User[];
  selectedDelegateId: string | null;
  delegationExpiresInDays: number;
  
  // Invitations
  invitees: User[];
  selectedInviteeId: string | null;
  invitationExpiresInDays: number;
  
  // Agent runs
  lastAgentRun: AgentRunResponse | null;
  
  // UI state
  statusMessage: string;
  errorMessage: string;
}

// Methods:
- loadWorkflows()
- selectWorkflow(workflowId)
- createWorkflow(templateId, startDate, persona)
- loadWorkflowItems(workflowId)
- loadTravelAgents()
- createDelegation(delegateId, workflowId, expiresInDays)
- loadInvitees()
- createInvitation(inviteeId, workflowId, expiresInDays)
```

## API Client Implementation

### Base API Client Pattern

```typescript
// services/api/base.ts
class ApiClient {
  private baseUrl: string;
  private getToken: () => Promise<string | null>;
  
  async request(endpoint: string, options: RequestInit) {
    const token = await this.getToken();
    const headers = {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...options.headers,
    };
    // Make request with error handling
  }
}
```

### Domain Services Client

```typescript
// services/api/domainServices.ts
- fetchTemplates()
- fetchWorkflows()
- fetchWorkflowItems(workflowId, persona)
- createWorkflow(templateId, principalSub, startDate, persona)
```

### Delegation Client

```typescript
// services/api/delegation.ts
- listUsersByPersona(persona)
- createDelegation(principalId, delegateId, workflowId, scope, expiresInDays)
```

### AI Agent Client

```typescript
// services/api/aiAgent.ts
- runAgent(workflowId, principalSub, dryRun, persona)
```

## Firebase Configuration

### Setup Steps

1. **Create Firebase Project** (if not already done)
2. **Enable Email/Password Authentication** in Firebase Console
3. **Get Firebase Config:**
   - API Key
   - Project ID
   - Auth Domain
4. **Configure Firebase SDK:**
   ```typescript
   // services/firebase/config.ts
   import { initializeApp } from 'firebase/app';
   import { getAuth } from 'firebase/auth';
   
   const firebaseConfig = {
     apiKey: process.env.VITE_FIREBASE_API_KEY,
     authDomain: process.env.VITE_FIREBASE_AUTH_DOMAIN,
     projectId: process.env.VITE_FIREBASE_PROJECT_ID,
     // ... other config
   };
   
   const app = initializeApp(firebaseConfig);
   export const auth = getAuth(app);
   ```

### Authentication Flow

```typescript
// services/firebase/auth.ts
import { 
  signInWithEmailAndPassword, 
  createUserWithEmailAndPassword,
  signOut,
  User
} from 'firebase/auth';
import { auth } from './config';

export async function signIn(email: string, password: string) {
  const userCredential = await signInWithEmailAndPassword(auth, email, password);
  const idToken = await userCredential.user.getIdToken();
  return { user: userCredential.user, idToken };
}

export async function signUp(email: string, password: string) {
  const userCredential = await createUserWithEmailAndPassword(auth, email, password);
  const idToken = await userCredential.user.getIdToken();
  return { user: userCredential.user, idToken };
}

export async function logout() {
  await signOut(auth);
}
```

## Navigation & Routing

### Route Structure

```
/ (Welcome Panel)
/account (My-Account Panel)
/trips (My-Trip Panel)
/invite (Invite Panel)
/delegate (Delegate Panel)
```

### Navigation Logic

- **Unauthenticated users:**
  - Redirect to `/account` when accessing protected routes
  - Welcome panel buttons redirect to `/account`
  
- **Authenticated users:**
  - Can access all panels
  - Welcome panel buttons navigate to appropriate panels

## UI/UX Design Guidelines

### Color Scheme (Nura Style)
- Primary Orange: `#F28C3D` (RGB: 242, 140, 61)
- Soft Dark: `#333340` (RGB: 51, 51, 64)
- Background: `#FAFAFA` (RGB: 250, 250, 250)
- White Cards: `#FFFFFF`
- Subtle Shadows: `rgba(0, 0, 0, 0.03)`

### Typography
- Headlines: Medium weight, system font
- Body: Regular weight, system font
- Monospace: For IDs and technical data

### Components
- Cards: White background, rounded corners (12px), subtle shadow
- Buttons: Primary (orange) and secondary (outline) styles
- Status Badges: Color-coded (green=success, orange=warning, red=error)
- Form Inputs: Rounded borders, proper spacing

## Development Phases

### Phase 1: Foundation (Week 1)
- [ ] Set up React + TypeScript project
- [ ] Configure Tailwind CSS
- [ ] Set up Firebase SDK
- [ ] Create base API client
- [ ] Implement authentication context
- [ ] Create routing structure

### Phase 2: Authentication (Week 1-2)
- [ ] Build My-Account panel
- [ ] Implement sign-in/sign-up forms
- [ ] Integrate Firebase Auth
- [ ] Token management and refresh
- [ ] Persona extraction from JWT
- [ ] Protected route handling

### Phase 3: Core Panels (Week 2-3)
- [ ] Welcome panel with background image
- [ ] My-Trip panel (workflow selection and display)
- [ ] Workflow items list component
- [ ] Create workflow functionality
- [ ] API integration for workflows

### Phase 4: Delegation & Invitations (Week 3-4)
- [ ] Delegate panel
- [ ] Invite panel
- [ ] User listing by persona
- [ ] Delegation creation API integration
- [ ] Success/error feedback

### Phase 5: Polish & Testing (Week 4)
- [ ] Error handling improvements
- [ ] Loading states
- [ ] Responsive design
- [ ] Cross-browser testing
- [ ] Integration testing with GCP deployment

## Environment Configuration

### Required Environment Variables

```env
# Firebase
VITE_FIREBASE_API_KEY=your_api_key
VITE_FIREBASE_AUTH_DOMAIN=your_project.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=your_project_id

# FlowPilot APIs (GCP)
VITE_DOMAIN_SERVICES_API_URL=https://flowpilot-domain-services-api-737191827545.us-central1.run.app
VITE_DELEGATION_API_URL=https://flowpilot-delegation-api-737191827545.us-central1.run.app
VITE_AI_AGENT_API_URL=https://flowpilot-ai-agent-api-737191827545.us-central1.run.app
VITE_AUTHZ_API_URL=https://flowpilot-authz-api-737191827545.us-central1.run.app
```

## Security Considerations

1. **Token Storage:**
   - Store tokens in memory (React state/context)
   - Avoid localStorage for sensitive tokens (consider httpOnly cookies for production)

2. **API Security:**
   - Always include Authorization header with Bearer token
   - Handle 401 errors (token expired) → refresh or re-authenticate
   - Validate all API responses

3. **Input Validation:**
   - Validate email format
   - Enforce password requirements
   - Sanitize user inputs

4. **Error Handling:**
   - Don't expose sensitive error details to users
   - Log errors server-side
   - Provide user-friendly error messages

## Testing Strategy

1. **Unit Tests:**
   - API client methods
   - Utility functions (JWT decoding, date formatting)
   - State management logic

2. **Integration Tests:**
   - Authentication flow
   - API calls with mock responses
   - Navigation flows

3. **E2E Tests (Optional):**
   - Complete user workflows
   - Cross-browser testing

## Deployment

### Build Process
```bash
npm run build  # Creates production build
```

### Hosting Options
- **Firebase Hosting** (recommended - integrates well with Firebase Auth)
- **Vercel**
- **Netlify**
- **Cloud Run** (static site)

### Deployment Steps
1. Build production bundle
2. Configure Firebase Hosting
3. Deploy to Firebase Hosting
4. Configure custom domain (if needed)
5. Set up environment variables in hosting platform

## Future Enhancements

1. **Agent Execution UI:**
   - Add "Dry Run" and "Book Trip" buttons (like Swift app)
   - Display authorization results
   - Show reason codes for denials

2. **Profile Management:**
   - User profile editing
   - Persona preferences
   - Auto-booking consent settings

3. **Real-time Updates:**
   - WebSocket integration for workflow status updates
   - Real-time delegation notifications

4. **Mobile Responsiveness:**
   - Optimize for mobile devices
   - Touch-friendly interactions

## Dependencies

### Core Dependencies
```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.20.0",
    "firebase": "^10.7.0",
    "axios": "^1.6.0",
    "zustand": "^4.4.0" // or use React Context
  },
  "devDependencies": {
    "@types/react": "^18.2.0",
    "@types/react-dom": "^18.2.0",
    "typescript": "^5.3.0",
    "vite": "^5.0.0",
    "tailwindcss": "^3.4.0",
    "@vitejs/plugin-react": "^4.2.0"
  }
}
```

## Notes

- The web app should mirror the functionality of the Swift macOS app as closely as possible
- Use the same API endpoints and authentication flow
- Maintain consistency in UI/UX with the Nura design style
- Ensure all panels are accessible and functional
- Handle edge cases (no workflows, no agents, etc.) gracefully
