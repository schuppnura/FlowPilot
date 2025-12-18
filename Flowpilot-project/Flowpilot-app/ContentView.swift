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
            agentResultsPanel
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
            
            DatePicker(
                "Start date:",
                selection: $state.workflowStartDate,
                displayedComponents: [.date]
            )
            .datePickerStyle(.compact)
            
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
            
            if let startDate = state.workflowStartDateString {
                HStack(spacing: 8) {
                    Text("Start date:").foregroundStyle(.secondary)
                    Text(startDate).textSelection(.enabled)
                }
            }
            
            if !state.workflowItems.isEmpty {
                Divider()
                
                Text("Workflow Items (\(state.workflowItems.count))").font(.subheadline).foregroundStyle(.secondary)
                
                ScrollView {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(state.workflowItems) { item in
                            workflowItemRow(item)
                        }
                    }
                }
                .frame(maxHeight: 200)
            }
        }
        .padding(12)
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.gray.opacity(0.3)))
    }
    
    private func workflowItemRow(_ item: WorkflowItem) -> some View {
        HStack(spacing: 8) {
            Text(itemIcon(for: item.kind))
                .font(.title3)
            
            VStack(alignment: .leading, spacing: 4) {
                Text(item.title)
                    .font(.body)
                    .fontWeight(.medium)
                
                // Details line based on item kind
                if let details = formatItemDetails(item) {
                    Text(details)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                
                // Status badge
                Text(item.status)
                    .font(.caption2)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.blue.opacity(0.1))
                    .foregroundStyle(.blue)
                    .cornerRadius(3)
            }
            
            Spacer()
        }
        .padding(8)
        .background(Color.gray.opacity(0.05))
        .cornerRadius(6)
    }
    
    private func formatItemDetails(_ item: WorkflowItem) -> String? {
        var parts: [String] = []
        
        switch item.kind.lowercased() {
        case "hotel":
            if let type = item.type {
                parts.append(type)
            }
            if let city = item.city {
                parts.append(city)
            }
            if let neighborhood = item.neighborhood {
                parts.append(neighborhood)
            }
            if let stars = item.star_rating {
                parts.append(String(repeating: "⭐️", count: stars))
            }
            
        case "flight":
            if let departure = item.departure_airport, let arrival = item.arrival_airport {
                parts.append("\(departure) → \(arrival)")
            }
            
        case "restaurant":
            if let cuisine = item.cuisine {
                parts.append(cuisine)
            }
            if let stars = item.star_rating {
                let michelinStars = String(repeating: "⭐️", count: stars)
                parts.append("\(michelinStars) Michelin")
            }
            
        default:
            if let type = item.type {
                parts.append(type)
            }
        }
        
        return parts.isEmpty ? nil : parts.joined(separator: " • ")
    }
    
    private func itemIcon(for kind: String) -> String {
        switch kind.lowercased() {
        case "flight":
            return "✈️"
        case "hotel":
            return "🏨"
        case "restaurant":
            return "🍴"
        case "museum":
            return "🏛️"
        case "train":
            return "🚆"
        default:
            return "📋"
        }
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
    
    private var agentResultsPanel: some View {
        Group {
            if let run = state.lastAgentRun {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Agent run results (\(run.run_id))").font(.headline)
                    
                    ScrollView {
                        VStack(alignment: .leading, spacing: 8) {
                            ForEach(run.results) { result in
                                resultItemView(result)
                            }
                        }
                    }
                    .frame(maxHeight: 400)
                }
                .padding(12)
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.gray.opacity(0.3)))
            }
        }
    }
    
    private func resultItemView(_ result: AgentRunItemResult) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(result.workflow_item_id)
                    .font(.system(.body, design: .monospaced))
                    .bold()
                Spacer()
                Text("[\(result.kind)]")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            
            HStack(spacing: 8) {
                statusBadge(status: result.status, decision: result.decision)
                
                if let reasonCodes = result.reason_codes, !reasonCodes.isEmpty {
                    Text("Reasons: \(reasonCodes.joined(separator: ", "))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            
            if let advice = result.advice, !advice.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(advice) { adviceItem in
                        HStack(alignment: .top, spacing: 4) {
                            Text("•")
                                .font(.caption)
                            Text(adviceItem.message)
                                .font(.caption)
                                .foregroundStyle(adviceItem.type.lowercased() == "error" ? .red : .secondary)
                        }
                    }
                }
                .padding(.leading, 8)
            }
        }
        .padding(8)
        .background(resultBackgroundColor(status: result.status, decision: result.decision))
        .cornerRadius(6)
    }
    
    private func statusBadge(status: String, decision: String) -> some View {
        let color: Color
        let text: String
        
        if status.lowercased() == "error" {
            color = .red
            text = "ERROR"
        } else if decision.lowercased() == "deny" {
            color = .orange
            text = "DENIED"
        } else if decision.lowercased() == "allow" {
            color = .green
            text = "ALLOWED"
        } else {
            color = .gray
            text = status.uppercased()
        }
        
        return Text(text)
            .font(.caption)
            .fontWeight(.semibold)
            .padding(.horizontal, 8)
            .padding(.vertical, 2)
            .background(color.opacity(0.2))
            .foregroundStyle(color)
            .cornerRadius(4)
    }
    
    private func resultBackgroundColor(status: String, decision: String) -> Color {
        if status.lowercased() == "error" {
            return Color.red.opacity(0.05)
        } else if decision.lowercased() == "deny" {
            return Color.orange.opacity(0.05)
        } else if decision.lowercased() == "allow" {
            return Color.green.opacity(0.05)
        }
        return Color.gray.opacity(0.05)
    }
    
    private var statusPanel: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Status / Errors").font(.headline)
            
            if !state.statusMessage.isEmpty {
                ScrollView {
                    Text(state.statusMessage)
                        .font(.system(.body, design: .monospaced))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(maxHeight: 300)
            }
            
            if !state.errorMessage.isEmpty {
                ScrollView {
                    Text(state.errorMessage)
                        .foregroundStyle(.red)
                        .font(.system(.body, design: .monospaced))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(maxHeight: 150)
            }
        }
        .padding(12)
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.gray.opacity(0.3)))
    }
}
