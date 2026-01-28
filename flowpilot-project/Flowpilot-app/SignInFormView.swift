//
//  SignInFormView.swift
//  FlowPilot-demo
//
//  Sign-in form for Firebase email/password authentication
//

import SwiftUI

struct SignInFormView: View {
    @EnvironmentObject var state: AppState
    @State private var usernameOrEmail: String = "carlo"  // Default test user
    @State private var password: String = ""
    @State private var isSigningIn: Bool = false
    
    // Username to email mapping for convenience
    private let usernameToEmail: [String: String] = [
        "carlo": "test1@example.com",
        "peter": "test2@example.com",
        "yannick": "test3@example.com",
        "isabel": "test4@examplee.com",
        "kathleen": "test5@example.com",
        "martine": "test6@example.com",
        "sarah": "test7@example.com"
    ]
    
    // Convert username to email if needed
    private func resolveEmail() -> String {
        let input = usernameOrEmail.lowercased().trimmingCharacters(in: .whitespaces)
        // If it's a username, map it to email
        if let email = usernameToEmail[input] {
            return email
        }
        // Otherwise, assume it's already an email
        return usernameOrEmail
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .center, spacing: 12) {
                Text("Username")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .frame(width: 80, alignment: .leading)
                TextField("Username", text: $usernameOrEmail)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 180)
                    .disabled(isSigningIn)
            }
            
            HStack(alignment: .center, spacing: 12) {
                Text("Password")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .frame(width: 80, alignment: .leading)
                SecureField("Password", text: $password)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 180)
                    .disabled(isSigningIn)
            }
            
            Button(action: {
                Task {
                    isSigningIn = true
                    let email = resolveEmail()
                    await state.signIn(email: email, password: password)
                    isSigningIn = false
                }
            }) {
                if isSigningIn {
                    ProgressView()
                        .controlSize(.small)
                        .frame(width: 100)
                } else {
                    Label("Sign In", systemImage: "person.badge.key.fill")
                        .frame(width: 100)
                }
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .tint(Color(red: 0.95, green: 0.55, blue: 0.25))
            .disabled(usernameOrEmail.isEmpty || password.isEmpty || isSigningIn)
            
            VStack(alignment: .leading, spacing: 4) {
                Text("Test users: carlo, peter, yannick, isabel, kathleen, martine, sarah")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text("Password: qkr9AXM3wum8fjt*xnc")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }
}
