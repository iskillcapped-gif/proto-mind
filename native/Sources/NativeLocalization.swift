import CryptoKit
import Observation
import SwiftUI

enum InterfaceLanguage: String, CaseIterable, Identifiable {
    case russian = "ru", english = "en"
    var id: String { rawValue }
    var title: String { self == .russian ? "Русский" : "English" }
    static func key(_ configuration: LaunchConfiguration) -> String {
        "interfaceLanguage.v1." + SHA256.hash(data: Data(configuration.stateDirectory.standardizedFileURL.path.utf8))
            .map { String(format: "%02x", $0) }.joined()
    }
    static func saved(_ configuration: LaunchConfiguration, defaults: UserDefaults = .standard) -> InterfaceLanguage {
        if let override = ProcessInfo.processInfo.environment["PROTO_MIND_LANGUAGE"], let value = Self(rawValue: override) { return value }
        if let value = defaults.string(forKey: key(configuration)).flatMap(Self.init(rawValue:)) { return value }
        return ["ru", "uk"].contains(String((Locale.preferredLanguages.first ?? "en").prefix(2))) ? .russian : .english
    }
}

@Observable
final class InterfaceLocalization {
    static let shared = InterfaceLocalization()
    var language: InterfaceLanguage = .russian
}

extension Notification.Name {
    static let interfaceLanguageChanged = Notification.Name("ProtoMind.interfaceLanguageChanged")
}

enum L10n {
    // Views observe the shared language through these getters. Changing it updates
    // labels in place; it never replaces a workspace or its task/tab ownership.
    static var language: InterfaceLanguage {
        get { InterfaceLocalization.shared.language }
        set {
            guard newValue != language else { return }
            InterfaceLocalization.shared.language = newValue
            NotificationCenter.default.post(name: .interfaceLanguageChanged, object: nil)
        }
    }
    static var locale: Locale { Locale(identifier: language.rawValue) }
    static func select(_ next: InterfaceLanguage, configuration: LaunchConfiguration, defaults: UserDefaults = .standard) {
        defaults.set(next.rawValue, forKey: InterfaceLanguage.key(configuration))
        language = next
    }
    static func pick(_ russian: String, _ english: String) -> String { language == .english ? english : russian }
    static func text(_ source: String) -> String {
        guard language == .english else { return source }
        return english[source] ?? additionalEnglish[source] ?? source
    }
    static func format(_ message: InterfaceMessage) -> String {
        message.render(template: text(message.key))
    }
}

/// Only the literal template is translated. User text, filenames and provider
/// identifiers inserted into it are kept verbatim, including braces and percent signs.
struct InterfaceMessage: ExpressibleByStringLiteral, ExpressibleByStringInterpolation {
    private static let slotPattern = try! NSRegularExpression(pattern: #"\{([0-9]+)\}"#)
    var key: String
    var values: [String]
    init(stringLiteral value: String) { key = value; values = [] }
    init(stringInterpolation: StringInterpolation) { key = stringInterpolation.key; values = stringInterpolation.values }
    struct StringInterpolation: StringInterpolationProtocol {
        var key = ""
        var values: [String] = []
        init(literalCapacity: Int, interpolationCount: Int) { values.reserveCapacity(interpolationCount) }
        mutating func appendLiteral(_ literal: String) { key += literal }
        mutating func appendInterpolation<T>(_ value: T) {
            key += "{\(values.count)}"; values.append(String(describing: value))
        }
    }
    func render(template: String) -> String {
        // Substitute in one pass, so inserted text cannot introduce another slot.
        let original = template as NSString
        var result = "", cursor = 0
        for match in Self.slotPattern.matches(in: template, range: NSRange(location: 0, length: original.length)) {
            result += original.substring(with: NSRange(location: cursor, length: match.range.location - cursor))
            if let index = Int(original.substring(with: match.range(at: 1))), values.indices.contains(index) {
                result += values[index]
            } else { result += original.substring(with: match.range) }
            cursor = NSMaxRange(match.range)
        }
        return result + original.substring(from: cursor)
    }
}

struct InterfaceLanguagePicker: View {
    let configuration: LaunchConfiguration
    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Picker(L10n.text("Язык"), selection: Binding(get: { L10n.language }, set: { L10n.select($0, configuration: configuration) })) {
                ForEach(InterfaceLanguage.allCases) { Text($0.title).tag($0) }
            }
            Text(L10n.pick("Язык меняется сразу во всех окнах. Ваши сообщения и файлы остаются как есть.", "The language changes immediately in every window. Your messages and files stay as they are."))
                .font(.caption).foregroundStyle(.secondary)
        }
    }
}
