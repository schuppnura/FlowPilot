# Swift Code Changes for Invitations Feature

## Overview
Add an "Invitations" panel that allows users to invite others **with the same persona** to view (read-only access) their workflows. This creates delegations for read access semantically separate from execute delegations.

---

## 1. Update AppState.swift - Add Invitation State

Add these new @Published properties after line 34 (after delegation properties):

```swift
// Invitations (read-only access)
@Published var invitees: [TravelAgentUser] = []
@Published var selectedInviteeId: String?
@Published var invitationExpiresInDays: Int = 30  // Default longer expiration for invites
private var isLoadingInvitees: Bool = false
```

Add this new method after `loadTravelAgents()` (around line 446):

```swift
func loadInvitees() async {
    // Load users with the same persona as the selected persona for invitations
    // Prevent concurrent/duplicate calls
    guard !isLoadingInvitees && invitees.isEmpty else {
        return
    }
    
    guard let persona = selectedPersona else {
        // Can't load invitees without knowing which persona to filter by
        invitees = []
        return
    }
    
    isLoadingInvitees = true
    clearError()
    
    statusMessage = "Loading users with \(persona) persona…"
    do {
        let users = try await delegationClient.listUsersByPersona(persona: persona)
        // Filter out self
        invitees = users.filter { $0.id != principalSub }
        statusMessage = "Loaded \(invitees.count) user(s) with \(persona) persona."
    } catch {
        setError("Load invitees failed: \(error)")
        statusMessage = ""
        invitees = []
    }
    isLoadingInvitees = false
}
```

Add this new method after `createDelegation()` (around line 479):

```swift
func createInvitation() async {
    // Create an invitation (delegation for read access)
    // Same underlying mechanism as delegation, but UI semantics are different
    clearError()
    guard let principalId = principalSub else {
        setError("You must sign in first.")
        return
    }
    guard let inviteeId = selectedInviteeId else {
        setError("Select a user to invite first.")
        return
    }
    guard let workflowIdToShare = selectedWorkflowId ?? workflowId else {
        setError("Select or create a workflow first.")
        return
    }
    
    statusMessage = "Creating invitation…"
    do {
        _ = try await delegationClient.createDelegation(
            principalId: principalId,
            delegateId: inviteeId,
            workflowId: workflowIdToShare,
            expiresInDays: invitationExpiresInDays
        )
        statusMessage = "Invitation sent for workflow \(workflowIdToShare). Expires in \(invitationExpiresInDays) days."
        // Clear selection after successful invitation
        selectedInviteeId = nil
    } catch {
        setError("Create invitation failed: \(error)")
        statusMessage = ""
    }
}
```

Update the `signOut()` method to clear invitation state (around line 102):

```swift
// Add these lines in signOut() with the other clearing:
invitees = []
selectedInviteeId = nil
invitationExpiresInDays = 30
```

Update `signIn()` to auto-load invitees (around line 181):

```swift
// Add this line after loadTravelAgents():
await loadInvitees()
```

---

## 2. Update ContentView.swift - Add Invitations Panel

### Step 1: Rename "Delegation" to "Delegations" (line 382)

Change:
```swift
Text("Delegation")
```

To:
```swift
Text("Delegations")
```

### Step 2: Add invitationsPanel after delegationPanel (line 16)

In the VStack where panels are listed, add `invitationsPanel` after `delegationPanel`:

```swift
VStack(alignment: .leading, spacing: 20) {
    headerSection
    identityPanel
    workflowTemplatesPanel
    workflowsPanel
    delegationPanel
    invitationsPanel  // ADD THIS LINE
    authorizationResultsPanel
}
```

### Step 3: Add the invitationsPanel property after delegationPanel (around line 461)

Add this complete panel implementation:

```swift
private var invitationsPanel: some View {
    let personaRequired = state.personas.count > 1 && state.selectedPersona == nil
    
    return HStack(alignment: .top, spacing: 16) {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Image(systemName: "envelope.badge.person.crop")
                    .foregroundStyle(Color(red: 0.3, green: 0.3, blue: 0.35))
                Text("Invitations")
                    .font(.headline)
                    .fontWeight(.medium)
                    .foregroundStyle(Color(red: 0.2, green: 0.2, blue: 0.25))
            }
            
            if personaRequired {
                HStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.orange)
                    Text("Please select a persona first")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
                .padding(.vertical, 8)
            }
            
            HStack(alignment: .center, spacing: 12) {
                Text("Invite User")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .frame(width: 100, alignment: .leading)
                Picker("", selection: Binding<String>(
                    get: { state.selectedInviteeId ?? "" },
                    set: { newValue in state.selectedInviteeId = newValue.isEmpty ? nil : newValue }
                )) {
                    Text("Choose a user…").tag("")
                    ForEach(state.invitees) { user in
                        Text(user.displayName).tag(user.id)
                    }
                }
                .pickerStyle(.menu)
                .controlSize(.large)
                .disabled(personaRequired)
                .task {
                    // Load invitees when view appears and persona is selected
                    if state.principalSub != nil && state.selectedPersona != nil && state.invitees.isEmpty {
                        await state.loadInvitees()
                    }
                }
                .onChange(of: state.selectedPersona) { oldValue, newValue in
                    // Reload invitees when persona changes
                    if newValue != nil && newValue != oldValue {
                        Task {
                            state.invitees = []  // Clear old list
                            await state.loadInvitees()
                        }
                    }
                }
            }
            
            HStack(alignment: .center, spacing: 12) {
                Text("Expiration (days)")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .frame(width: 100, alignment: .leading)
                Stepper(value: $state.invitationExpiresInDays, in: 1...365, step: 1) {
                    Text("\(state.invitationExpiresInDays) days")
                        .foregroundStyle(.primary)
                }
                .disabled(personaRequired)
            }
            
            Text("Invites users with the same persona to view your trip (read-only)")
                .font(.caption)
                .foregroundStyle(.secondary)
                .italic()
        }
        
        Spacer()
        
        Button(action: {
            Task { await state.createInvitation() }
        }) {
            Label("Invite to View", systemImage: "envelope.circle.fill")
        }
        .buttonStyle(.borderedProminent)
        .controlSize(.large)
        .tint(Color(red: 0.2, green: 0.6, blue: 0.8))  // Different color (blue) from delegations
        .disabled(
            state.principalSub == nil ||
            (state.selectedInviteeId ?? "").isEmpty ||
            (state.workflowId ?? "").isEmpty ||
            (state.personas.count > 1 && state.selectedPersona == nil)
        )
        .frame(width: 150)
    }
    .padding(16)
    .background(Color.white)
    .cornerRadius(12)
    .shadow(color: Color.black.opacity(0.03), radius: 4, x: 0, y: 1)
    .opacity(personaRequired ? 0.5 : 1.0)
}
```

---

## 3. Condense UI (Optional)

To make everything fit on screen, reduce spacing and padding throughout ContentView.swift:

### Global Changes:
- Line 11: Change `spacing: 20` to `spacing: 12`
- Line 19: Change `.padding(20)` to `.padding(12)`

### Per-Panel Changes:
Reduce `.padding(16)` to `.padding(12)` for each panel (identityPanel, workflowTemplatesPanel, workflowsPanel, delegationPanel, invitationsPanel, authorizationResultsPanel)

### Font Size Reductions (optional):
- Change `.font(.headline)` to `.font(.system(size: 14, weight: .semibold))`
- Change `.font(.subheadline)` to `.font(.system(size: 12))`

---

## Testing the Changes

### 1. Build and Run
1. Open the project in Xcode
2. Build (Cmd+B)
3. Run (Cmd+R)

### 2. Test Invitations Flow

**As Carlo (traveler persona):**
1. Sign in as Carlo
2. Select "traveler" persona
3. Create or select a workflow
4. Go to Invitations panel
5. Select Yannick (should appear in list with traveler persona)
6. Click "Invite to View"
7. Should see success message

**As Yannick (traveler persona):**
1. Sign in as Yannick
2. Select "traveler" persona
3. Select Carlo's workflow from dropdown
4. Should be able to view workflow items (read access)
5. Cannot execute items (no delegation for execute)

**As Yannick (travel-agent persona):**
1. Change persona to "travel-agent"
2. Try to select Carlo's workflow
3. Should get 403 Permission Denied (persona mismatch)

---

## Key Differences: Delegations vs Invitations

| Aspect | Delegations | Invitations |
|--------|------------|-------------|
| **Purpose** | Grant execute access | Grant read-only access |
| **Target Persona** | travel-agent (fixed) | Same persona as owner |
| **Button Text** | "Delegate Trip" | "Invite to View" |
| **Button Color** | Orange | Blue |
| **Default Expiration** | 7 days | 30 days |
| **Icon** | person.2.badge.gearshape.fill | envelope.badge.person.crop |
| **User List** | Travel agents only | Users with same persona |
| **Backend Action** | Creates delegation (used for execute) | Creates delegation (used for read) |

---

## Notes

- Both features use the same delegation API endpoint
- The distinction between "execute" and "read" is semantic in the UI
- OPA policy determines whether action is "execute" or "read" based on the actual API call
- Invitations automatically reload when persona changes
- Users cannot invite themselves (filtered out)
