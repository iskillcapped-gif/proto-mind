import CryptoKit
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

enum L10n {
    // One language for the lifetime of the process, including all companion windows.
    // Tests default to Russian; application startup resolves the profile preference.
    static var language: InterfaceLanguage = .russian
    static func pick(_ russian: String, _ english: String) -> String { language == .english ? english : russian }
    static func text(_ source: String) -> String {
        guard language == .english else { return source }
        return english[source] ?? source
    }
}

struct InterfaceLanguagePicker: View {
    let configuration: LaunchConfiguration
    @State private var language: InterfaceLanguage = L10n.language
    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Picker("Language / Язык", selection: $language) {
                ForEach(InterfaceLanguage.allCases) { Text($0.title).tag($0) }
            }
            if language != L10n.language {
                Text(language == .english ? "Restart Proto-Mind to apply English. Active tasks keep running until you quit." : "Перезапустите Proto-Mind, чтобы включить русский язык. До выхода задачи продолжат работу.")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }.onAppear { language = InterfaceLanguage.saved(configuration) }
            .onChange(of: language) { _, next in UserDefaults.standard.set(next.rawValue, forKey: InterfaceLanguage.key(configuration)) }
    }
}
