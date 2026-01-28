//
//  Models.swift
//  FlowPilot-demo
//
//  Consolidated API models used by the desktop demo.
//

import Foundation

// MARK: - Cumbaya Templates

struct WorkflowTemplate: Codable, Identifiable {
    let template_id: String
    let domain: String
    let name: String
    
    var id: String { template_id }
}

struct WorkflowTemplatesResponse: Codable {
    let templates: [WorkflowTemplate]
}

struct LoadTemplateRequest: Codable {
    let template_id: String
    let principal_sub: String
    let start_date: String
    let persona: String?
}

struct LoadTemplateResponse: Codable {
    let workflow_id: String
    let template_id: String?
    let created_at: String?
    let start_date: String?
}

struct WorkflowItem: Codable, Identifiable {
    let item_id: String
    let kind: String
    let title: String
    let status: String
    
    // Optional detail fields
    let type: String?
    let city: String?
    let neighborhood: String?
    let star_rating: Int?
    let departure_airport: String?
    let arrival_airport: String?
    let cuisine: String?
    
    var id: String { item_id }
}

struct WorkflowItemsResponse: Codable {
    let workflow_id: String
    let items: [WorkflowItem]
}

// MARK: - Agent Runner

struct AgentRunRequest: Codable {
    let workflow_id: String
    let principal_sub: String
    let dry_run: Bool
    let persona: String?
}

struct AgentRunResponse: Codable {
    let run_id: String
    let workflow_id: String
    let principal_sub: String
    let dry_run: Bool
    let results: [AgentRunItemResult]
}

struct AgentRunItemResult: Codable, Identifiable {
    let workflow_item_id: String
    let kind: String
    let status: String
    let decision: String
    let reason_codes: [String]?
    let advice: [AgentAdvice]?
    
    var id: String { workflow_item_id }
    
    var itinerary_item_id: String { workflow_item_id }
    var outcome: String { decision }
}

struct AgentAdvice: Codable, Identifiable {
    let id = UUID()
    let type: String
    let message: String
    
    enum CodingKeys: String, CodingKey {
        case type
        case kind
        case message
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        
        let decodedType = try container.decodeIfPresent(String.self, forKey: .type)
        let decodedKind = try container.decodeIfPresent(String.self, forKey: .kind)
        self.type = decodedType ?? decodedKind ?? "info"
        
        self.message = try container.decode(String.self, forKey: .message)
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(type, forKey: .type)
        try container.encode(message, forKey: .message)
    }
}

// MARK: - Workflows

struct Workflow: Codable, Identifiable {
    let workflow_id: String
    let template_id: String
    let owner_sub: String
    let created_at: String
    let departure_date: String?
    let item_count: Int
    
    var id: String { workflow_id }
}

struct WorkflowsResponse: Codable {
    let workflows: [Workflow]
}

// MARK: - Delegation

struct CreateDelegationRequest: Codable {
    let principal_id: String
    let delegate_id: String
    let workflow_id: String?
    let scope: [String]?
    let expires_in_days: Int
}

struct DelegationResponse: Codable {
    let principal_id: String
    let delegate_id: String
    let workflow_id: String?
    let scope: [String]?
    let expires_at: String
    let created_at: String
    let revoked_at: String?
}

struct TravelAgentUser: Codable, Identifiable {
    let id: String
    let username: String
    let email: String?
    
    var displayName: String {
        username
    }
}

struct UsersByPersonaResponse: Codable {
    let users: [TravelAgentUser]
}
