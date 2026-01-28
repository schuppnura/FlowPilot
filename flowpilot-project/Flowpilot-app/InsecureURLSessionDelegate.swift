//
//  InsecureURLSessionDelegate.swift
//  FlowPilot-demo
//
//  Disables SSL certificate verification for local development with self-signed certificates.
//  WARNING: This should NEVER be used in production!
//

import Foundation

/// URLSessionDelegate that bypasses SSL certificate validation.
/// Use ONLY for local development with self-signed certificates.
final class InsecureURLSessionDelegate: NSObject, URLSessionDelegate {
    func urlSession(
        _ session: URLSession,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        // Accept all server trust challenges without verification
        if challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
           let serverTrust = challenge.protectionSpace.serverTrust {
            let credential = URLCredential(trust: serverTrust)
            completionHandler(.useCredential, credential)
        } else {
            completionHandler(.performDefaultHandling, nil)
        }
    }
}

extension URLSession {
    /// URLSession configured for local development (disables SSL verification).
    /// WARNING: Use ONLY for development with self-signed certificates.
    static let insecure: URLSession = {
        let configuration = URLSessionConfiguration.default
        return URLSession(
            configuration: configuration,
            delegate: InsecureURLSessionDelegate(),
            delegateQueue: nil
        )
    }()
}
