//
//  FirebaseAuthClient.swift
//  FlowPilot-demo
//
//  Firebase Authentication client for email/password authentication.
//  Uses Firebase Authentication REST API to sign in and get ID tokens.
//

import Foundation

enum FirebaseAuthError: Error {
    case signInFailed(String)
    case refreshFailed(String)
    case invalidResponse(String)
    case missingIdToken
    case missingUid
}

struct FirebaseAuthTokenResponse: Codable {
    let idToken: String
    let refreshToken: String
    let expiresIn: String
    let localId: String  // Firebase UID
    let email: String?
    let displayName: String?
}

final class FirebaseAuthClient {
    private let apiKey: String
    private let projectId: String
    
    init(apiKey: String = AppConfig.firebaseWebApiKey, projectId: String = AppConfig.firebaseProjectId) {
        self.apiKey = apiKey
        self.projectId = projectId
    }
    
    func signIn(email: String, password: String) async throws -> (FirebaseAuthTokenResponse, String) {
        let url = URL(string: "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=\(apiKey)")!
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let payload = [
            "email": email,
            "password": password,
            "returnSecureToken": true
        ] as [String : Any]
        
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let http = response as? HTTPURLResponse else {
            throw FirebaseAuthError.invalidResponse("Non-HTTP response")
        }
        
        if http.statusCode != 200 {
            let bodyText = String(data: data, encoding: .utf8) ?? "<no body>"
            throw FirebaseAuthError.signInFailed("HTTP \(http.statusCode): \(bodyText)")
        }
        
        let tokenResponse = try JSONDecoder().decode(FirebaseAuthTokenResponse.self, from: data)
        let uid = tokenResponse.localId
        
        return (tokenResponse, uid)
    }
    
    func refreshAccessToken(refreshToken: String) async throws -> FirebaseAuthTokenResponse {
        let url = URL(string: "https://securetoken.googleapis.com/v1/token?key=\(apiKey)")!
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let payload = [
            "grant_type": "refresh_token",
            "refresh_token": refreshToken
        ] as [String : Any]
        
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let http = response as? HTTPURLResponse else {
            throw FirebaseAuthError.invalidResponse("Non-HTTP response")
        }
        
        if http.statusCode != 200 {
            let bodyText = String(data: data, encoding: .utf8) ?? "<no body>"
            throw FirebaseAuthError.refreshFailed("HTTP \(http.statusCode): \(bodyText)")
        }
        
        // The refresh endpoint returns a slightly different structure
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        guard let idToken = json?["id_token"] as? String,
              let refreshTokenNew = json?["refresh_token"] as? String,
              let expiresIn = json?["expires_in"] as? String,
              let userId = json?["user_id"] as? String else {
            throw FirebaseAuthError.invalidResponse("Missing required fields in refresh response")
        }
        
        return FirebaseAuthTokenResponse(
            idToken: idToken,
            refreshToken: refreshTokenNew,
            expiresIn: expiresIn,
            localId: userId,
            email: nil,
            displayName: nil
        )
    }
    
    func signOut() async throws {
        // Firebase doesn't require server-side sign out for email/password
        // The client just discards the tokens
        // This method is kept for API compatibility
    }
}
