// Nura Travel - Main Content View
// Travel-focused UI with modern design and Nura branding
import SwiftUI

struct ContentView: View {
    @EnvironmentObject var state: AppState
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                headerSection
                identityPanel
                workflowTemplatesPanel
                workflowsPanel
                agentPanel
                agentResultsPanel
            }
            .padding(20)
        }
        .background(
            Color(red: 0.98, green: 0.98, blue: 0.98) // Soft neutral background - Nura style
        )
        // Note: Templates are loaded automatically after sign-in (see AppState.signIn)
    }
    
    private var headerSection: some View {
        HStack(spacing: 16) {
            // Nura Logo - using SF Symbol as placeholder (replace with actual logo image if available)
            ZStack {
                Circle()
                    .fill(
                        LinearGradient(
                            colors: [
                                Color(red: 0.85, green: 0.35, blue: 0.15), // Dark red
                                Color(red: 0.95, green: 0.55, blue: 0.25)  // Orange
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                    .frame(width: 60, height: 60)
                
                Text("N")
                    .font(.system(size: 32, weight: .bold, design: .default))
                    .foregroundStyle(.white)
            }
            
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    Text("Nura")
                        .font(.system(size: 32, weight: .light, design: .default))
                        .foregroundStyle(Color(red: 0.2, green: 0.2, blue: 0.25))
                    Text("Travel")
                        .font(.system(size: 24, weight: .light, design: .default))
                        .foregroundStyle(Color(red: 0.4, green: 0.4, blue: 0.45))
                }
                Text("Intelligent travel planning with AI-powered authorization")
                    .font(.system(.subheadline, design: .default))
                    .foregroundStyle(Color(red: 0.5, green: 0.5, blue: 0.55))
            }
            Spacer()
        }
        .padding(.bottom, 8)
    }
    
    private var identityPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "person.circle.fill")
                    .foregroundStyle(Color(red: 0.3, green: 0.3, blue: 0.35)) // Soft dark - Nura style
                Text("Account")
                    .font(.headline)
                    .fontWeight(.medium)
                    .foregroundStyle(Color(red: 0.2, green: 0.2, blue: 0.25)) // Soft dark - Nura style
            }
            
            HStack(spacing: 12) {
                Button(action: {
                    Task { await state.signIn(isRegistrationPreferred: false) }
                }) {
                    Label("Sign In", systemImage: "person.badge.key.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .tint(Color(red: 0.95, green: 0.55, blue: 0.25)) // Orange - Nura logo color
                
                Button(action: {
                    state.signOut()
                }) {
                    Label("Sign Out", systemImage: "person.crop.circle.badge.xmark")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
                .disabled(state.principalSub == nil)
            }
            
            if let sub = state.principalSub {
                HStack(spacing: 8) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(.green)
                    Text("Signed in as:")
                        .foregroundStyle(.secondary)
                    Text(sub)
                        .textSelection(.enabled)
                        .font(.system(.body, design: .monospaced))
                        .foregroundStyle(.primary)
                }
                .padding(.top, 4)
            }
        }
        .padding(16)
        .background(Color.white)
        .cornerRadius(12)
        .shadow(color: Color.black.opacity(0.03), radius: 4, x: 0, y: 1) // Subtle shadow - Nura style
    }
    
    private var workflowTemplatesPanel: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Image(systemName: "map.fill")
                    .foregroundStyle(Color(red: 0.3, green: 0.3, blue: 0.35)) // Soft dark - Nura style
                Text("Plan Your Trip")
                    .font(.headline)
                    .fontWeight(.medium)
                    .foregroundStyle(Color(red: 0.2, green: 0.2, blue: 0.25)) // Soft dark - Nura style
            }
            
            VStack(alignment: .leading, spacing: 8) {
                Text("Trip Template")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                Picker("Select template", selection: Binding<String>(
                    get: { state.selectedWorkflowTemplateId ?? "" },
                    set: { newValue in state.selectedWorkflowTemplateId = newValue.isEmpty ? nil : newValue }
                )) {
                    Text("Choose a trip template…").tag("")
                    ForEach(state.workflowTemplates, id: \.id) { template in
                        Text(template.name).tag(template.id)
                    }
                }
                .pickerStyle(.menu)
                .controlSize(.large)
            }
            
            VStack(alignment: .leading, spacing: 8) {
                Text("Departure Date")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                DatePicker(
                    "",
                    selection: $state.workflowStartDate,
                    displayedComponents: [.date]
                )
                .datePickerStyle(.compact)
                .labelsHidden()
            }
            
            Button(action: {
                Task { await state.createWorkflowFromSelectedTemplate() }
            }) {
                Label("Create Trip Itinerary", systemImage: "plus.circle.fill")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .tint(Color(red: 0.95, green: 0.55, blue: 0.25)) // Orange - Nura logo color
            .disabled(state.principalSub == nil || (state.selectedWorkflowTemplateId ?? "").isEmpty)
        }
        .padding(16)
        .background(Color.white)
        .cornerRadius(12)
        .shadow(color: Color.black.opacity(0.03), radius: 4, x: 0, y: 1) // Subtle shadow - Nura style
    }
    
    private var workflowsPanel: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Image(systemName: "list.bullet.rectangle.fill")
                    .foregroundStyle(Color(red: 0.3, green: 0.3, blue: 0.35)) // Soft dark - Nura style
                Text("Trip Itinerary")
                    .font(.headline)
                    .fontWeight(.medium)
                    .foregroundStyle(Color(red: 0.2, green: 0.2, blue: 0.25)) // Soft dark - Nura style
            }
            
            if let workflowId = state.workflowId {
                VStack(alignment: .leading, spacing: 8) {
                    HStack(spacing: 8) {
                        Image(systemName: "number.circle.fill")
                            .foregroundStyle(.secondary)
                        Text("Trip ID:")
                            .foregroundStyle(.secondary)
                        Text(workflowId)
                            .textSelection(.enabled)
                            .font(.system(.body, design: .monospaced))
                    }
                    
                    if let startDate = state.workflowStartDateString {
                        HStack(spacing: 8) {
                            Image(systemName: "calendar")
                                .foregroundStyle(.secondary)
                            Text("Departure:")
                                .foregroundStyle(.secondary)
                            Text(startDate)
                                .textSelection(.enabled)
                        }
                    }
                }
                .padding(.bottom, 8)
            } else {
                Text("No active trip. Create a trip from a template above.")
                    .foregroundStyle(.secondary)
                    .italic()
            }
            
            if !state.workflowItems.isEmpty {
                Divider()
                
                Text("Itinerary Items (\(state.workflowItems.count))")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundStyle(.secondary)
                    .padding(.top, 4)
                
                ScrollView {
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(state.workflowItems) { item in
                            workflowItemRow(item)
                        }
                    }
                }
                .frame(maxHeight: 250)
            }
        }
        .padding(16)
        .background(Color.white)
        .cornerRadius(12)
        .shadow(color: Color.black.opacity(0.03), radius: 4, x: 0, y: 1) // Subtle shadow - Nura style
    }
    
    private func workflowItemRow(_ item: WorkflowItem) -> some View {
        HStack(spacing: 12) {
            Text(itemIcon(for: item.kind))
                .font(.system(size: 28))
                .frame(width: 40, height: 40)
                .background(
                    Circle()
                        .fill(Color(red: 0.3, green: 0.3, blue: 0.35).opacity(0.08)) // Subtle background - Nura style
                )
            
            VStack(alignment: .leading, spacing: 6) {
                Text(item.title)
                    .font(.body)
                    .fontWeight(.semibold)
                    .foregroundStyle(.primary)
                
                // Details line based on item kind
                if let details = formatItemDetails(item) {
                    Text(details)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                
                // Status badge
                HStack(spacing: 4) {
                    Circle()
                        .fill(statusColor(for: item.status))
                        .frame(width: 6, height: 6)
                    Text(item.status.capitalized)
                        .font(.caption)
                        .fontWeight(.medium)
                }
                .foregroundStyle(statusColor(for: item.status).opacity(0.8)) // Softened - Nura style
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(statusColor(for: item.status).opacity(0.08)) // Subtle - Nura style
                .cornerRadius(6) // Smaller radius - Nura style
            }
            
            Spacer()
        }
        .padding(12)
        .background(Color.white)
        .cornerRadius(10)
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.gray.opacity(0.15), lineWidth: 0.5) // Subtle border - Nura style
        )
    }
    
    private func statusColor(for status: String) -> Color {
        switch status.lowercased() {
        case "planned":
            return .blue
        case "executed", "completed":
            return .green
        case "denied", "error":
            return .red
        default:
            return .gray
        }
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
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Image(systemName: "sparkles")
                    .foregroundStyle(Color(red: 0.3, green: 0.3, blue: 0.35)) // Soft dark - Nura style
                Text("AI Authorization Check")
                    .font(.headline)
                    .fontWeight(.medium)
                    .foregroundStyle(Color(red: 0.2, green: 0.2, blue: 0.25)) // Soft dark - Nura style
            }
            
            VStack(spacing: 12) {
                Button(action: {
                    Task { await state.runAgentDryRun() }
                }) {
                    Label("Check Authorization (Dry Run)", systemImage: "checkmark.shield.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .tint(Color(red: 0.85, green: 0.35, blue: 0.15)) // Dark red - Nura logo color
                .disabled(state.principalSub == nil || state.workflowId == nil)
                
                Button(action: {
                    Task { await state.completeRequiredProfileFieldsFromAdvice() }
                }) {
                    Label("Apply Profile Updates", systemImage: "person.crop.circle.badge.checkmark")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
                .disabled(state.principalSub == nil || state.missingProfileFieldsFromAdvice.isEmpty)
            }
            
            if !state.missingProfileFieldsFromAdvice.isEmpty {
                HStack(spacing: 8) {
                    Image(systemName: "info.circle.fill")
                        .foregroundStyle(.orange)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Profile Updates Available")
                            .font(.caption)
                            .fontWeight(.semibold)
                        Text("Missing fields: \(state.missingProfileFieldsFromAdvice.joined(separator: ", "))")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(10)
                .background(Color.orange.opacity(0.1))
                .cornerRadius(8)
            }
        }
        .padding(16)
        .background(Color.white)
        .cornerRadius(12)
        .shadow(color: Color.black.opacity(0.03), radius: 4, x: 0, y: 1) // Subtle shadow - Nura style
    }
    
    private var agentResultsPanel: some View {
        Group {
            if let run = state.lastAgentRun {
                VStack(alignment: .leading, spacing: 16) {
            HStack {
                Image(systemName: "chart.bar.fill")
                    .foregroundStyle(Color(red: 0.3, green: 0.3, blue: 0.35)) // Soft dark - Nura style
                Text("Authorization Results")
                    .font(.headline)
                    .fontWeight(.medium)
                    .foregroundStyle(Color(red: 0.2, green: 0.2, blue: 0.25)) // Soft dark - Nura style
                        Spacer()
                        Text("Run: \(run.run_id)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                    }
                    
                    ScrollView {
                        VStack(alignment: .leading, spacing: 12) {
                            ForEach(run.results) { result in
                                resultItemView(result)
                            }
                        }
                    }
                    .frame(maxHeight: 400)
                }
        .padding(16)
        .background(Color.white)
        .cornerRadius(12)
        .shadow(color: Color.black.opacity(0.03), radius: 4, x: 0, y: 1) // Subtle shadow - Nura style
            }
        }
    }
    
    private func resultItemView(_ result: AgentRunItemResult) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                HStack(spacing: 6) {
                    Text(itemIcon(for: result.kind))
                        .font(.title3)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(result.workflow_item_id)
                            .font(.system(.caption, design: .monospaced))
                            .foregroundStyle(.secondary)
                        Text(result.kind.capitalized)
                            .font(.subheadline)
                            .fontWeight(.semibold)
                    }
                }
                Spacer()
                statusBadge(status: result.status, decision: result.decision)
            }
            
            if let reasonCodes = result.reason_codes, !reasonCodes.isEmpty {
                HStack(spacing: 6) {
                    Image(systemName: "info.circle.fill")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text(reasonCodes.joined(separator: ", "))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            
            if let advice = result.advice, !advice.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(advice) { adviceItem in
                        HStack(alignment: .top, spacing: 6) {
                            Image(systemName: adviceItem.type.lowercased() == "error" ? "exclamationmark.circle.fill" : "info.circle.fill")
                                .font(.caption2)
                                .foregroundStyle(adviceItem.type.lowercased() == "error" ? .red : .blue)
                            Text(adviceItem.message)
                                .font(.caption)
                                .foregroundStyle(adviceItem.type.lowercased() == "error" ? .red : .secondary)
                        }
                    }
                }
                .padding(.top, 4)
            }
        }
        .padding(12)
        .background(resultBackgroundColor(status: result.status, decision: result.decision))
        .cornerRadius(10)
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(borderColor(status: result.status, decision: result.decision), lineWidth: 0.5) // Subtle border - Nura style
        )
    }
    
    private func borderColor(status: String, decision: String) -> Color {
        if status.lowercased() == "error" {
            return Color.red.opacity(0.15) // Subtle - Nura style
        } else if decision.lowercased() == "deny" {
            return Color.orange.opacity(0.15) // Subtle - Nura style
        } else if decision.lowercased() == "allow" {
            return Color.green.opacity(0.15) // Subtle - Nura style
        }
        return Color.gray.opacity(0.1) // Subtle - Nura style
    }
    
    private func statusBadge(status: String, decision: String) -> some View {
        let color: Color
        let text: String
        let icon: String
        
        if status.lowercased() == "error" {
            color = .red
            text = "ERROR"
            icon = "xmark.circle.fill"
        } else if decision.lowercased() == "deny" {
            color = .orange
            text = "DENIED"
            icon = "xmark.shield.fill"
        } else if decision.lowercased() == "allow" {
            color = .green
            text = "ALLOWED"
            icon = "checkmark.shield.fill"
        } else {
            color = .gray
            text = status.uppercased()
            icon = "questionmark.circle.fill"
        }
        
        return HStack(spacing: 4) {
            Image(systemName: icon)
                .font(.caption2)
            Text(text)
                .font(.caption)
                .fontWeight(.bold)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(color.opacity(0.08)) // Subtle background - Nura style
        .foregroundStyle(color.opacity(0.8)) // Softened text - Nura style
        .cornerRadius(6) // Smaller radius - Nura style
    }
    
    private func resultBackgroundColor(status: String, decision: String) -> Color {
        if status.lowercased() == "error" {
            return Color.red.opacity(0.04) // Very subtle - Nura style
        } else if decision.lowercased() == "deny" {
            return Color.orange.opacity(0.04) // Very subtle - Nura style
        } else if decision.lowercased() == "allow" {
            return Color.green.opacity(0.04) // Very subtle - Nura style
        }
        return Color.white
    }
}
