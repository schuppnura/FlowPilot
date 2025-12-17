//
//  PkceError.swift
//  FlowPilot-demo
//
//  Created by Carlo on 15/12/2025.
//


import Foundation
import CryptoKit

enum PkceError: Error {
    case randomFailed
}

struct PkceUtils {
    static func generateCodeVerifier() throws -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        let status = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        if status != errSecSuccess { throw PkceError.randomFailed }
        return base64Url(Data(bytes))
    }

    static func generateCodeChallengeS256(verifier: String) -> String {
        let data = verifier.data(using: .utf8) ?? Data()
        let digest = SHA256.hash(data: data)
        return base64Url(Data(digest))
    }

    static func generateState() throws -> String {
        var bytes = [UInt8](repeating: 0, count: 16)
        let status = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        if status != errSecSuccess { throw PkceError.randomFailed }
        return base64Url(Data(bytes))
    }

    static func generateNonce() throws -> String {
        var bytes = [UInt8](repeating: 0, count: 16)
        let status = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        if status != errSecSuccess { throw PkceError.randomFailed }
        return base64Url(Data(bytes))
    }

    static func base64Url(_ data: Data) -> String {
        return data.base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }
}