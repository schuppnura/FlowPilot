//
//  JwtError.swift
//  FlowPilot-demo
//
//  Created by Carlo on 15/12/2025.
//


import Foundation

enum JwtError: Error {
    case invalidFormat
    case invalidBase64
    case invalidJson
    case missingClaim(String)
}

struct JwtUtils {
    static func decodeClaims(idToken: String) throws -> [String: Any] {
        let parts = idToken.split(separator: ".")
        if parts.count < 2 { throw JwtError.invalidFormat }
        let payload = String(parts[1])
        let data = try decodeBase64Url(payload)
        let json = try JSONSerialization.jsonObject(with: data, options: [])
        guard let dict = json as? [String: Any] else { throw JwtError.invalidJson }
        return dict
    }

    static func decodeBase64Url(_ input: String) throws -> Data {
        var base64 = input.replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
        let padding = 4 - (base64.count % 4)
        if padding < 4 { base64 += String(repeating: "=", count: padding) }
        guard let data = Data(base64Encoded: base64) else { throw JwtError.invalidBase64 }
        return data
    }

    static func requireStringClaim(_ claims: [String: Any], key: String) throws -> String {
        guard let value = claims[key] as? String, !value.isEmpty else { throw JwtError.missingClaim(key) }
        return value
    }
}