import Foundation

final class FlowPilotAIAgentApiClient {
    private let baseUrl: URL
    private let urlSession: URLSession
    private let accessTokenProvider: () -> String?

    init(baseUrl: URL = AppConfig.agentRunnerBaseUrl, urlSession: URLSession = .shared, accessTokenProvider: @escaping () -> String? = { nil }) {
        // Initialize client with a base URL; why: keep endpoint routing explicit and testable; side effect: none.
        self.baseUrl = baseUrl
        self.urlSession = urlSession
        self.accessTokenProvider = accessTokenProvider
    }

    func runAgent(workflowId: String, principalSub: String, dryRun: Bool) async throws -> AgentRunResponse {
        // Run the agent for a workflow; why: execute items item-by-item under policy control; assumptions: POST /v1/agent-runs; side effect: network I/O.
        let url = baseUrl.appendingPathComponent("/v1/agent-runs")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        if let token = accessTokenProvider(), !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let payload = AgentRunRequest(workflow_id: workflowId, principal_sub: principalSub, dry_run: dryRun)
        request.httpBody = try JSONEncoder().encode(payload)

        let (data, response) = try await urlSession.data(for: request)
        let http = try requireHttpResponse(response: response, data: data)

        if http.statusCode != 200 && http.statusCode != 201 {
            throw ApiClientError.httpError(http.statusCode, stringBody(data))
        }

        return try JSONDecoder().decode(AgentRunResponse.self, from: data)
    }

    private func requireHttpResponse(response: URLResponse, data: Data) throws -> HTTPURLResponse {
        // Ensure the response is HTTP; why: protect against unexpected URLSession responses; assumptions: none; side effect: none.
        guard let http = response as? HTTPURLResponse else {
            throw ApiClientError.invalidResponse("Non-HTTP response: \(data.count) bytes")
        }
        return http
    }

    private func stringBody(_ data: Data) -> String {
        // Convert response data to a readable string; why: improve diagnostics on non-2xx; assumptions: UTF-8 preferred; side effect: none.
        return String(data: data, encoding: .utf8) ?? "<non-utf8 body>"
    }
}
