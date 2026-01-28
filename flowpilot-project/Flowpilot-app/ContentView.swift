// FlowPilot - Main Content View
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
                delegationPanel
                invitationsPanel
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
                Text("FlowPilot")
                    .font(.system(size: 32, weight: .light, design: .default))
                    .foregroundStyle(Color(red: 0.2, green: 0.2, blue: 0.25))
                Text("App to demonstrate policy-driven authorization & delegation for AI-powered workflows")
                    .font(.system(.subheadline, design: .default))
                    .foregroundStyle(Color(red: 0.5, green: 0.5, blue: 0.55))
            }
            Spacer()
        }
        .padding(.bottom, 8)
    }
    
    private var identityPanel: some View {
        HStack(alignment: .top, spacing: 16) {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Image(systemName: "person.circle.fill")
                        .foregroundStyle(Color(red: 0.3, green: 0.3, blue: 0.35)) // Soft dark - Nura style
                    Text("Account")
                        .font(.headline)
                        .fontWeight(.medium)
                        .foregroundStyle(Color(red: 0.2, green: 0.2, blue: 0.25)) // Soft dark - Nura style
                }
                
                if let sub = state.principalSub {
                    HStack(spacing: 8) {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(.green)
                        Text("Signed in as:")
                            .foregroundStyle(.secondary)
                        if let username = state.username, !username.isEmpty {
                            Text(username)
                                .font(.body)
                                .foregroundStyle(.primary)
                            Text("(\(sub))")
                                .textSelection(.enabled)
                                .font(.system(.body, design: .monospaced))
                                .foregroundStyle(.secondary)
                        } else {
                            Text(sub)
                                .textSelection(.enabled)
                                .font(.system(.body, design: .monospaced))
                                .foregroundStyle(.primary)
                        }
                    }
                } else {
                    Text("Not signed in")
                        .foregroundStyle(.secondary)
                }
                
                // Persona selector - formatted like other pickers
                if let _ = state.principalSub {
                    if state.personas.count > 1 {
                        HStack(alignment: .center, spacing: 12) {
                            Text("User persona")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                                .frame(width: 100, alignment: .leading)
                            Picker("", selection: Binding<String>(
                                get: { state.selectedPersona ?? "" },
                                set: { newValue in
                                    state.selectedPersona = newValue.isEmpty ? nil : newValue
                                }
                            )) {
                                Text("Select persona…").tag("")
                                ForEach(state.personas, id: \.self) { persona in
                                    Text(persona).tag(persona)
                                }
                            }
                            .pickerStyle(.menu)
                            .controlSize(.large)
                        }
                    } else if state.personas.count == 1 {
                        HStack(alignment: .center, spacing: 12) {
                            Text("Persona")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                                .frame(width: 100, alignment: .leading)
                            HStack(spacing: 8) {
                                Image(systemName: "person.badge.shield.checkmark.fill")
                                    .foregroundStyle(Color(red: 0.95, green: 0.55, blue: 0.25))
                                Text(state.personas.first ?? "")
                                    .font(.body)
                                    .foregroundStyle(.primary)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.vertical, 8)
                            .padding(.horizontal, 12)
                            .background(Color(red: 0.98, green: 0.98, blue: 0.98))
                            .cornerRadius(8)
                        }
                    }
                }
            }
            
            Spacer()
            
            if state.principalSub == nil {
                // Show sign-in form
                SignInFormView()
            } else {
                Button(action: {
                    state.signOut()
                }) {
                    Label("Sign Out", systemImage: "person.crop.circle.badge.xmark")
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .tint(Color(red: 0.95, green: 0.55, blue: 0.25))
                .frame(width: 140)
            }
        }
        .padding(16)
        .background(Color.white)
        .cornerRadius(12)
        .shadow(color: Color.black.opacity(0.03), radius: 4, x: 0, y: 1) // Subtle shadow - Nura style
    }
    
    private var workflowTemplatesPanel: some View {
        let personaRequired = state.personas.count > 1 && state.selectedPersona == nil
        
        return HStack(alignment: .top, spacing: 16) {
            VStack(alignment: .leading, spacing: 16) {
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
                
                HStack(alignment: .center, spacing: 12) {
                    Text("Trip Template")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .frame(width: 100, alignment: .leading)
                    Picker("", selection: Binding<String>(
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
                    
                    Text("→")
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
            }
            
            Spacer()
            
            Button(action: {
                Task { await state.createWorkflowFromSelectedTemplate() }
            }) {
                Label("Create Trip Itinerary", systemImage: "plus.circle.fill")
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .tint(Color(red: 0.95, green: 0.55, blue: 0.25)) // Orange - Nura logo color
            .disabled(
                state.principalSub == nil || 
                (state.selectedWorkflowTemplateId ?? "").isEmpty ||
                (state.personas.count > 1 && state.selectedPersona == nil)
            )
            .frame(width: 180)
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
            
            // Workflow selection (existing workflows)
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
                Text("Trip Itinerary")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .frame(width: 100, alignment: .leading)
                if state.workflows.isEmpty {
                    Text("No trips available. Create a trip from a template above.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.vertical, 8)
                } else {
                    Picker("", selection: Binding<String>(
                        get: { state.selectedWorkflowId ?? "" },
                        set: { newValue in
                            state.selectedWorkflowId = newValue.isEmpty ? nil : newValue
                            if !newValue.isEmpty {
                                Task { await state.selectWorkflow(newValue) }
                            }
                        }
                    )) {
                        Text("Choose an existing trip…").tag("")
                        ForEach(state.workflows, id: \.id) { workflow in
                            Text("\(workflow.workflow_id) - \(workflow.departure_date ?? "no date") (\(workflow.item_count) items)").tag(workflow.id)
                        }
                    }
                    .pickerStyle(.menu)
                    .controlSize(.large)
                    .disabled(personaRequired)
                }
            }
            
            if let workflowId = state.workflowId {
                Divider()
                
                VStack(alignment: .leading, spacing: 8) {
                    // Show delegation info if travel-agent persona and not the owner
                    if state.selectedPersona == "travel-agent",
                       let principalSub = state.principalSub,
                       let currentWorkflow = state.workflows.first(where: { $0.workflow_id == workflowId }),
                       currentWorkflow.owner_sub != principalSub {
                        HStack(spacing: 8) {
                            Image(systemName: "person.2.badge.gearshape.fill")
                                .foregroundStyle(.orange)
                            Text("Delegated by owner:")
                                .foregroundStyle(.secondary)
                            Text(currentWorkflow.owner_sub)
                                .textSelection(.enabled)
                                .font(.system(.body, design: .monospaced))
                                .foregroundStyle(.primary)
                        }
                        .padding(.bottom, 4)
                    }
                    
                    HStack(spacing: 8) {
                        Image(systemName: "number.circle.fill")
                            .foregroundStyle(.secondary)
                        Text("Trip ID:")
                            .foregroundStyle(.secondary)
                        Text(workflowId)
                            .textSelection(.enabled)
                            .font(.system(.body, design: .monospaced))
                        
                        // Show departure date next to Trip ID
                        if let currentWorkflow = state.workflows.first(where: { $0.workflow_id == workflowId }),
                           let departureDate = currentWorkflow.departure_date {
                            Text("|")
                                .foregroundStyle(.secondary)
                            Image(systemName: "calendar")
                                .foregroundStyle(.secondary)
                            Text(departureDate)
                                .foregroundStyle(.primary)
                        }
                    }
                }
                .padding(.bottom, 8)
            } else {
                Text("No active trip. Create a trip from a template above or select an existing trip.")
                    .foregroundStyle(.secondary)
                    .italic()
                    .padding(.top, 8)
            }
            
            if !state.workflowItems.isEmpty {
                ScrollView {
                    VStack(alignment: .leading, spacing: 4) {
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
    
    private var delegationPanel: some View {
        let personaRequired = state.personas.count > 1 && state.selectedPersona == nil
        
        return HStack(alignment: .top, spacing: 16) {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Image(systemName: "person.2.badge.gearshape.fill")
                        .foregroundStyle(Color(red: 0.3, green: 0.3, blue: 0.35))
                    Text("Delegations")
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
                    Text("Travel Agent")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .frame(width: 100, alignment: .leading)
                    Picker("", selection: Binding<String>(
                        get: { state.selectedDelegateId ?? "" },
                        set: { newValue in state.selectedDelegateId = newValue.isEmpty ? nil : newValue }
                    )) {
                        Text("Choose a travel agent…").tag("")
                        ForEach(state.travelAgents) { agent in
                            Text(agent.displayName).tag(agent.id)
                        }
                    }
                    .pickerStyle(.menu)
                    .controlSize(.large)
                    .disabled(personaRequired)
                    .task {
                        // Use .task instead of .onAppear to ensure it only runs once per view lifecycle
                        // Only load if signed in and agents list is empty
                        if state.principalSub != nil && state.travelAgents.isEmpty {
                            await state.loadTravelAgents()
                        }
                    }
                    
                    Text("→")
                        .foregroundStyle(.secondary)
                    
                    Stepper(value: $state.delegationExpiresInDays, in: 1...365, step: 1) {
                        Text("\(state.delegationExpiresInDays) days")
                            .foregroundStyle(.primary)
                    }
                    .disabled(personaRequired)
                }
            }
            
            Spacer()
            
            Button(action: {
                Task { await state.createDelegation() }
            }) {
                Label("Delegate Trip", systemImage: "arrow.right.circle.fill")
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .tint(Color(red: 0.95, green: 0.55, blue: 0.25))
            .disabled(
                state.principalSub == nil ||
                (state.selectedDelegateId ?? "").isEmpty ||
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
                        Text("Invite a user…").tag("")
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
                    
                    Text("→")
                        .foregroundStyle(.secondary)
                    
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
        .padding(8)
        .background(Color.white)
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
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
            HStack(alignment: .top, spacing: 16) {
                HStack {
                    Image(systemName: "chart.bar.fill")
                        .foregroundStyle(Color(red: 0.3, green: 0.3, blue: 0.35))
                    Text("Authorization")
                        .font(.headline)
                        .fontWeight(.medium)
                        .foregroundStyle(Color(red: 0.2, green: 0.2, blue: 0.25))
                }
                
                Spacer()
                
                HStack(spacing: 12) {
                    Button(action: {
                        Task { await state.runAgentDryRun() }
                    }) {
                        Label("Dry Run", systemImage: "checkmark.shield.fill")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.large)
                    .disabled(state.principalSub == nil || state.workflowId == nil || personaRequired)
                    
                    Button(action: {
                        Task { await state.bookTrip() }
                    }) {
                        Label("Book Trip", systemImage: "calendar.badge.checkmark")
                    }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.large)
                    .tint(Color(red: 0.85, green: 0.35, blue: 0.15))
                    .disabled(state.principalSub == nil || state.workflowId == nil || personaRequired)
                }
            }
            
            if let run = state.lastAgentRun {
                HStack(spacing: 8) {
                    Image(systemName: "number.circle.fill")
                        .foregroundStyle(.secondary)
                    Text("Run ID:")
                        .foregroundStyle(.secondary)
                    Text(run.run_id)
                        .textSelection(.enabled)
                        .font(.system(.body, design: .monospaced))
                }
                .padding(.bottom, 8)
                
                ScrollView {
                    VStack(alignment: .leading, spacing: 4) {
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
        .padding(8)
        .background(Color.white)
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
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
            text = "NO AUTOBOOKING"
            icon = "xmark.shield.fill"
        } else if decision.lowercased() == "allow" {
            color = .green
            text = "AUTOBOOK READY"
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
