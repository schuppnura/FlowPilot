//
//  KeycloakOidcClient.swift
//  FlowPilot-demo
//
//  Created by Carlo on 15/12/2025.
//


import Foundation
import AuthenticationServices

enum OidcClientError: Error {
    case discoveryFailed(String)
    case sessionFailed(String)
    case callbackMissingCode
    case callbackStateMismatch
    case tokenExchangeFailed(String)
    case nonceMismatch
    case missingSub
}

final class KeycloakOidcClient: NSObject {
    private let issuer: URL
    private let clientId: String
    private let redirectUri: String
    private let scopes: String

    private var authSession: ASWebAuthenticationSession?
    private var cachedDiscovery: OidcDiscovery?

    init(issuer: URL, clientId: String, redirectUri: String, scopes: String) {
        self.issuer = issuer
        self.clientId = clientId
        self.redirectUri = redirectUri
        self.scopes = scopes
    }

    func signIn(isRegistrationPreferred: Bool) async throws -> (OidcTokenResponse, String) {
        let discovery = try await fetchDiscoveryIfNeeded()
        let codeVerifier = try PkceUtils.generateCodeVerifier()
        let codeChallenge = PkceUtils.generateCodeChallengeS256(verifier: codeVerifier)
        let state = try PkceUtils.generateState()
        let nonce = try PkceUtils.generateNonce()

        let authorizeUrl = try buildAuthorizeUrl(
            authorizationEndpoint: discovery.authorization_endpoint,
            codeChallenge: codeChallenge,
            state: state,
            nonce: nonce,
            isRegistrationPreferred: isRegistrationPreferred
        )

        let callbackUrl = try await startWebAuthenticationSession(authorizeUrl: authorizeUrl)
        let callbackParts = parseCallback(url: callbackUrl)

        guard let code = callbackParts.code, !code.isEmpty else { throw OidcClientError.callbackMissingCode }
        if callbackParts.state != state { throw OidcClientError.callbackStateMismatch }

        let tokenResponse = try await exchangeCodeForTokens(
            tokenEndpoint: discovery.token_endpoint,
            code: code,
            codeVerifier: codeVerifier
        )

        let claims = try JwtUtils.decodeClaims(idToken: tokenResponse.id_token)
        let returnedNonce = claims["nonce"] as? String
        if let returnedNonceValue = returnedNonce, returnedNonceValue != nonce {
            throw OidcClientError.nonceMismatch
        }

        let sub = try JwtUtils.requireStringClaim(claims, key: "sub")
        return (tokenResponse, sub)
    }
    
    func refreshAccessToken(refreshToken: String) async throws -> OidcTokenResponse {
        // Refresh the access token using the refresh token
        // This will get a new access token with updated claims (including persona)
        let discovery = try await fetchDiscoveryIfNeeded()
        
        guard let url = URL(string: discovery.token_endpoint) else {
            throw OidcClientError.discoveryFailed("Invalid token endpoint URL")
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        
        let form = [
            ("grant_type", "refresh_token"),
            ("client_id", clientId),
            ("refresh_token", refreshToken)
        ]
        request.httpBody = encodeForm(form)
        
        // Use .insecure for local development with self-signed certificates
        let (data, response) = try await URLSession.insecure.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw OidcClientError.tokenExchangeFailed("Non-HTTP response")
        }
        
        if http.statusCode != 200 {
            let bodyText = String(data: data, encoding: .utf8) ?? "<no body>"
            throw OidcClientError.tokenExchangeFailed("HTTP \(http.statusCode): \(bodyText)")
        }
        
        return try JSONDecoder().decode(OidcTokenResponse.self, from: data)
    }
    
    func signOut(idToken: String) async throws {
        // Perform OIDC logout by calling Keycloak's end_session_endpoint
        // This terminates the Keycloak session and clears SSO cookies
        let discovery = try await fetchDiscoveryIfNeeded()
        
        guard let endSessionEndpoint = discovery.end_session_endpoint,
              let endSessionUrl = URL(string: endSessionEndpoint) else {
            // If no end_session_endpoint, just return (some OIDC providers don't support it)
            return
        }
        
        // Build logout URL with id_token_hint and post_logout_redirect_uri
        guard var components = URLComponents(url: endSessionUrl, resolvingAgainstBaseURL: false) else {
            return
        }
        
        var queryItems: [URLQueryItem] = []
        queryItems.append(URLQueryItem(name: "id_token_hint", value: idToken))
        queryItems.append(URLQueryItem(name: "post_logout_redirect_uri", value: redirectUri))
        components.queryItems = queryItems
        
        guard let logoutUrl = components.url else {
            return
        }
        
        // Use ASWebAuthenticationSession to perform the logout in the system browser
        // This ensures Keycloak's SSO cookies are cleared
        _ = try? await startWebAuthenticationSession(authorizeUrl: logoutUrl)
    }

    private func fetchDiscoveryIfNeeded() async throws -> OidcDiscovery {
        if let cached = cachedDiscovery { return cached }
        let discoveryUrl = issuer.appendingPathComponent(".well-known/openid-configuration")
        var request = URLRequest(url: discoveryUrl)
        request.httpMethod = "GET"

        // Use .insecure for local development with self-signed certificates
        let (data, response) = try await URLSession.insecure.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw OidcClientError.discoveryFailed("HTTP error fetching discovery")
        }

        let decoded = try JSONDecoder().decode(OidcDiscovery.self, from: data)
        cachedDiscovery = decoded
        return decoded
    }

    private func buildAuthorizeUrl(
        authorizationEndpoint: String,
        codeChallenge: String,
        state: String,
        nonce: String,
        isRegistrationPreferred: Bool
    ) throws -> URL {
        guard var components = URLComponents(string: authorizationEndpoint) else {
            throw OidcClientError.discoveryFailed("Invalid authorization endpoint URL")
        }

        var items: [URLQueryItem] = []
        items.append(URLQueryItem(name: "client_id", value: clientId))
        items.append(URLQueryItem(name: "response_type", value: "code"))
        items.append(URLQueryItem(name: "scope", value: scopes))
        items.append(URLQueryItem(name: "redirect_uri", value: redirectUri))
        items.append(URLQueryItem(name: "code_challenge_method", value: "S256"))
        items.append(URLQueryItem(name: "code_challenge", value: codeChallenge))
        items.append(URLQueryItem(name: "state", value: state))
        items.append(URLQueryItem(name: "nonce", value: nonce))

        if isRegistrationPreferred {
            items.append(URLQueryItem(name: "kc_action", value: "register"))
        }

        components.queryItems = items
        guard let url = components.url else {
            throw OidcClientError.discoveryFailed("Failed to construct authorization URL")
        }
        return url
    }

    private func startWebAuthenticationSession(authorizeUrl: URL) async throws -> URL {
        try await withCheckedThrowingContinuation { continuation in
            let session = ASWebAuthenticationSession(
                url: authorizeUrl,
                callbackURLScheme: AppConfig.oidcCallbackScheme
            ) { callbackUrl, error in
                if let errorValue = error {
                    continuation.resume(throwing: OidcClientError.sessionFailed(errorValue.localizedDescription))
                    return
                }
                guard let callbackUrlValue = callbackUrl else {
                    continuation.resume(throwing: OidcClientError.sessionFailed("Missing callback URL"))
                    return
                }
                continuation.resume(returning: callbackUrlValue)
            }

            session.presentationContextProvider = self
            session.prefersEphemeralWebBrowserSession = false
            self.authSession = session

            if session.start() != true {
                continuation.resume(throwing: OidcClientError.sessionFailed("ASWebAuthenticationSession failed to start"))
                return
            }
        }
    }

    private func parseCallback(url: URL) -> (code: String?, state: String?) {
        var code: String?
        var state: String?

        guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            return (nil, nil)
        }

        let items = components.queryItems ?? []
        for item in items {
            if item.name == "code" { code = item.value }
            if item.name == "state" { state = item.value }
        }
        return (code, state)
    }

    private func exchangeCodeForTokens(tokenEndpoint: String, code: String, codeVerifier: String) async throws -> OidcTokenResponse {
        guard let url = URL(string: tokenEndpoint) else {
            throw OidcClientError.discoveryFailed("Invalid token endpoint URL")
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")

        let form = [
            ("grant_type", "authorization_code"),
            ("client_id", clientId),
            ("redirect_uri", redirectUri),
            ("code", code),
            ("code_verifier", codeVerifier)
        ]
        request.httpBody = encodeForm(form)

        // Use .insecure for local development with self-signed certificates
        let (data, response) = try await URLSession.insecure.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw OidcClientError.tokenExchangeFailed("Non-HTTP response")
        }

        if http.statusCode != 200 {
            let bodyText = String(data: data, encoding: .utf8) ?? "<no body>"
            throw OidcClientError.tokenExchangeFailed("HTTP \(http.statusCode): \(bodyText)")
        }

        return try JSONDecoder().decode(OidcTokenResponse.self, from: data)
    }

    private func encodeForm(_ items: [(String, String)]) -> Data {
        var parts: [String] = []
        for (key, value) in items {
            let encodedKey = key.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? key
            let encodedValue = value.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? value
            parts.append("\(encodedKey)=\(encodedValue)")
        }
        return parts.joined(separator: "&").data(using: .utf8) ?? Data()
    }
}

extension KeycloakOidcClient: ASWebAuthenticationPresentationContextProviding {
    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        return NSApplication.shared.windows.first ?? ASPresentationAnchor()
    }
}