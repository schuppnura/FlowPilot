//
//  OidcDiscovery.swift
//  FlowPilot-demo
//
//  Created by Carlo on 15/12/2025.
//


import Foundation

struct OidcDiscovery: Codable {
    let authorization_endpoint: String
    let token_endpoint: String
    let end_session_endpoint: String?
    let token_endpoint_auth_methods_supported: [String]?
}

struct OidcTokenResponse: Codable {
    let access_token: String
    let id_token: String
    let expires_in: Int
    let token_type: String
    let refresh_token: String?
    let scope: String?
}