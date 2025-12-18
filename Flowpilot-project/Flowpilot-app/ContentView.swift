// This view expects AppState.workflowTemplates to be [WorkflowTemplate]
import SwiftUI

struct ContentView: View {
    @EnvironmentObject var state: AppState
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            identityPanel
            workflowTemplatesPanel
            workflowsPanel
            agentPanel
            statusPanel
            Spacer()
        }
        .padding(16)
        // Note: Templates are loaded automatically after sign-in (see AppState.signIn)
    }
    
    private var identityPanel: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Identity").font(.headline)
            
            HStack(spacing: 12) {
                Button("Register") {
                    Task { await state.signIn(isRegistrationPreferred: true) }
                }
                Button("Sign in") {
                    Task { await state.signIn(isRegistrationPreferred: false) }
                }
                Button("Sign out") {
                    state.signOut()
                }
                .disabled(state.principalSub == nil)
            }
            
            HStack(spacing: 8) {
                Text("Principal sub:").foregroundStyle(.secondary)
                Text(state.principalSub ?? "—").textSelection(.enabled)
            }
        }
        .padding(12)
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.gray.opacity(0.3)))
    }
    
    private var workflowTemplatesPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Workflow templates").font(.headline)
            
            Picker("Select template", selection: Binding<String>(
                get: { state.selectedWorkflowTemplateId ?? "" },
                set: { newValue in state.selectedWorkflowTemplateId = newValue.isEmpty ? nil : newValue }
            )) {
                Text("Select…").tag("")
                ForEach(state.workflowTemplates, id: \.id) { template in
                    Text("\(template.name) (\(template.id))").tag(template.id)
                }
            }
            .pickerStyle(.menu)
            
            Button("Create workflow") {
                Task { await state.createWorkflowFromSelectedTemplate() }
            }
            .disabled(state.principalSub == nil || (state.selectedWorkflowTemplateId ?? "").isEmpty)
        }
        .padding(12)
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.gray.opacity(0.3)))
    }
    
    private var workflowsPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Workflows").font(.headline)
            
            HStack(spacing: 8) {
                Text("Workflow ID:").foregroundStyle(.secondary)
                Text(state.workflowId ?? "—").textSelection(.enabled)
            }
        }
        .padding(12)
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.gray.opacity(0.3)))
    }
    
    private var agentPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Agent runner").font(.headline)
            
            HStack(spacing: 12) {
                Button("Execute workflow (dry-run)") {
                    Task { await state.runAgentDryRun() }
                }
                .disabled(state.principalSub == nil || state.workflowId == nil)
                
                Button("Apply advice (mark profile fields present)") {
                    Task { await state.completeRequiredProfileFieldsFromAdvice() }
                }
                .disabled(state.principalSub == nil || state.missingProfileFieldsFromAdvice.isEmpty)
            }
            
            if !state.missingProfileFieldsFromAdvice.isEmpty {
                Text("Missing profile fields: \(state.missingProfileFieldsFromAdvice.joined(separator: ", "))")
                    .foregroundStyle(.secondary)
            }
        }
        .padding(12)
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.gray.opacity(0.3)))
    }
    
    private var statusPanel: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Status / Errors").font(.headline)
            
            if !state.statusMessage.isEmpty {
                Text(state.statusMessage)
            }
            
            if !state.errorMessage.isEmpty {
                Text(state.errorMessage).foregroundStyle(.red)
            }
        }
        .padding(12)
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.gray.opacity(0.3)))
    }
}
