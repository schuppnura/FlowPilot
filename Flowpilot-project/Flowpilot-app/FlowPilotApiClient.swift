import Foundation

// Shared HTTP error type used across demo API clients.
enum ApiClientError: Error, LocalizedError {
    case httpError(Int, String)
    case invalidResponse(String)

    var errorDescription: String? {
        switch self {
        case .httpError(let status, let body):
            return "HTTP error \(status): \(body)"
        case .invalidResponse(let message):
            return "Invalid response: \(message)"
        }
    }
}

/// Primary client for the FlowPilot domain/services API (system-of-record).
/// Backward compatibility: the legacy names remain available via typealiases below.
final class FlowPilotApiClient {
    private let baseUrl: URL
    private let urlSession: URLSession

    init(baseUrl: URL = AppConfig.servicesBaseUrl, urlSession: URLSession = .shared) {
        // Initialize client with a base URL; why: keep endpoint routing explicit and testable; side effect: none.
        self.baseUrl = baseUrl
        self.urlSession = urlSession
    }

    func fetchTemplates() async throws -> [TripTemplate] {
        // Fetch available workflow templates; assumptions: GET /v1/trip-templates; side effect: network I/O.
        let url = baseUrl.appendingPathComponent("/v1/trip-templates")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"

        let (data, response) = try await urlSession.data(for: request)
        let http = try requireHttpResponse(response: response, data: data)
        if http.statusCode != 200 {
            throw ApiClientError.httpError(http.statusCode, stringBody(data))
        }

        let decoded = try JSONDecoder().decode(TripTemplatesResponse.self, from: data)
        return decoded.templates
    }

    func loadTemplate(templateId: String, principalSub: String) async throws -> String {
        // Create a workflow instance from a template; assumptions: POST /v1/trips; side effect: network I/O + server-side state creation.
        let url = baseUrl.appendingPathComponent("/v1/trips")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let payload = LoadTemplateRequest(template_id: templateId, principal_sub: principalSub)
        request.httpBody = try JSONEncoder().encode(payload)

        let (data, response) = try await urlSession.data(for: request)
        let http = try requireHttpResponse(response: response, data: data)

        if http.statusCode != 200 && http.statusCode != 201 {
            throw ApiClientError.httpError(http.statusCode, stringBody(data))
        }

        return try extractTripId(from: data)
    }

    // Preferred naming (non-breaking): clearer method names that wrap the legacy ones.

    func createWorkflowFromTemplate(templateId: String, principalSub: String) async throws -> String {
        return try await loadTemplate(templateId: templateId, principalSub: principalSub)
    }

    // MARK: - Internals

    private func extractTripId(from data: Data) throws -> String {
        // Extract trip_id from a flexible JSON response; why: allow evolution (top-level or nested under trip); assumptions: response is JSON; side effect: none.
        let jsonObject = try JSONSerialization.jsonObject(with: data, options: [])
        guard let root = jsonObject as? [String: Any] else {
            throw ApiClientError.invalidResponse("Expected JSON object, got: \(stringBody(data))")
        }

        if let tripId = root["trip_id"] as? String, !tripId.isEmpty {
            return tripId
        }

        if let trip = root["trip"] as? [String: Any],
           let tripId = trip["trip_id"] as? String,
           !tripId.isEmpty {
            return tripId
        }

        throw ApiClientError.invalidResponse("Expected trip_id in response, got: \(stringBody(data))")
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
