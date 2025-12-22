//
//  FlowPilotApp.swift
//  Policy-driven Authorization
//
//  Policy-driven Authorization - Policy-driven authorization with AI-powered workflows
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
        }
        .defaultSize(width: 1000, height: 1300)
        .windowStyle(.automatic)
    }
}
