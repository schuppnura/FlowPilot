import Foundation

final class AuthzApiClient {
    private let baseUrl: URL
    private let urlSession: URLSession
    private let accessTokenProvider: () -> String?

    /// Backward compatible initializer (previously took a baseUrl string).
    init(baseUrl: String, urlSession: URLSession = .shared, accessTokenProvider: @escaping () -> String? = { nil }) {
        self.baseUrl = URL(string: baseUrl) ?? AppConfig.authzBaseUrlUrl
        self.urlSession = urlSession
        self.accessTokenProvider = accessTokenProvider
    }

    init(
        baseUrl: URL = AppConfig.authzBaseUrlUrl,
        urlSession: URLSession = .shared,
        accessTokenProvider: @escaping () -> String? = { nil }
    ) {
        // Initialize client with a base URL; why: keep endpoint routing explicit and testable; side effect: none.
        // Uses standard URLSession for Cloud Run services with proper TLS certificates.
        self.baseUrl = baseUrl
        self.urlSession = urlSession
        self.accessTokenProvider = accessTokenProvider
    }

    /// Sets "presence" flags for a principal profile without sending PII values.
    /// This enables progressive profiling checks on the server side.
    func setIdentityPresence(principalSub: String, fields: [String]) async throws {
        // Patch identity presence flags in authz-api; why: support progressive profiling without storing PII; side effect: network I/O.
        let normalizedSub = principalSub.trimmingCharacters(in: .whitespacesAndNewlines)
        if normalizedSub.isEmpty {
            throw ApiClientError.invalidResponse("principalSub must not be empty")
        }

        let presence: [String: Bool] = Dictionary(uniqueKeysWithValues: fields.map { ($0, true) })

        let path = "/v1/profiles/\(normalizedSub)/identity-presence"
        let url = baseUrl.appendingPathComponent(path)
        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        if let token = accessTokenProvider(), !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let body: [String: Any] = ["presence": presence]
        request.httpBody = try JSONSerialization.data(withJSONObject: body, options: [])

        let (data, response) = try await urlSession.data(for: request)
        let http = try requireHttpResponse(response: response, data: data)

        if http.statusCode < 200 || http.statusCode >= 300 {
            throw ApiClientError.httpError(http.statusCode, stringBody(data))
        }
    }

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
