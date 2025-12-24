// Policy-driven Authorization - Main Content View
// Policy-driven authorization UI with modern design
import SwiftUI
import AppKit

struct ContentView: View {
    @EnvironmentObject var state: AppState
    
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                headerSection
                identityPanel
                workflowTemplatesPanel
                workflowsPanel
                authorizationResultsPanel
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
            // Nura Logo
            Image("nura_logo")
                .resizable()
                .aspectRatio(contentMode: .fit)
                .frame(width: 60, height: 60)
            
            VStack(alignment: .leading, spacing: 4) {
                Text("Policy-driven Authorization")
                    .font(.system(size: 32, weight: .light, design: .default))
                    .foregroundStyle(Color(red: 0.2, green: 0.2, blue: 0.25))
                Text("Policy-driven authorization with AI-powered workflows")
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
                .tint(Color(red: 0.95, green: 0.55, blue: 0.25))
                
                Button(action: {
                    state.signOut()
                }) {
                    Label("Sign Out", systemImage: "person.crop.circle.badge.xmark")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .controlSize(.large)
                .disabled(state.principalSub == nil)
                
                // Persona display/selector - replaces "My Account" button position
                if let _ = state.principalSub {
                    if state.personas.count == 1 {
                        // Single persona - display it in the button row
                        HStack(spacing: 8) {
                            Image(systemName: "person.badge.shield.checkmark.fill")
                                .foregroundStyle(Color(red: 0.95, green: 0.55, blue: 0.25))
                            Text(state.personas.first ?? "")
                                .font(.body)
                                .foregroundStyle(.primary)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                        .padding(.horizontal, 12)
                        .background(Color(red: 0.98, green: 0.98, blue: 0.98))
                        .cornerRadius(8)
                    } else if state.personas.count > 1 {
                        // Multiple personas - show selector in the button row
                        Picker("Select persona", selection: Binding<String>(
                            get: { state.selectedPersona ?? "" },
                            set: { newValue in
                                state.selectedPersona = newValue.isEmpty ? nil : newValue
                            }
                        )) {
                            Text("Select persona").tag("")
                            ForEach(state.personas, id: \.self) { persona in
                                Text(persona).tag(persona)
                            }
                        }
                        .pickerStyle(.menu)
                        .controlSize(.large)
                        .frame(maxWidth: .infinity)
                    } else {
                        // No personas found - show placeholder for debugging
                        Text("No persona")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 10)
                            .padding(.horizontal, 12)
                            .background(Color(red: 0.98, green: 0.98, blue: 0.98))
                            .cornerRadius(8)
                    }
                }
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
        let personaRequired = state.personas.count > 1 && state.selectedPersona == nil
        
        return VStack(alignment: .leading, spacing: 16) {
            HStack {
                Image(systemName: "map.fill")
                    .foregroundStyle(Color(red: 0.3, green: 0.3, blue: 0.35)) // Soft dark - Nura style
                Text("Plan Your Trip")
                    .font(.headline)
                    .fontWeight(.medium)
                    .foregroundStyle(Color(red: 0.2, green: 0.2, blue: 0.25)) // Soft dark - Nura style
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
                .disabled(personaRequired)
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
                .disabled(personaRequired)
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
            .disabled(
                state.principalSub == nil || 
                (state.selectedWorkflowTemplateId ?? "").isEmpty ||
                (state.personas.count > 1 && state.selectedPersona == nil)
            )
        }
        .padding(16)
        .background(Color.white)
        .cornerRadius(12)
        .shadow(color: Color.black.opacity(0.03), radius: 4, x: 0, y: 1) // Subtle shadow - Nura style
    }
    
    private var workflowsPanel: some View {
        let personaRequired = state.personas.count > 1 && state.selectedPersona == nil
        
        return VStack(alignment: .leading, spacing: 16) {
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
        .opacity(personaRequired ? 0.5 : 1.0)
    }
    
    private func workflowItemRow(_ item: WorkflowItem) -> some View {
        HStack(alignment: .top, spacing: 12) {
            // Kind - aligned with "Itinerary Items" header and bold
            Text(item.kind)
                .font(.subheadline)
                .fontWeight(.bold)
                .foregroundStyle(.primary)
                .frame(width: 80, alignment: .leading)
            
            // Rest of the details
            Text(formatItemDetailsRest(item))
                .font(.system(.body, design: .default))
                .foregroundStyle(.primary)
            
            Spacer()
            
            // Status badge
            HStack(spacing: 4) {
                Circle()
                    .fill(statusColor(for: item.status))
                    .frame(width: 6, height: 6)
                Text(item.status.capitalized)
                    .font(.caption)
                    .fontWeight(.medium)
            }
            .foregroundStyle(statusColor(for: item.status).opacity(0.8))
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(statusColor(for: item.status).opacity(0.08))
            .cornerRadius(6)
        }
        .padding(12)
        .background(Color.white)
        .cornerRadius(10)
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.gray.opacity(0.15), lineWidth: 0.5)
        )
    }
    
    private func formatItemDetailsRest(_ item: WorkflowItem) -> String {
        var parts: [String] = []
        
        // Show: type, title (kind is shown separately and bold)
        if let type = item.type {
            parts.append(type)
        }
        parts.append(item.title)
        
        // Then add optional fields if present (in specified order)
        if let star_rating = item.star_rating {
            parts.append("⭐\(star_rating)")
        }
        if let cuisine = item.cuisine {
            parts.append(cuisine)
        }
        if let city = item.city {
            parts.append(city)
        }
        if let neighborhood = item.neighborhood {
            parts.append(neighborhood)
        }
        if let departure_airport = item.departure_airport {
            parts.append("\(departure_airport)→")
        }
        if let arrival_airport = item.arrival_airport {
            parts.append(arrival_airport)
        }
        
        return parts.joined(separator: " • ")
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
    
    private var authorizationResultsPanel: some View {
        let personaRequired = state.personas.count > 1 && state.selectedPersona == nil
        
        return VStack(alignment: .leading, spacing: 16) {
            HStack {
                Image(systemName: "chart.bar.fill")
                    .foregroundStyle(Color(red: 0.3, green: 0.3, blue: 0.35))
                Text("Authorization")
                    .font(.headline)
                    .fontWeight(.medium)
                    .foregroundStyle(Color(red: 0.2, green: 0.2, blue: 0.25))
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
                .tint(Color(red: 0.85, green: 0.35, blue: 0.15))
                .disabled(state.principalSub == nil || state.workflowId == nil || personaRequired)
            }
            
            if let run = state.lastAgentRun {
                Divider()
                    .padding(.vertical, 8)
                
                HStack {
                    Text("Run: \(run.run_id)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                    Spacer()
                }
                
                Text("Authorization Results (\(run.results.count))")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundStyle(.secondary)
                    .padding(.top, 4)
                
                ScrollView {
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(run.results) { result in
                            resultItemView(result)
                        }
                    }
                }
                .frame(maxHeight: 400)
            }
        }
        .padding(16)
        .background(Color.white)
        .cornerRadius(12)
        .shadow(color: Color.black.opacity(0.03), radius: 4, x: 0, y: 1)
        .opacity(personaRequired ? 0.5 : 1.0)
    }
    
    private func resultItemView(_ result: AgentRunItemResult) -> some View {
        HStack(alignment: .top, spacing: 12) {
            // Kind - aligned with "Authorization" header and bold
            Text(result.kind)
                .font(.subheadline)
                .fontWeight(.bold)
                .foregroundStyle(.primary)
                .frame(width: 80, alignment: .leading)
            
            // Workflow item ID and reason codes on the same line
            VStack(alignment: .leading, spacing: 4) {
                Text(result.workflow_item_id)
                    .font(.system(.body, design: .monospaced))
                    .foregroundStyle(.primary)
                
                // Show reason codes if denied
                if result.decision.lowercased() == "deny", let reasonCodes = result.reason_codes, !reasonCodes.isEmpty {
                    Text(reasonCodes.joined(separator: ", "))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            
            Spacer()
            
            // Status badge
            statusBadge(status: result.status, decision: result.decision)
        }
        .padding(12)
        .background(Color.white)
        .cornerRadius(10)
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.gray.opacity(0.15), lineWidth: 0.5)
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
