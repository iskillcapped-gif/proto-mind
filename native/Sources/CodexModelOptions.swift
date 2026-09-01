import Foundation

enum CodexReasoningEffort: String, CaseIterable, Identifiable {
    case none, minimal, low, medium, high, xhigh, max, ultra
    var id: String { rawValue }
    var title: String {
        switch self {
        case .none: return "Без рассуждения"
        case .minimal: return "Минимальное"
        case .low: return "Лёгкое"
        case .medium: return "Среднее"
        case .high: return "Высокое"
        case .xhigh: return "Очень высокое"
        case .max: return "Макс."
        case .ultra: return "Ультра"
        }
    }
}

struct CodexModelOption: Identifiable, Equatable {
    let id: String
    let name: String
    let isDefault: Bool
    let efforts: [CodexReasoningEffort]
    let defaultEffort: CodexReasoningEffort?

    init?(_ value: JSONValue) {
        let identifier = value["id"].text
        guard !identifier.isEmpty, identifier.count <= 160 else { return nil }
        id = identifier
        name = value["name"].text.isEmpty ? identifier : value["name"].text
        isDefault = value["default"].flag
        let supported = Set(value["reasoning_efforts"].items.compactMap { CodexReasoningEffort(rawValue: $0["id"].text) })
        efforts = CodexReasoningEffort.allCases.filter { supported.contains($0) }
        let candidate = CodexReasoningEffort(rawValue: value["default_reasoning_effort"].text)
        defaultEffort = candidate.flatMap { supported.contains($0) ? $0 : nil }
    }

    var displayName: String {
        guard name.lowercased().hasPrefix("gpt-") else { return name }
        let words = name.dropFirst(4).split(separator: "-")
        return words.map { word in
            ["sol", "terra", "luna", "mini", "codex", "spark"].contains(word.lowercased()) ? word.capitalized : String(word)
        }.joined(separator: " ")
    }
}
