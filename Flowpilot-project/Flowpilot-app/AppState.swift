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
    @Published var idToken: String?
    @Published var accessToken: String?
    
    @Published var workflowTemplates: [WorkflowTemplate] = []
    @Published var selectedWorkflowTemplateId: String?
    @Published var workflowStartDate: Date = Date()
    @Published var workflowId: String?
    @Published var workflowStartDateString: String?
    @Published var workflowItems: [WorkflowItem] = []
    
    @Published var lastAgentRun: AgentRunResponse?
    @Published var missingProfileFieldsFromAdvice: [String] = []
    
    @Published var statusMessage: String = ""
    @Published var errorMessage: String = ""
    
    let oidcClient = KeycloakOidcClient(
        issuer: AppConfig.keycloakIssuer,
        clientId: AppConfig.oidcClientId,
        redirectUri: AppConfig.oidcRedirectUri,
        scopes: AppConfig.oidcScopes
    )
    
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
    
    func clearError() {
        // Clear error state; why: keep UI feedback current; side effect: mutates published state.
        errorMessage = ""
    }
    
    func setError(_ message: String) {
        // Set error state; why: provide visible diagnostics; side effect: mutates published state.
        errorMessage = message
    }
    
    func signOut() {
        // Sign out and clear transient demo state; why: ensure next demo run is clean; side effect: mutates published state.
        // Also performs Keycloak logout to terminate the SSO session
        
        // Capture idToken before clearing
        let idTokenToRevoke = idToken
        
        // Clear local state immediately
        principalSub = nil
        idToken = nil
        accessToken = nil
        
        workflowId = nil
        workflowStartDateString = nil
        workflowItems = []
        workflowTemplates = []
        selectedWorkflowTemplateId = nil
        
        lastAgentRun = nil
        missingProfileFieldsFromAdvice = []
        
        statusMessage = "Signing out..."
        errorMessage = ""
        
        // Perform Keycloak logout asynchronously
        if let token = idTokenToRevoke {
            Task {
                do {
                    try await oidcClient.signOut(idToken: token)
                    await MainActor.run {
                        statusMessage = "Signed out."
                    }
                } catch {
                    // Logout failed, but we've already cleared local state
                    await MainActor.run {
                        statusMessage = "Signed out (local only)."
                    }
                }
            }
        } else {
            statusMessage = "Signed out."
        }
    }
    
    func openKeycloakAccountManagement() {
        // Open Keycloak account management
        // The account console will handle authentication automatically
        // If user is not signed in, it will redirect to login
        let issuerString = AppConfig.keycloakIssuer.absoluteString
        let baseUrl = issuerString.components(separatedBy: "/realms/").first ?? issuerString
        let realm = "flowpilot"
        
        // Use account-console client with proper OAuth flow
        // The account console uses client_id=account-console
        let accountUrl = "\(baseUrl)/realms/\(realm)/protocol/openid-connect/auth?client_id=account-console&redirect_uri=\(baseUrl.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? baseUrl)/realms/\(realm)/account&response_type=code&scope=openid%20profile&code_challenge_method=S256"
        
        guard let url = URL(string: accountUrl) else {
            // Fallback to direct account console URL
            let fallbackUrl = "\(baseUrl)/realms/\(realm)/account"
            if let fallback = URL(string: fallbackUrl) {
                NSWorkspace.shared.open(fallback)
                statusMessage = "Opening Keycloak account management. Please sign in if prompted."
            } else {
                setError("Unable to open Keycloak account management.")
            }
            return
        }
        
        NSWorkspace.shared.open(url)
        statusMessage = "Opening Keycloak account management..."
    }
    
    func signIn(isRegistrationPreferred: Bool) async {
        // Perform OIDC sign-in/registration; why: bind workflows to an authenticated principal; side effect: opens browser UI.
        clearError()
        statusMessage = isRegistrationPreferred ? "Opening registration…" : "Opening sign-in…"
        
        do {
            let (tokens, sub) = try await oidcClient.signIn(isRegistrationPreferred: isRegistrationPreferred)
            principalSub = sub
            idToken = tokens.id_token
            accessToken = tokens.access_token
            statusMessage = "Signed in. sub=\(sub)"
            
            // Auto-load templates post sign-in; why: remove manual step and keep UX consistent.
            await loadWorkflowTemplates(forceReload: true)
        } catch {
            setError("Sign-in failed: \(error)")
            statusMessage = ""
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
        
        // Format start date as ISO 8601 date string (YYYY-MM-DD)
        let dateFormatter = ISO8601DateFormatter()
        dateFormatter.formatOptions = [.withFullDate]
        let startDateString = dateFormatter.string(from: workflowStartDate)
        
        statusMessage = "Creating workflow…"
        do {
            // Backend still creates a "trip"; we treat it as a workflow id in the UI/state.
            let newWorkflowId = try await workflowClient.loadTemplate(templateId: templateId, principalSub: sub, startDate: startDateString)
            workflowId = newWorkflowId
            workflowStartDateString = startDateString
            
            // Fetch workflow items immediately after creation
            let items = try await workflowClient.fetchWorkflowItems(workflowId: newWorkflowId)
            workflowItems = items
            
            statusMessage = "Created workflow: \(newWorkflowId) (start: \(startDateString)) with \(items.count) items"
        } catch {
            setError("Create workflow failed: \(error)")
            statusMessage = ""
        }
    }
    
    func runAgentDryRun() async {
        // Run the agent-runner in dry-run; why: demonstrate delegated authorization and deny/advice flows; side effect: network I/O.
        clearError()
        guard let sub = principalSub else {
            setError("You must sign in first.")
            return
        }
        guard let workflow = workflowId else {
            setError("Create a workflow first.")
            return
        }
        
        statusMessage = "Running agent (dry-run)…"
        do {
            // Agent-runner API still expects workflowId; we pass the workflow id.
            let run = try await agentRunnerClient.runAgent(workflowId: workflow, principalSub: sub, dryRun: true)
            lastAgentRun = run
            missingProfileFieldsFromAdvice = AdviceUtils.extractMissingProfileFields(from: run)
            let allowedCount = run.results.filter { $0.decision.lowercased() == "allow" }.count
            let deniedCount = run.results.filter { $0.decision.lowercased() == "deny" }.count
            let errorCount = run.results.filter { $0.status.lowercased() == "error" }.count
            statusMessage = "Agent run complete. Allowed=\(allowedCount), Denied=\(deniedCount), Errors=\(errorCount)."
            
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

