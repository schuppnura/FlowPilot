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
    // MARK: - FlowPilot service endpoints (Cloud Run)

    /// AuthZ API base URL (string form preserved for backward compatibility).
    /// Default: Cloud Run deployment in us-central1.
    static let authzBaseUrl: String = stringValue(
        key: "FLOWPILOT_AUTHZ_BASE_URL",
        infoPlistKey: "FLOWPILOT_AUTHZ_BASE_URL",
        defaultValue: "https://flowpilot-authz-api-737191827545.us-central1.run.app"
    )

    /// URL form of `authzBaseUrl`.
    static let authzBaseUrlUrl: URL = URL(string: authzBaseUrl) ?? URL(string: "https://flowpilot-authz-api-737191827545.us-central1.run.app")!

    /// Domain/services API base URL.
    /// Default: Cloud Run deployment in us-central1.
    static let servicesBaseUrl: URL = urlValue(
        key: "FLOWPILOT_SERVICES_BASE_URL",
        infoPlistKey: "FLOWPILOT_SERVICES_BASE_URL",
        defaultValue: "https://flowpilot-domain-services-api-737191827545.us-central1.run.app"
    )

    /// Agent-runner API base URL.
    /// Default: Cloud Run deployment in us-central1.
    static let agentRunnerBaseUrl: URL = urlValue(
        key: "FLOWPILOT_AGENT_RUNNER_BASE_URL",
        infoPlistKey: "FLOWPILOT_AGENT_RUNNER_BASE_URL",
        defaultValue: "https://flowpilot-ai-agent-api-737191827545.us-central1.run.app"
    )
    
    /// Delegation API base URL.
    /// Default: Cloud Run deployment in us-central1.
    static let delegationBaseUrl: URL = urlValue(
        key: "FLOWPILOT_DELEGATION_BASE_URL",
        infoPlistKey: "FLOWPILOT_DELEGATION_BASE_URL",
        defaultValue: "https://flowpilot-delegation-api-737191827545.us-central1.run.app"
    )

    // MARK: - Firebase Authentication

    /// Firebase Web API Key for authentication.
    /// Used for email/password authentication via Firebase REST API.
    /// IMPORTANT: Set via environment variable or Info.plist - do not hardcode
    static let firebaseWebApiKey: String = stringValue(
        key: "FLOWPILOT_FIREBASE_API_KEY",
        infoPlistKey: "FLOWPILOT_FIREBASE_API_KEY",
        defaultValue: "your-firebase-api-key-here"
    )

    /// Firebase Project ID.
    static let firebaseProjectId: String = stringValue(
        key: "FLOWPILOT_FIREBASE_PROJECT_ID",
        infoPlistKey: "FLOWPILOT_FIREBASE_PROJECT_ID",
        defaultValue: "vision-course-476214"
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
