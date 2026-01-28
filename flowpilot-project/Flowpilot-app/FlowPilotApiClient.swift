import Foundation

// Shared HTTP error type used across demo API clients.
enum ApiClientError: Error, LocalizedError {
    case httpError(Int, String)
    case invalidResponse(String)
    case networkError(String)

    var errorDescription: String? {
        switch self {
        case .httpError(let status, let body):
            return "HTTP error \(status): \(body)"
        case .invalidResponse(let message):
            return "Invalid response: \(message)"
        case .networkError(let message):
            return "Network error: \(message)"
        }
    }
}

/// Primary client for the FlowPilot domain/services API (system-of-record).
/// Backward compatibility: the legacy names remain available via typealiases below.
final class FlowPilotApiClient {
    private let baseUrl: URL
    private let urlSession: URLSession
    private let accessTokenProvider: () -> String?

    init(baseUrl: URL = AppConfig.servicesBaseUrl, urlSession: URLSession = .shared, accessTokenProvider: @escaping () -> String? = { nil }) {
        // Initialize client with a base URL; why: keep endpoint routing explicit and testable; side effect: none.
        // Uses standard URLSession for Cloud Run services with proper TLS certificates.
        self.baseUrl = baseUrl
        self.urlSession = urlSession
        self.accessTokenProvider = accessTokenProvider
    }

    func fetchTemplates() async throws -> [WorkflowTemplate] {
        // Fetch available workflow templates; assumptions: GET /v1/workflow-templates; side effect: network I/O.
        let url = baseUrl.appendingPathComponent("v1/workflow-templates")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        
        if let token = accessTokenProvider(), !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let (data, response) = try await urlSession.data(for: request)
        let http = try requireHttpResponse(response: response, data: data)
        if http.statusCode != 200 {
            throw ApiClientError.httpError(http.statusCode, stringBody(data))
        }

        let decoded = try JSONDecoder().decode(WorkflowTemplatesResponse.self, from: data)
        return decoded.templates
    }

    func loadTemplate(templateId: String, principalSub: String, startDate: String, persona: String?) async throws -> String {
        // Create a workflow instance from a template; assumptions: POST /v1/workflows; side effect: network I/O + server-side state creation.
        let url = baseUrl.appendingPathComponent("v1/workflows")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        if let token = accessTokenProvider(), !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let payload = LoadTemplateRequest(template_id: templateId, principal_sub: principalSub, start_date: startDate, persona: persona)
        request.httpBody = try JSONEncoder().encode(payload)

        let (data, response) = try await urlSession.data(for: request)
        let http = try requireHttpResponse(response: response, data: data)

        if http.statusCode != 200 && http.statusCode != 201 {
            throw ApiClientError.httpError(http.statusCode, stringBody(data))
        }

        return try extractTripId(from: data)
    }

    // Preferred naming (non-breaking): clearer method names that wrap the legacy ones.

    func createWorkflowFromTemplate(templateId: String, principalSub: String, startDate: String, persona: String?) async throws -> String {
        return try await loadTemplate(templateId: templateId, principalSub: principalSub, startDate: startDate, persona: persona)
    }
    
    func fetchWorkflowItems(workflowId: String, persona: String?) async throws -> [WorkflowItem] {
        // Fetch workflow items for a workflow; assumptions: GET /v1/workflows/{workflow_id}/items; side effect: network I/O.
        var urlComponents = URLComponents(url: baseUrl.appendingPathComponent("v1/workflows/\(workflowId)/items"), resolvingAgainstBaseURL: false)!
        
        // Add persona query parameter if provided
        if let persona = persona {
            urlComponents.queryItems = [URLQueryItem(name: "persona", value: persona)]
        }
        
        guard let url = urlComponents.url else {
            throw ApiClientError.invalidResponse("Failed to construct URL with query parameters")
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        
        if let token = accessTokenProvider(), !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        
        let (data, response) = try await urlSession.data(for: request)
        let http = try requireHttpResponse(response: response, data: data)
        if http.statusCode != 200 {
            throw ApiClientError.httpError(http.statusCode, stringBody(data))
        }
        
        let decoded = try JSONDecoder().decode(WorkflowItemsResponse.self, from: data)
        return decoded.items
    }
    
    func fetchWorkflows() async throws -> [Workflow] {
        // Fetch all workflows; assumptions: GET /v1/workflows; side effect: network I/O.
        let url = baseUrl.appendingPathComponent("v1/workflows")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        
        if let token = accessTokenProvider(), !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        
        let (data, response) = try await urlSession.data(for: request)
        let http = try requireHttpResponse(response: response, data: data)
        if http.statusCode != 200 {
            throw ApiClientError.httpError(http.statusCode, stringBody(data))
        }
        
        let decoded = try JSONDecoder().decode(WorkflowsResponse.self, from: data)
        return decoded.workflows
    }

    // MARK: - Internals

    private func extractTripId(from data: Data) throws -> String {
        // Extract workflow_id from a flexible JSON response; why: allow evolution (top-level or nested under trip); assumptions: response is JSON; side effect: none.
        let jsonObject = try JSONSerialization.jsonObject(with: data, options: [])
        guard let root = jsonObject as? [String: Any] else {
            throw ApiClientError.invalidResponse("Expected JSON object, got: \(stringBody(data))")
        }

        if let workflowId = root["workflow_id"] as? String, !workflowId.isEmpty {
            return workflowId
        }

        if let trip = root["trip"] as? [String: Any],
           let workflowId = trip["workflow_id"] as? String,
           !workflowId.isEmpty {
            return workflowId
        }

        throw ApiClientError.invalidResponse("Expected workflow_id in response, got: \(stringBody(data))")
    }

    private func requireHttpResponse(response: URLResponse, data: Data) throws -> HTTPURLResponse {
        // Ensure the response is HTTP; why: protect against unexpected URLSession responses; assumptions: none; side effect: none.
        guard let http = response as? HTTPURLResponse else {
            throw ApiClientError.invalidResponse("Non-HTTP response: \(data.count) bytes")
        }
        return http
    }

    private func stringBody(_ data: Data) -> String {
        // Convert response data to a readable string; why: improve error diagnostics; assumptions: UTF-8 preferred; side effect: none.
        return String(data: data, encoding: .utf8) ?? "<non-utf8 body>"
    }
}

// Backward compatibility with legacy naming.
typealias CumbayaApiClient = FlowPilotApiClient
typealias FlowPilotServicesApiClient = FlowPilotApiClient
