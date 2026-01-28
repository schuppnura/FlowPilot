//
//  AppState.swift
//  FlowPilot-demo
//
//

import Foundation
import Combine
import AppKit

@MainActor
final class AppState: ObservableObject {
    @Published var principalSub: String?
    @Published var username: String?
    @Published var idToken: String?
    @Published var accessToken: String?
    @Published var refreshToken: String?
    
    @Published var personas: [String] = []
    @Published var selectedPersona: String?
    
    @Published var workflowTemplates: [WorkflowTemplate] = []
    @Published var selectedWorkflowTemplateId: String?
    @Published var workflowStartDate: Date = Date()
    @Published var workflowId: String?
    @Published var workflowStartDateString: String?
    @Published var workflowItems: [WorkflowItem] = []
    
    @Published var workflows: [Workflow] = []
    @Published var selectedWorkflowId: String?
    
    @Published var travelAgents: [TravelAgentUser] = []
    @Published var selectedDelegateId: String?
    @Published var delegationExpiresInDays: Int = 7
    private var isLoadingTravelAgents: Bool = false
    
    // Invitations (read-only access)
    @Published var invitees: [TravelAgentUser] = []
    @Published var selectedInviteeId: String?
    @Published var invitationExpiresInDays: Int = 30  // Default longer expiration for invites
    private var isLoadingInvitees: Bool = false
    
    @Published var lastAgentRun: AgentRunResponse?
    @Published var missingProfileFieldsFromAdvice: [String] = []
    
    @Published var statusMessage: String = ""
    @Published var errorMessage: String = ""
    
    let firebaseAuthClient = FirebaseAuthClient()
    
    // Domain-specific client name can remain for now; AppState treats it as a generic workflow backend.
    // Clients are initialized lazily to capture self reference for token provider
    lazy var workflowClient: FlowPilotApiClient = {
        FlowPilotApiClient(accessTokenProvider: { [weak self] in self?.accessToken })
    }()
    
    lazy var agentRunnerClient: FlowPilotAIAgentApiClient = {
        FlowPilotAIAgentApiClient(accessTokenProvider: { [weak self] in self?.accessToken })
    }()
    
    // Profile API is now embedded into authz-api; keep it as an AuthZ client.
    lazy var authzClient: AuthzApiClient = {
        AuthzApiClient(baseUrl: AppConfig.authzBaseUrl, accessTokenProvider: { [weak self] in self?.accessToken })
    }()
    
    lazy var delegationClient: DelegationApiClient = {
        DelegationApiClient(accessTokenProvider: { [weak self] in self?.accessToken })
    }()
    
    func clearError() {
        // Clear error state; why: keep UI feedback current; side effect: mutates published state.
        errorMessage = ""
    }
    
    func setError(_ message: String) {
        // Set error state; why: provide visible diagnostics; side effect: mutates published state.
        errorMessage = message
    }
    
    func signOut() {
        // Sign out and clear transient state; why: ensure next session is clean; side effect: mutates published state.
        // Firebase email/password auth doesn't require server-side logout
        
        // Clear local state
        principalSub = nil
        username = nil
        idToken = nil
        accessToken = nil
        refreshToken = nil
        personas = []
        selectedPersona = nil
        
        workflowId = nil
        workflowStartDateString = nil
        workflowItems = []
        workflowTemplates = []
        selectedWorkflowTemplateId = nil
        workflows = []
        selectedWorkflowId = nil
        travelAgents = []
        selectedDelegateId = nil
        delegationExpiresInDays = 7
        invitees = []
        selectedInviteeId = nil
        invitationExpiresInDays = 30
        
        lastAgentRun = nil
        missingProfileFieldsFromAdvice = []
        
        statusMessage = "Signed out."
        errorMessage = ""
    }
    
    func openFirebaseAccountManagement() {
        // Open Firebase console for account management
        let consoleUrl = "https://console.firebase.google.com/project/\(AppConfig.firebaseProjectId)/authentication/users"
        
        guard let url = URL(string: consoleUrl) else {
            setError("Unable to open Firebase console.")
            return
        }
        
        NSWorkspace.shared.open(url)
        statusMessage = "Opening Firebase console..."
    }
    
    func signIn(email: String, password: String) async {
        // Perform Firebase email/password sign-in; why: bind workflows to an authenticated principal.
        clearError()
        statusMessage = "Signing in…"
        
        do {
            let (tokens, uid) = try await firebaseAuthClient.signIn(email: email, password: password)
            principalSub = uid
            idToken = tokens.idToken
            accessToken = tokens.idToken  // Firebase uses ID token for authorization
            refreshToken = tokens.refreshToken
            
            // Extract username from email
            username = tokens.email ?? email.components(separatedBy: "@").first
            
            // Extract persona from token claims
            extractPersonaFromToken()
            
            statusMessage = "Signed in. uid=\(uid)"
            
            // Auto-load templates, workflows, and travel agents post sign-in
            await loadWorkflowTemplates(forceReload: true)
            await loadWorkflows()
            await loadTravelAgents()
            await loadInvitees()
        } catch {
            setError("Sign-in failed: \(error)")
            statusMessage = ""
        }
    }
    
    func extractPersonaFromToken() {
        // Extract persona claim from access token; why: get user personas for selection; side effect: updates persona state.
        guard let token = accessToken else {
            personas = []
            selectedPersona = nil
            print("DEBUG: No access token available for persona extraction")
            return
        }
        
        do {
            // Decode access token (JwtUtils.decodeClaims works with any JWT, not just id tokens)
            let claims = try JwtUtils.decodeClaims(idToken: token)
            
            // Debug: print all claim keys to see what's available
            print("DEBUG: Available claims in access token: \(claims.keys.sorted())")
            
            // Extract persona claim - it should be an array of strings (multi-valued attribute)
            var extractedPersonas: [String] = []
            
            if let personaValue = claims["persona"] {
                print("DEBUG: Found persona claim: \(personaValue) (type: \(type(of: personaValue)))")
                
                if let personaArray = personaValue as? [String] {
                    // Persona is already an array
                    extractedPersonas = personaArray.filter { !$0.isEmpty }
                    print("DEBUG: Extracted personas as [String]: \(extractedPersonas)")
                } else if let personaArray = personaValue as? [Any] {
                    // Persona is an array of other types, convert to strings
                    extractedPersonas = personaArray.compactMap { item in
                        if let str = item as? String, !str.isEmpty {
                            return str
                        }
                        return nil
                    }
                    print("DEBUG: Extracted personas as [Any]: \(extractedPersonas)")
                } else if let personaString = personaValue as? String, !personaString.isEmpty {
                    // Persona is a single string
                    extractedPersonas = [personaString]
                    print("DEBUG: Extracted persona as String: \(extractedPersonas)")
                } else {
                    print("DEBUG: Persona value is not in expected format: \(personaValue)")
                }
            } else {
                print("DEBUG: No 'persona' claim found in access token")
            }
            
            personas = extractedPersonas
            print("DEBUG: Final personas array: \(personas)")
            
            // Auto-select if only one persona
            if personas.count == 1 {
                selectedPersona = personas.first
                print("DEBUG: Auto-selected persona: \(selectedPersona ?? "nil")")
            } else if personas.count > 1 {
                // If multiple personas and we already have a selection that's still valid, keep it
                // Otherwise, clear selection
                if let current = selectedPersona, personas.contains(current) {
                    // Keep current selection
                    print("DEBUG: Keeping current persona selection: \(current)")
                } else {
                    selectedPersona = nil
                    print("DEBUG: Cleared persona selection (multiple personas, no valid selection)")
                }
            } else {
                // No personas found
                selectedPersona = nil
                print("DEBUG: No personas found, cleared selection")
            }
        } catch {
            // If extraction fails, clear personas
            personas = []
            selectedPersona = nil
            print("DEBUG: Failed to extract persona from token: \(error)")
        }
    }
    
    func extractUsernameFromToken() {
        // Extract username claim from access token; why: display username in Account pane; side effect: updates username state.
        guard let token = accessToken else {
            username = nil
            print("DEBUG: No access token available for username extraction")
            return
        }
        
        do {
            let claims = try JwtUtils.decodeClaims(idToken: token)
            
            // Debug: print all claim keys to see what's available
            print("DEBUG: Available claims in access token: \(claims.keys.sorted())")
            
            // Try both "username" and "preferred_username" (Firebase might use either)
            if let usernameValue = claims["username"] as? String, !usernameValue.isEmpty {
                username = usernameValue
                print("DEBUG: Extracted username from 'username' claim: \(username ?? "nil")")
            } else if let preferredUsername = claims["preferred_username"] as? String, !preferredUsername.isEmpty {
                username = preferredUsername
                print("DEBUG: Extracted username from 'preferred_username' claim: \(username ?? "nil")")
            } else {
                username = nil
                print("DEBUG: No 'username' or 'preferred_username' claim found in access token")
                print("DEBUG: Token claims: \(claims)")
            }
        } catch {
            print("DEBUG: Extracting username failed: \(error)")
            username = nil
        }
    }
    
    
    func loadWorkflowTemplates(forceReload: Bool) async {
        // Load workflow templates from backend; why: user selects a workflow template without extra clicks; side effect: network I/O.
        clearError()
        
        if !forceReload && !workflowTemplates.isEmpty {
            return
        }
        
        statusMessage = "Loading workflow templates…"
        do {
            let loaded = try await workflowClient.fetchTemplates()
            workflowTemplates = loaded
            selectedWorkflowTemplateId = loaded.first?.template_id
            statusMessage = "Loaded \(loaded.count) workflow templates."
        } catch {
            setError("Load workflow templates failed: \(error)")
            statusMessage = ""
        }
    }
    
    func createWorkflowFromSelectedTemplate() async {
        // Create a workflow from the selected template; why: produce a workflow instance for agent execution; side effect: network I/O.
        clearError()
        guard let sub = principalSub else {
            setError("You must sign in first.")
            return
        }
        guard let templateId = selectedWorkflowTemplateId else {
            setError("Select a template first.")
            return
        }
        
        // Check if persona is required and selected
        if personas.count > 1 && selectedPersona == nil {
            setError("Please select a persona first.")
            return
        }
        
        // Format start date as ISO 8601 date string (YYYY-MM-DD)
        let dateFormatter = ISO8601DateFormatter()
        dateFormatter.formatOptions = [.withFullDate]
        let startDateString = dateFormatter.string(from: workflowStartDate)
        
        statusMessage = "Creating workflow…"
        do {
            // Backend still creates a "trip"; we treat it as a workflow id in the UI/state.
            // If only one persona exists, use it even if not explicitly selected
            let personaToSend = selectedPersona ?? (personas.count == 1 ? personas.first : nil)
            print("DEBUG: Sending persona to workflow API: \(personaToSend ?? "nil") (selectedPersona: \(selectedPersona ?? "nil"), personas: \(personas))")
            let newWorkflowId = try await workflowClient.loadTemplate(templateId: templateId, principalSub: sub, startDate: startDateString, persona: personaToSend)
            
            // Reload workflows list to include the new one
            await loadWorkflows()
            
            // Automatically select the newly created workflow
            await selectWorkflow(newWorkflowId)
            
            statusMessage = "Created and selected workflow: \(newWorkflowId) (start: \(startDateString))"
        } catch {
            setError("Create workflow failed: \(error)")
            statusMessage = ""
        }
    }
    
    func refreshAccessTokenIfNeeded() async -> Bool {
        // Refresh access token to get latest claims; why: ensure token has latest claims before execute; side effect: updates access token.
        guard let refreshTokenValue = refreshToken else {
            return false
        }
        
        do {
            let tokenResponse = try await firebaseAuthClient.refreshAccessToken(refreshToken: refreshTokenValue)
            idToken = tokenResponse.idToken
            accessToken = tokenResponse.idToken  // Firebase uses ID token for authorization
            refreshToken = tokenResponse.refreshToken
            
            // Re-extract persona after refresh
            extractPersonaFromToken()
            return true
        } catch {
            setError("Token refresh failed: \(error)")
            return false
        }
    }
    
    func loadWorkflows() async {
        // Load all workflows from backend; why: allow user to select existing workflow; side effect: network I/O.
        clearError()
        guard principalSub != nil else {
            setError("You must sign in first.")
            return
        }
        
        statusMessage = "Loading workflows…"
        do {
            let loaded = try await workflowClient.fetchWorkflows()
            workflows = loaded
            statusMessage = "Loaded \(loaded.count) workflows."
        } catch {
            setError("Load workflows failed: \(error)")
            statusMessage = ""
        }
    }
    
    func selectWorkflow(_ workflowId: String) async {
        // Select an existing workflow and load its items; why: allow user to work with existing workflows; side effect: network I/O.
        clearError()
        guard principalSub != nil else {
            setError("You must sign in first.")
            return
        }
        
        // If user has multiple personas but none is selected, require selection
        if personas.count > 1 && selectedPersona == nil {
            setError("Please select a persona first.")
            return
        }
        
        selectedWorkflowId = workflowId
        self.workflowId = workflowId
        
        // Use selected persona, or auto-select if only one persona exists
        let personaToSend = selectedPersona ?? (personas.count == 1 ? personas.first : nil)
        
        statusMessage = "Loading workflow items…"
        do {
            let items = try await workflowClient.fetchWorkflowItems(workflowId: workflowId, persona: personaToSend)
            workflowItems = items
            statusMessage = "Selected workflow: \(workflowId) with \(items.count) items"
        } catch {
            setError("Load workflow items failed: \(error)")
            statusMessage = ""
        }
    }
    
    func loadTravelAgents() async {
        // Load travel agents (users with persona "travel-agent"); why: populate delegation target list; side effect: network I/O.
        // Prevent concurrent/duplicate calls
        guard !isLoadingTravelAgents && travelAgents.isEmpty else {
            return
        }
        
        isLoadingTravelAgents = true
        clearError()
        
        statusMessage = "Loading travel agents…"
        do {
            let users = try await delegationClient.listUsersByPersona(persona: "travel-agent")
            travelAgents = users
            statusMessage = "Loaded \(users.count) travel agent(s)."
        } catch {
            setError("Load travel agents failed: \(error)")
            statusMessage = ""
            travelAgents = []
        }
        isLoadingTravelAgents = false
    }
    
    func createDelegation() async {
        // Create a delegation relationship; why: delegate workflow to travel agent; side effect: network I/O.
        clearError()
        guard let principalId = principalSub else {
            setError("You must sign in first.")
            return
        }
        guard let delegateId = selectedDelegateId else {
            setError("Select a travel agent first.")
            return
        }
        guard let workflowIdToDelegate = selectedWorkflowId ?? workflowId else {
            setError("Select or create a workflow first.")
            return
        }
        
        statusMessage = "Creating delegation…"
        do {
            _ = try await delegationClient.createDelegation(
                principalId: principalId,
                delegateId: delegateId,
                workflowId: workflowIdToDelegate,
                scope: ["execute"],  // Travel agents can execute workflows
                expiresInDays: delegationExpiresInDays
            )
            statusMessage = "Delegation created successfully for workflow \(workflowIdToDelegate). Expires in \(delegationExpiresInDays) days."
            // Clear selection after successful delegation
            selectedDelegateId = nil
        } catch {
            setError("Create delegation failed: \(error)")
            statusMessage = ""
        }
    }
    
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
                scope: ["read"],  // Invitations are read-only
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
    
    func runAgentDryRun() async {
        // Run the agent-runner in dry-run; why: demonstrate delegated authorization and deny/advice flows; side effect: network I/O.
        await runAgent(dryRun: true)
    }
    
    func bookTrip() async {
        // Book the trip (execute without dry-run); why: actually book the workflow items; side effect: network I/O and status changes.
        await runAgent(dryRun: false)
    }
    
    private func runAgent(dryRun: Bool) async {
        // Run the agent-runner; why: execute or simulate workflow execution; side effect: network I/O.
        clearError()
        guard let sub = principalSub else {
            setError("You must sign in first.")
            return
        }
        guard let workflow = workflowId else {
            setError("Create or select a workflow first.")
            return
        }
        
        // Check if persona is required and selected
        if personas.count > 1 && selectedPersona == nil {
            setError("Please select a persona first.")
            return
        }
        
        // Refresh token before execute to get latest autobook attributes
        statusMessage = "Refreshing access token…"
        let refreshed = await refreshAccessTokenIfNeeded()
        if !refreshed {
            // Token refresh failed, but continue with existing token
            statusMessage = "Token refresh failed, continuing with existing token…"
        }
        
        let actionLabel = dryRun ? "dry-run" : "booking"
        statusMessage = "Running agent (\(actionLabel))…"
        do {
            // Agent-runner API still expects workflowId; we pass the workflow id and selected persona.
            // If only one persona exists, use it even if not explicitly selected
            let personaToSend = selectedPersona ?? (personas.count == 1 ? personas.first : nil)
            print("DEBUG: Sending persona to agent API: \(personaToSend ?? "nil") (selectedPersona: \(selectedPersona ?? "nil"), personas: \(personas))")
            let run = try await agentRunnerClient.runAgent(workflowId: workflow, principalSub: sub, dryRun: dryRun, persona: personaToSend)
            lastAgentRun = run
            missingProfileFieldsFromAdvice = AdviceUtils.extractMissingProfileFields(from: run)
            let allowedCount = run.results.filter { $0.decision.lowercased() == "allow" }.count
            let deniedCount = run.results.filter { $0.decision.lowercased() == "deny" }.count
            let errorCount = run.results.filter { $0.status.lowercased() == "error" }.count
            
            if dryRun {
                statusMessage = "Dry run complete. Allowed=\(allowedCount), Denied=\(deniedCount), Errors=\(errorCount)."
            } else {
                statusMessage = "Booking complete. Booked=\(allowedCount), Denied=\(deniedCount), Errors=\(errorCount)."
                // Refresh workflow items to show updated status (booked/rebooked)
                if let workflowId = self.workflowId {
                    let personaToSend = selectedPersona ?? (personas.count == 1 ? personas.first : nil)
                    if let items = try? await workflowClient.fetchWorkflowItems(workflowId: workflowId, persona: personaToSend) {
                        workflowItems = items
                    }
                }
            }
            
            // Surface detailed denial/error information for visibility
            let denials = run.results.filter { $0.decision.lowercased() == "deny" || $0.status.lowercased() == "error" }
            if !denials.isEmpty {
                let detailLines = denials.map { result -> String in
                    var line = "[\(result.kind)] \(result.workflow_item_id): \(result.status.uppercased()) - \(result.decision.uppercased())"
                    if let reasonCodes = result.reason_codes, !reasonCodes.isEmpty {
                        line += " | Reason: \(reasonCodes.joined(separator: ", "))"
                    }
                    if let advice = result.advice, !advice.isEmpty {
                        let messages = advice.map { $0.message }.joined(separator: "; ")
                        line += " | \(messages)"
                    }
                    return line
                }
                statusMessage += "\n\nDetails:\n" + detailLines.joined(separator: "\n")
            }
        } catch {
            setError("Agent run failed: \(error)")
            statusMessage = ""
        }
    }
    
    func completeRequiredProfileFieldsFromAdvice() async {
        // Patch identity presence in AuthZ based on agent advice; why: demo progressive profiling without storing PII; side effect: network I/O.
        clearError()
        guard let sub = principalSub else {
            setError("You must sign in first.")
            return
        }
        if missingProfileFieldsFromAdvice.isEmpty {
            setError("No missing profile fields detected in advice.")
            return
        }
        
        statusMessage = "Updating profile presence flags…"
        do {
            try await authzClient.setIdentityPresence(principalSub: sub, fields: missingProfileFieldsFromAdvice)
            statusMessage = "Profile presence updated: \(missingProfileFieldsFromAdvice.joined(separator: ", "))"
        } catch {
            setError("Profile update failed: \(error)")
            statusMessage = ""
        }
    }
    
}

