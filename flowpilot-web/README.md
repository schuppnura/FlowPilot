# FlowPilot Web App

A web application for FlowPilot that provides the same functionality as the macOS app, with a tab-based interface.

## Features

- **Tab-based Navigation**: Five main tabs (Welcome, My Account, My Trip, Invite, Delegate)
- **Firebase Authentication**: Email/password sign-in and sign-up
- **Workflow Management**: Create and manage trips/workflows
- **Delegation**: Delegate trips to travel agents
- **Invitations**: Invite users to view trips (read-only)

## Getting Started

### Prerequisites

- Node.js 18+ and npm
- Firebase project with Authentication enabled

### Installation

1. Install dependencies:
```bash
npm install
```

2. Copy environment variables:
```bash
cp .env.example .env
```

3. Configure your `.env` file with your Firebase credentials and API URLs.

### Development

Start the development server:
```bash
npm run dev
```

The app will be available at `http://localhost:5173`

### Build

Build for production:
```bash
npm run build
```

The built files will be in the `dist` directory.

## Project Structure

```
flowpilot-web/
├── src/
│   ├── components/
│   │   ├── panels/          # Tab panel components
│   │   ├── common/          # Shared components
│   │   └── layout/           # Layout components
│   ├── services/
│   │   ├── firebase/        # Firebase configuration
│   │   └── api/             # API clients
│   ├── state/               # State management (Context)
│   ├── types/               # TypeScript types
│   └── utils/               # Utility functions
├── public/
│   └── images/              # Static assets
└── package.json
```

## Environment Variables

See `.env.example` for required environment variables.

## Technologies

- React 18
- TypeScript
- Vite
- Tailwind CSS
- Firebase Authentication
- React Router
