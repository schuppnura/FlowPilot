import Foundation

final class DelegationApiClient {
    private let baseUrl: URL
    private let urlSession: URLSession
    private let accessTokenProvider: () -> String?
    
    init(baseUrl: URL = AppConfig.delegationBaseUrl, urlSession: URLSession = .shared, accessTokenProvider: @escaping () -> String? = { nil }) {
        self.baseUrl = baseUrl
        self.urlSession = urlSession
        self.accessTokenProvider = accessTokenProvider
    }
    
    func createDelegation(principalId: String, delegateId: String, workflowId: String?, scope: [String]?, expiresInDays: Int) async throws -> DelegationResponse {
        let url = baseUrl.appendingPathComponent("v1/delegations")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        if let token = accessTokenProvider(), !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        
        let payload = CreateDelegationRequest(
            principal_id: principalId,
            delegate_id: delegateId,
            workflow_id: workflowId,
            scope: scope,
            expires_in_days: expiresInDays
        )
        request.httpBody = try JSONEncoder().encode(payload)
        
        let (data, response) = try await urlSession.data(for: request)
        let http = try requireHttpResponse(response: response, data: data)
        if http.statusCode != 200 {
            throw ApiClientError.httpError(http.statusCode, stringBody(data))
        }
        
        return try JSONDecoder().decode(DelegationResponse.self, from: data)
    }
    
    func listUsersByPersona(persona: String) async throws -> [TravelAgentUser] {
        var urlComponents = URLComponents(url: baseUrl.appendingPathComponent("v1/users"), resolvingAgainstBaseURL: false)!
        urlComponents.queryItems = [URLQueryItem(name: "persona", value: persona)]
        
        var request = URLRequest(url: urlComponents.url!)
        request.httpMethod = "GET"
        
        if let token = accessTokenProvider(), !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        
        let (data, response) = try await urlSession.data(for: request)
        let http = try requireHttpResponse(response: response, data: data)
        if http.statusCode != 200 {
            throw ApiClientError.httpError(http.statusCode, stringBody(data))
        }
        
        let responseObj = try JSONDecoder().decode(UsersByPersonaResponse.self, from: data)
        return responseObj.users
    }
    
    // MARK: - Internals
    
    private func requireHttpResponse(response: URLResponse, data: Data) throws -> HTTPURLResponse {
        guard let http = response as? HTTPURLResponse else {
            throw ApiClientError.invalidResponse("Non-HTTP response: \(data.count) bytes")
        }
        return http
    }
    
    private func stringBody(_ data: Data) -> String {
        return String(data: data, encoding: .utf8) ?? "<non-utf8 body>"
    }
}

