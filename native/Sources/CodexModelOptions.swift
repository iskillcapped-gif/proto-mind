import Foundation

enum CodexReasoningEffort: String, CaseIterable, Identifiable {
    case none, minimal, low, medium, high, xhigh, max, ultra
    var id: String { rawValue }
    var title: String {
        switch self {
        case .none: return L10n.text("Без рассуждения")
        case .minimal: return L10n.text("Минимальное")
        case .low: return L10n.text("Лёгкое")
        case .medium: return L10n.text("Среднее")
        case .high: return L10n.text("Высокое")
        case .xhigh: return L10n.text("Очень высокое")
        case .max: return L10n.text("Макс.")
        case .ultra: return L10n.text("Ультра")
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
            ["astra", "sol", "terra", "luna", "mini", "codex", "spark"].contains(word.lowercased()) ? word.capitalized : String(word)
        }.joined(separator: " ")
    }
}
