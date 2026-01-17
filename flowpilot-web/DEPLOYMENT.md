# Deployment Guide for FlowPilot Web App

This guide explains how to deploy the FlowPilot web app to Firebase Hosting to make it publicly accessible.

## Quick Start

The easiest way to deploy:

```bash
cd flowpilot-web
./deploy.sh
```

This script will:
1. Install Firebase CLI if needed
2. Prompt you to log in if not already logged in
3. Build the production bundle
4. Deploy to Firebase Hosting

## Prerequisites

1. **Firebase CLI** installed (or use the deploy script which installs it):
   ```bash
   npm install -g firebase-tools
   ```

2. **Firebase project** already set up (project ID: `vision-course-476214`)

3. **Logged in to Firebase**:
   ```bash
   firebase login
   ```

## Initial Setup

The configuration files (`firebase.json` and `.firebaserc`) are already created. If you need to reinitialize:

1. **Navigate to the web app directory**:
   ```bash
   cd flowpilot-web
   ```

2. **Initialize Firebase Hosting** (if needed):
   ```bash
   firebase init hosting
   ```
   - Select "Use an existing project"
   - Choose `vision-course-476214`
   - Set public directory to `dist`
   - Configure as single-page app: **Yes**
   - Set up automatic builds: **No** (we'll build manually)

## Environment Variables

Before deploying, make sure you have a `.env` file (or `.env.production`) with:

```env
VITE_FIREBASE_API_KEY=your_api_key
VITE_FIREBASE_AUTH_DOMAIN=your_project.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=vision-course-476214

# API URLs (these are already set in the code, but you can override)
VITE_DOMAIN_SERVICES_API_URL=https://flowpilot-domain-services-api-737191827545.us-central1.run.app
VITE_DELEGATION_API_URL=https://flowpilot-delegation-api-737191827545.us-central1.run.app
VITE_AI_AGENT_API_URL=https://flowpilot-ai-agent-api-737191827545.us-central1.run.app
VITE_PERSONA_API_URL=https://flowpilot-persona-api-737191827545.us-central1.run.app
```

**Important**: For production, you'll need to set these as build-time environment variables. Firebase Hosting doesn't support runtime environment variables, so you have two options:

### Option 1: Build with environment variables (Recommended)

Set environment variables before building:
```bash
export VITE_FIREBASE_API_KEY=your_key
export VITE_FIREBASE_AUTH_DOMAIN=your_domain
export VITE_FIREBASE_PROJECT_ID=vision-course-476214
npm run build
firebase deploy --only hosting
```

### Option 2: Use Firebase Hosting environment config

Create a `.env.production.local` file (this won't be committed):
```bash
# .env.production.local
VITE_FIREBASE_API_KEY=your_key
VITE_FIREBASE_AUTH_DOMAIN=your_domain
VITE_FIREBASE_PROJECT_ID=vision-course-476214
```

## Deployment Steps

1. **Build the production bundle**:
   ```bash
   npm run build
   ```
   This creates optimized files in the `dist/` directory.

2. **Deploy to Firebase Hosting**:
   ```bash
   npm run deploy
   ```
   Or:
   ```bash
   firebase deploy --only hosting
   ```

3. **Verify deployment**:
   After deployment, Firebase will provide a URL like:
   ```
   https://vision-course-476214.web.app
   ```
   Or your custom domain if configured.

## Custom Domain (Optional)

To use a custom domain:

1. Go to [Firebase Console](https://console.firebase.google.com/) → Your Project → Hosting
2. Click "Add custom domain"
3. Follow the instructions to verify domain ownership
4. Update DNS records as instructed

## Continuous Deployment (Optional)

You can set up automatic deployments using GitHub Actions or similar CI/CD:

1. Create `.github/workflows/deploy.yml`:
   ```yaml
   name: Deploy to Firebase Hosting
   on:
     push:
       branches: [main]
   jobs:
     deploy:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v3
         - uses: actions/setup-node@v3
           with:
             node-version: '18'
         - run: npm ci
         - run: npm run build
         - uses: FirebaseExtended/action-hosting-deploy@v0
           with:
             repoToken: '${{ secrets.GITHUB_TOKEN }}'
             firebaseServiceAccount: '${{ secrets.FIREBASE_SERVICE_ACCOUNT }}'
             projectId: vision-course-476214
   ```

## Troubleshooting

### Build fails
- Check that all environment variables are set
- Verify TypeScript compilation: `npm run build`

### CORS errors in production
- Ensure your backend APIs have CORS middleware enabled
- Add your Firebase Hosting domain to allowed origins

### Authentication not working
- Verify Firebase config in `.env` matches your Firebase project
- Check that Email/Password authentication is enabled in Firebase Console

## Post-Deployment Checklist

- [ ] Test authentication (sign up, sign in, sign out)
- [ ] Verify API calls work (check browser console for errors)
- [ ] Test all tabs and functionality
- [ ] Check that images load correctly
- [ ] Verify CORS is working for all API endpoints
