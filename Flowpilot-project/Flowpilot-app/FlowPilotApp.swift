//
//  NuraApp.swift
//  Nura Travel
//
//  Nura Travel - Intelligent travel planning with AI-powered authorization
//

import SwiftUI

@main
struct NuraApp: App {
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
