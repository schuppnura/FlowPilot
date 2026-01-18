# Domain Configuration Guide

The FlowPilot web app supports multiple domain configurations (travel, nursing, etc.) with customizable terminology and styling.

## Configuration System

Domain-specific settings are centralized in `src/config.ts`:

### Supported Domains
- **travel**: Travel booking workflows (default)
- **nursing**: Healthcare/nursing care workflows

### Configuration Properties

Each domain configuration includes:

```typescript
{
  displayName: string;        // Display name for the domain
  tagline: string;            // Hero section tagline
  backgroundImage: string;    // Path to background image
  terminology: {
    workflow: string;         // Singular term for workflow
    workflows: string;        // Plural term for workflow
    workflowItem: string;     // Singular term for workflow item
    workflowItems: string;    // Plural term for workflow items
    createAction: string;     // Text for create button
    manageAction: string;     // Text for manage button
    myWorkflows: string;      // Text for "My [workflows]" tab
  }
}
```

### Travel Domain Configuration

```typescript
{
  displayName: 'Travel',
  tagline: 'Policy-driven authorization & delegation for AI-powered workflows',
  backgroundImage: '/images/nura-home.jpg',
  terminology: {
    workflow: 'itinerary',
    workflows: 'itineraries',
    workflowItem: 'trip item',
    workflowItems: 'trip items',
    createAction: 'Create New Trip',
    manageAction: 'Manage My Trip',
    myWorkflows: 'My Trips',
  }
}
```

### Nursing Domain Configuration

```typescript
{
  displayName: 'Nursing Care',
  tagline: 'Intelligent care coordination with secure delegation',
  backgroundImage: '/images/nura-nursing.jpg',
  terminology: {
    workflow: 'work schedule',
    workflows: 'work schedules',
    workflowItem: 'task',
    workflowItems: 'tasks',
    createAction: 'Create Work Schedule',
    manageAction: 'Manage My Schedule',
    myWorkflows: 'My Schedules',
  }
}
```

## Using Terminology in Components

### Import Configuration

```typescript
import { config, terminology, capitalize } from '../../config';
```

### Using Terminology

The `terminology` export provides both lowercase and capitalized versions:

```typescript
// Lowercase versions
terminology.workflow        // "itinerary" or "work schedule"
terminology.workflows       // "itineraries" or "work schedules"
terminology.workflowItem    // "trip item" or "task"
terminology.workflowItems   // "trip items" or "tasks"

// Capitalized versions (auto-generated)
terminology.Workflow        // "Itinerary" or "Work schedule"
terminology.Workflows       // "Itineraries" or "Work schedules"
terminology.WorkflowItem    // "Trip item" or "Task"
terminology.WorkflowItems   // "Trip items" or "Tasks"
```

### Example Usage

```tsx
// Simple text replacement
<h2>Loading {terminology.workflows}...</h2>

// Dynamic button text
<button>{config.terminology.createAction}</button>

// Capitalized text
<h3>{terminology.Workflow} Details</h3>

// Manual capitalization for arbitrary strings
<h3>Create New {capitalize(terminology.workflow)}</h3>
```

### Domain-Specific Styling

Access domain-specific properties:

```tsx
// Background image
<div style={{ backgroundImage: `url(${config.backgroundImage})` }} />

// Tagline
<p>{config.tagline}</p>

// Conditional icon based on domain
<span>{config.domain === 'travel' ? '✈️' : '🏥'}</span>
```

## Building for Different Domains

### Development

Set the domain via environment variable:

```bash
# Travel domain (default)
npm run dev

# Nursing domain
VITE_DOMAIN=nursing npm run dev
```

### Production Build

Build for specific domain:

```bash
# Travel
npm run build

# Nursing
VITE_DOMAIN=nursing npm run build
```

### Environment Variables

Create `.env` files for different domains:

**.env.travel**
```
VITE_DOMAIN=travel
VITE_DOMAIN_SERVICES_API_URL=https://flowpilot-domain-services-api-737191827545.us-central1.run.app
```

**.env.nursing**
```
VITE_DOMAIN=nursing
VITE_DOMAIN_SERVICES_API_URL=https://flowpilot-domain-services-api-737191827545.us-central1.run.app
```

Then build:
```bash
npm run build -- --mode nursing
```

## Adding Background Images

Background images should be placed in `public/images/`:

- Travel: `public/images/nura-home.jpg`
- Nursing: `public/images/nura-nursing.jpg`

## Adding a New Domain

1. **Update `config.ts`**: Add new domain configuration to `domainConfigs`
2. **Add background image**: Place image in `public/images/`
3. **Update type**: Add domain to `AppDomain` type
4. **Test**: Build and test with `VITE_DOMAIN=newdomain`

Example:

```typescript
export type AppDomain = 'travel' | 'nursing' | 'finance';

const domainConfigs: Record<AppDomain, DomainConfig> = {
  // ... existing domains
  finance: {
    displayName: 'Finance',
    tagline: 'Secure approval workflows for financial operations',
    backgroundImage: '/images/nura-finance.jpg',
    terminology: {
      workflow: 'approval request',
      workflows: 'approval requests',
      workflowItem: 'approval item',
      workflowItems: 'approval items',
      createAction: 'Create Approval Request',
      manageAction: 'Manage Requests',
      myWorkflows: 'My Requests',
    },
  },
};
```

## Component Updates

All UI components have been updated to use the domain configuration:

- `WelcomePanel`: Hero section, buttons, tagline, background
- `MyTripsPanel`: Title, icons, empty states, loading messages
- `TripListItem`: Item counts
- `CreateTripModal`: Modal title, form labels
- `BookTripModal`: Modal title, button text
- `TripDetailsModal`: Modal title, icons, labels
- `BookPanel`: Title, button text, selection labels
- `DelegatePanel`: Selection labels, empty states
- `InvitePanel`: Selection labels, empty states
- `PanelHeader`: Current workflow label
- `TabNavigation`: Tab label for workflows
- `main.tsx`: Page title

## Testing

After configuration changes:

1. Test with travel domain: `npm run dev`
2. Test with nursing domain: `VITE_DOMAIN=nursing npm run dev`
3. Verify all terminology changes
4. Check background images load correctly
5. Verify page title updates
6. Test all panels and modals

## Notes

- The configuration is determined at build time using Vite environment variables
- Components import from `config.ts` for runtime access to terminology
- Background images are served from the `public` directory
- All user-facing text should use the terminology system for consistency
