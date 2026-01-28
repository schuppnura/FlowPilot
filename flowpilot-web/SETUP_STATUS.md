# FlowPilot Web App - Setup Status

## ✅ Completed

### Project Foundation
- ✅ React + TypeScript + Vite project structure
- ✅ Tailwind CSS configuration with Nura color scheme
- ✅ ESLint configuration
- ✅ Project dependencies (package.json)

### Tab-Based Navigation
- ✅ Tab navigation component with 5 tabs:
  - Welcome
  - My Account
  - My Trip
  - Invite
  - Delegate
- ✅ React Router setup with protected routes
- ✅ App layout with tab navigation

### Authentication
- ✅ Firebase configuration setup
- ✅ Firebase Authentication service
- ✅ AuthContext for global auth state
- ✅ Sign-in form component
- ✅ Sign-up form component
- ✅ My-Account panel with conditional rendering

### UI Components
- ✅ Welcome panel with background image
- ✅ Basic panel placeholders (My Trip, Invite, Delegate)
- ✅ Styling with Nura design system (orange, dark, bg colors)

### Assets
- ✅ Background image copied to public/images/nura-home.jpg

## 🚧 Next Steps

### 1. API Clients (Priority)
- [ ] Create base API client with token provider
- [ ] Domain Services API client (workflows, templates)
- [ ] Delegation API client
- [ ] AI Agent API client
- [ ] AuthZ API client

### 2. State Management
- [ ] Create AppStateContext (similar to Swift AppState)
- [ ] Implement workflow management state
- [ ] Implement persona extraction from JWT
- [ ] Implement delegation/invitation state

### 3. My-Trip Panel
- [ ] Workflow selection dropdown
- [ ] Workflow details display
- [ ] Workflow items list component
- [ ] Create workflow from template
- [ ] Status badges for workflow items

### 4. Invite Panel
- [ ] User listing by persona
- [ ] User selector dropdown
- [ ] Expiration days stepper
- [ ] Create invitation API integration

### 5. Delegate Panel
- [ ] Travel agent listing
- [ ] Travel agent selector dropdown
- [ ] Expiration days stepper
- [ ] Create delegation API integration

### 6. Utilities
- [ ] JWT decoding utility (for persona extraction)
- [ ] Date formatting utilities
- [ ] Error handling utilities

## 📝 Configuration Required

Before running the app, you need to:

1. **Install dependencies:**
   ```bash
   cd flowpilot-web
   npm install
   ```

2. **Set up environment variables:**
   ```bash
   cp .env.example .env
   ```
   
   Then edit `.env` with your Firebase credentials:
   - `VITE_FIREBASE_API_KEY`
   - `VITE_FIREBASE_AUTH_DOMAIN`
   - `VITE_FIREBASE_PROJECT_ID`

3. **Start development server:**
   ```bash
   npm run dev
   ```

## 🎨 Design Notes

- Tab navigation uses Nura orange (`#F28C3D`) for active state
- Cards use white background with subtle shadows
- Welcome panel has full-screen hero with background image
- All panels follow the Nura design system from the macOS app

## 📁 Project Structure

```
flowpilot-web/
├── src/
│   ├── components/
│   │   ├── panels/          ✅ All 5 panels created
│   │   ├── common/          ✅ Sign-in/up forms
│   │   └── layout/          ✅ Tab navigation & layout
│   ├── services/
│   │   └── firebase/        ✅ Auth service
│   ├── state/               ✅ AuthContext
│   ├── types/               ✅ TypeScript interfaces
│   ├── App.tsx              ✅ Main app with routing
│   └── main.tsx             ✅ Entry point
├── public/
│   └── images/             ✅ Background image
├── package.json             ✅ Dependencies
├── tailwind.config.js       ✅ Nura colors
└── vite.config.ts           ✅ Vite config
```

## 🔗 Integration Points

The app is ready to integrate with:
- Firebase Authentication (configured)
- FlowPilot Domain Services API (needs client)
- FlowPilot Delegation API (needs client)
- FlowPilot AI Agent API (needs client)
- FlowPilot AuthZ API (needs client)

All API clients should use the token from `AuthContext.getToken()` for authentication.
