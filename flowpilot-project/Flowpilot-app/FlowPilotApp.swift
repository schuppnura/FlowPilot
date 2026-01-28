//
//  FlowPilotApp.swift
//  FlowPilot
//
//  FlowPilot - App to demonstrate policy-driven authorization for AI-powered workflows
//

import SwiftUI

@main
struct FlowPilotApp: App {
    @StateObject private var state = AppState()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(state)
                .frame(minWidth: 900, minHeight: 1100)
                .onAppear {
                    // Ensure users are logged out on startup
                    if state.principalSub != nil || state.idToken != nil {
                        state.signOut()
                    }
                }
        }
        .defaultSize(width: 1000, height: 1300)
        .windowStyle(.automatic)
    }
}
