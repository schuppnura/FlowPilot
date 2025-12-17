//
//  AdviceUtils.swift
//  FlowPilot-demo
//
//  Created by Carlo on 15/12/2025.
//

import Foundation

struct AdviceUtils {
    static func extractMissingProfileFields(from run: AgentRunResponse) -> [String] {
        var fields: Set<String> = []
        for result in run.results {
            guard let adviceArray = result.advice else { continue }
            for advice in adviceArray {
                if advice.type == "profile_requirements" {
                    // Assumption: advice.message contains the missing field name or a comma-separated list
                    let splitFields = advice.message.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }
                    for field in splitFields where !field.isEmpty { fields.insert(field) }
                }
            }
        }
        return Array(fields).sorted()
    }
}
