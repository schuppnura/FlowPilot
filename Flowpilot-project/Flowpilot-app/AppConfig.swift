//
//  AppConfig.swift
//  FlowPilot-demo
//
//  Centralized configuration for endpoints and OIDC settings.
//  Design intent:
//  - Desktop app runs on the host.
//  - Docker publishes services on localhost ports.
//  - All values can be overridden via Info.plist or environment variables.
//

import Foundation

struct AppConfig {
    // MARK: - FlowPilot service endpoints

    /// AuthZ API base URL (string form preserved for backward compatibility).
    /// Default assumption: Docker publishes authz-api on localhost:8002.
    static let authzBaseUrl: String = stringValue(
        key: "FLOWPILOT_AUTHZ_BASE_URL",
        infoPlistKey: "FLOWPILOT_AUTHZ_BASE_URL",
        defaultValue: "http://localhost:8002"
    )

    /// URL form of `authzBaseUrl`.
    static let authzBaseUrlUrl: URL = URL(string: authzBaseUrl) ?? URL(string: "http://localhost:8002")!

    /// Domain/services API base URL.
    /// Default assumption: Docker publishes domain-services-api on localhost:8003.
    static let servicesBaseUrl: URL = urlValue(
        key: "FLOWPILOT_SERVICES_BASE_URL",
        infoPlistKey: "FLOWPILOT_SERVICES_BASE_URL",
        defaultValue: "http://127.0.0.1:8003"
    )

    /// Agent-runner API base URL.
    /// Default assumption: Docker publishes ai-agent-api on localhost:8004.
    static let agentRunnerBaseUrl: URL = urlValue(
        key: "FLOWPILOT_AGENT_RUNNER_BASE_URL",
        infoPlistKey: "FLOWPILOT_AGENT_RUNNER_BASE_URL",
        defaultValue: "http://127.0.0.1:8004"
    )
    
    /// Delegation API base URL.
    /// Default assumption: Docker publishes delegation-api on localhost:8005.
    static let delegationBaseUrl: URL = urlValue(
        key: "FLOWPILOT_DELEGATION_BASE_URL",
        infoPlistKey: "FLOWPILOT_DELEGATION_BASE_URL",
        defaultValue: "http://127.0.0.1:8005"
    )

    // MARK: - OIDC (Keycloak)

    /// Keycloak issuer (realm) URL.
    /// Default assumption: Docker publishes Keycloak on https://localhost:8443 and imports realm "flowpilot".
    static let keycloakIssuer: URL = urlValue(
        key: "FLOWPILOT_KEYCLOAK_ISSUER",
        infoPlistKey: "FLOWPILOT_KEYCLOAK_ISSUER",
        defaultValue: "https://localhost:8443/realms/flowpilot"
    )

    /// OIDC client id configured in Keycloak.
    static let oidcClientId: String = stringValue(
        key: "FLOWPILOT_OIDC_CLIENT_ID",
        infoPlistKey: "FLOWPILOT_OIDC_CLIENT_ID",
        defaultValue: "flowpilot-desktop"
    )

    /// Redirect URI registered in Keycloak for the desktop client.
    static let oidcRedirectUri: String = stringValue(
        key: "FLOWPILOT_OIDC_REDIRECT_URI",
        infoPlistKey: "FLOWPILOT_OIDC_REDIRECT_URI",
        defaultValue: "flowpilot-demo://oauth/callback"
    )

    /// Space-separated scopes.
    static let oidcScopes: String = stringValue(
        key: "FLOWPILOT_OIDC_SCOPES",
        infoPlistKey: "FLOWPILOT_OIDC_SCOPES",
        defaultValue: "openid profile autobook"
    )

    /// Custom scheme part of `oidcRedirectUri` used by ASWebAuthenticationSession.
    static let oidcCallbackScheme: String = stringValue(
        key: "FLOWPILOT_OIDC_CALLBACK_SCHEME",
        infoPlistKey: "FLOWPILOT_OIDC_CALLBACK_SCHEME",
        defaultValue: "flowpilot-demo"
    )

    // MARK: - Backward compatible aliases (legacy naming)

    /// Legacy alias maintained to avoid touching other files during the rename.
    static let cumbayaBaseUrl: URL = servicesBaseUrl

    // MARK: - Helpers

    private static func stringValue(key: String, infoPlistKey: String, defaultValue: String) -> String {
        // Resolve from environment, then Info.plist, then fallback.
        if let envValue = ProcessInfo.processInfo.environment[key], !envValue.isEmpty {
            return envValue
        }
        if let infoValue = Bundle.main.object(forInfoDictionaryKey: infoPlistKey) as? String, !infoValue.isEmpty {
            return infoValue
        }
        return defaultValue
    }

    private static func urlValue(key: String, infoPlistKey: String, defaultValue: String) -> URL {
        let value = stringValue(key: key, infoPlistKey: infoPlistKey, defaultValue: defaultValue)
        return URL(string: value) ?? URL(string: defaultValue)!
    }
}
