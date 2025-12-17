//
//  AppState.swift
//  FlowPilot-demo
//
//

import Foundation
import Combine

@MainActor
final class AppState: ObservableObject {
    @Published var principalSub: String?
    @Published var idToken: String?
    @Published var accessToken: String?
    
    @Published var workflowTemplates: [TripTemplate] = []
    @Published var selectedWorkflowTemplateId: String?
    @Published var workflowId: String?
    
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
    let workflowClient = FlowPilotApiClient()
    let agentRunnerClient = FlowPilotAIAgentApiClient()
    
    // Profile API is now embedded into authz-api; keep it as an AuthZ client.
    let authzClient = AuthzApiClient(baseUrl: AppConfig.authzBaseUrl)
    
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
        principalSub = nil
        idToken = nil
        accessToken = nil
        
        workflowId = nil
        workflowTemplates = []
        selectedWorkflowTemplateId = nil
        
        lastAgentRun = nil
        missingProfileFieldsFromAdvice = []
        
        statusMessage = "Signed out."
        errorMessage = ""
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
        
        statusMessage = "Creating workflow…"
        do {
            // Backend still creates a "trip"; we treat it as a workflow id in the UI/state.
            let newWorkflowId = try await workflowClient.loadTemplate(templateId: templateId, principalSub: sub)
            workflowId = newWorkflowId
            statusMessage = "Created workflow: \(newWorkflowId)"
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
            // Agent-runner API still expects tripId; we pass the workflow id.
            let run = try await agentRunnerClient.runAgent(workflowId: workflow, principalSub: sub, dryRun: true)
            lastAgentRun = run
            missingProfileFieldsFromAdvice = AdviceUtils.extractMissingProfileFields(from: run)
            let allowedCount = run.results.filter { $0.decision.lowercased() == "allow" }.count
            let deniedCount = run.results.filter { $0.decision.lowercased() == "deny" }.count
            let errorCount = run.results.filter { $0.status.lowercased() == "error" }.count
            statusMessage = "Agent run complete. Allowed=\(allowedCount), Denied=\(deniedCount), Errors=\(errorCount)."
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

