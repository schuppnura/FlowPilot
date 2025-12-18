//
//  FlowPilotDemoApp.swift
//  FlowPilot-demo
//
//  Created by Carlo on 15/12/2025.
//

import SwiftUI

@main
struct FlowPilotDemoApp: App {
    @StateObject private var state = AppState()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(state)
                .frame(minWidth: 800, minHeight: 1000)
        }
        .defaultSize(width: 900, height: 1200)
    }
}
