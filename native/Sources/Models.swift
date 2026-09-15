import CryptoKit
import Foundation

indirect enum JSONValue: Codable, Equatable, Sendable {
    case object([String: JSONValue]), array([JSONValue]), string(String), number(Double), bool(Bool), null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() { self = .null }
        else if let value = try? container.decode(Bool.self) { self = .bool(value) }
        else if let value = try? container.decode(String.self) { self = .string(value) }
        else if let value = try? container.decode(Double.self) { self = .number(value) }
        else if let value = try? container.decode([String: JSONValue].self) { self = .object(value) }
        else { self = .array(try container.decode([JSONValue].self)) }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .object(let value): try container.encode(value)
        case .array(let value): try container.encode(value)
        case .string(let value): try container.encode(value)
        case .number(let value): try container.encode(value)
        case .bool(let value): try container.encode(value)
        case .null: try container.encodeNil()
        }
    }

    subscript(_ key: String) -> JSONValue {
        if case .object(let values) = self { return values[key] ?? .null }
        return .null
    }
    var text: String { if case .string(let value) = self { return value }; return "" }
    var items: [JSONValue] { if case .array(let value) = self { return value }; return [] }
    var flag: Bool { if case .bool(let value) = self { return value }; return false }
    var integer: Int {
        if case .number(let value) = self, value.isFinite, value >= Double(Int.min), value < Double(Int.max) { return Int(value) }
        return 0
    }
    var isNull: Bool { self == .null }
    var pretty: String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        return (try? String(data: encoder.encode(self), encoding: .utf8)) ?? ""
    }
}

struct ChatMessage: Codable, Identifiable, Equatable {
    var id = UUID()
    var role: String
    var text: String
    var raw: String = ""
    var evidence: JSONValue = .null
    var notices: [String] = []
    var createdAt = Date()
    var isError = false
    var operatorInput: Bool? = nil
    var fileContext: [JSONValue]? = nil
    var imageContext: [JSONValue]? = nil
    var pdfContext: [JSONValue]? = nil
    var agentRun: JSONValue? = nil
    var workLog: JSONValue? = nil
    var autoSkills: JSONValue? = nil
    var knowledgeContext: JSONValue? = nil
    var memorySuggestions: JSONValue? = nil
    var memorySuggestionSourceID: UUID? = nil
    var turnReference: JSONValue? = nil
    var taskUpdates: [TaskUpdate]? = nil

    var searchableText: String { ([text] + (taskUpdates ?? []).map(\.text)).joined(separator: "\n\n") }
}

struct Conversation: Codable, Identifiable, Equatable {
    var id = UUID()
    var title = "Новый диалог"
    var createdAt = Date()
    var updatedAt = Date()
    var messages: [ChatMessage] = []
    var provider = "ollama"
    var model = ""
    var reasoningEffort = ""
    var autoSkillsEnabled = true
    var autoProjectRecallEnabled = true
    var memorySuggestionsEnabled = true
    var archived = false
    var draft = ""
    var workspacePath: String?
    var pendingFiles: [JSONValue] = []
    var pendingImages: [JSONValue] = []
    var pendingPDFs: [JSONValue] = []
    var pendingCriteria: [String] = []
    var draftContinuation: JSONValue? = nil
    var dismissedWorkSessionWarnings: [NativeWorkSessionNotice] = []

    init() {}

    enum CodingKeys: String, CodingKey {
        case id, title, createdAt, updatedAt, messages, provider, model, reasoningEffort, autoSkillsEnabled, autoProjectRecallEnabled, memorySuggestionsEnabled, archived, draft, workspacePath, pendingFiles, pendingImages, pendingPDFs, pendingCriteria, draftContinuation, dismissedWorkSessionWarnings
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decode(UUID.self, forKey: .id)
        title = try values.decode(String.self, forKey: .title)
        createdAt = try values.decode(Date.self, forKey: .createdAt)
        updatedAt = try values.decode(Date.self, forKey: .updatedAt)
        messages = try values.decode([ChatMessage].self, forKey: .messages)
        provider = try values.decode(String.self, forKey: .provider)
        model = try values.decode(String.self, forKey: .model)
        reasoningEffort = try values.decodeIfPresent(String.self, forKey: .reasoningEffort) ?? ""
        autoSkillsEnabled = try values.decodeIfPresent(Bool.self, forKey: .autoSkillsEnabled) ?? true
        autoProjectRecallEnabled = try values.decodeIfPresent(Bool.self, forKey: .autoProjectRecallEnabled) ?? true
        memorySuggestionsEnabled = try values.decodeIfPresent(Bool.self, forKey: .memorySuggestionsEnabled) ?? true
        archived = try values.decodeIfPresent(Bool.self, forKey: .archived) ?? false
        draft = try values.decodeIfPresent(String.self, forKey: .draft) ?? ""
        workspacePath = try values.decodeIfPresent(String.self, forKey: .workspacePath)
        pendingFiles = try values.decodeIfPresent([JSONValue].self, forKey: .pendingFiles) ?? []
        pendingImages = try values.decodeIfPresent([JSONValue].self, forKey: .pendingImages) ?? []
        pendingPDFs = try values.decodeIfPresent([JSONValue].self, forKey: .pendingPDFs) ?? []
        try NativePDFAttachment.validate(pendingPDFs)
        for message in messages { try NativePDFAttachment.validate(message.pdfContext ?? []) }
        try NativeImageAttachment.validate(pendingImages)
        for message in messages { try NativeImageAttachment.validate(message.imageContext ?? []) }
        for message in messages { if let report = message.autoSkills { _ = try NativeAutoSkillsReport(report) } }
        for message in messages { try checkKnowledgeMetadata(message.knowledgeContext ?? .null) }
        try validateMemorySuggestionHistory(messages, conversation: id)
        try validateTurnLineageHistory(messages, conversation: id)
        try TaskUpdate.validate(messages)
        pendingCriteria = try NativeTaskCriteria.validate(values.decodeIfPresent([String].self, forKey: .pendingCriteria) ?? [])
        draftContinuation = try values.decodeIfPresent(JSONValue.self, forKey: .draftContinuation)
        dismissedWorkSessionWarnings = try values.decodeIfPresent([NativeWorkSessionNotice].self, forKey: .dismissedWorkSessionWarnings) ?? []
        try NativeWorkSessionNotice.validate(dismissedWorkSessionWarnings)
    }

    var history: [JSONValue] {
        messages.filter { ["user", "assistant"].contains($0.role) && !$0.isError && $0.operatorInput != true && !($0.role == "user" && $0.text.hasPrefix("/")) }
            .flatMap { message -> [JSONValue] in
                var note = message.role == "user" && message.imageContext?.isEmpty == false
                    ? "[Earlier image bytes are NOT included in this turn. Reattach the image to inspect it again.]\n" : ""
                if message.role == "user" && message.pdfContext?.isEmpty == false {
                    note += "[Earlier PDF page text is NOT included in this turn. Reattach selected pages to inspect them again.]\n"
                }
                let primary = JSONValue.object(["role": .string(message.role), "content": .string(String((note + message.text).prefix(2000)))])
                return [primary] + (message.taskUpdates ?? []).filter { $0.state == .accepted }.map {
                    .object(["role": .string("user"), "content": .string(String($0.historyText.prefix(2000)))])
                }
            }.suffix(12).map { $0 }
    }
}

struct ChatArchive: Codable {
    var version = 5
    var conversations: [Conversation]
    var selectedID: UUID?
}

struct ConversationGroup: Identifiable {
    let id: String
    let title: String
    let workspace: String?
    var conversations: [Conversation]

    static func make(_ conversations: [Conversation]) -> [ConversationGroup] {
        var result: [ConversationGroup] = []
        for chat in conversations {
            let key = chat.workspacePath.map { "workspace:" + $0 } ?? "unbound"
            if let index = result.firstIndex(where: { $0.id == key }) {
                result[index].conversations.append(chat)
            } else {
                result.append(ConversationGroup(id: key, title: chat.workspacePath.map { URL(fileURLWithPath: $0).lastPathComponent } ?? "Без рабочей папки",
                                                workspace: chat.workspacePath, conversations: [chat]))
            }
        }
        return result
    }
}

enum NativeError: LocalizedError {
    case message(String)
    var errorDescription: String? { if case .message(let message) = self { return message }; return nil }
}

struct RememberedAgentAccess: Codable, Equatable {
    let conversationID: UUID
    let workspace: String?
}

struct NativePreferences: Codable, Equatable {
    var version: Int
    var cloudProcessingAllowed: Bool
    var personaEnabled: Bool
    var rememberedAgentAccess: [RememberedAgentAccess]

    init(version: Int = 3, cloudProcessingAllowed: Bool = false, personaEnabled: Bool = false,
         rememberedAgentAccess: [RememberedAgentAccess] = []) {
        self.version = version
        self.cloudProcessingAllowed = cloudProcessingAllowed
        self.personaEnabled = personaEnabled
        self.rememberedAgentAccess = rememberedAgentAccess
    }

    enum CodingKeys: String, CodingKey { case version, cloudProcessingAllowed, personaEnabled, rememberedAgentAccess }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        version = try values.decode(Int.self, forKey: .version)
        cloudProcessingAllowed = try values.decode(Bool.self, forKey: .cloudProcessingAllowed)
        if version >= 2 {
            personaEnabled = try values.decodeIfPresent(Bool.self, forKey: .personaEnabled) ?? false
        } else {
            personaEnabled = false
        }
        rememberedAgentAccess = version >= 3
            ? try values.decodeIfPresent([RememberedAgentAccess].self, forKey: .rememberedAgentAccess) ?? [] : []
    }
}

final class PreferenceStore {
    let url: URL
    private(set) var writeBlocked = false
    private var loaded = false
    private var generationBaseline: Data?
    init(directory: URL) { url = directory.appendingPathComponent("preferences.json") }

    func load() throws -> NativePreferences {
        try PrivateStateAccess.requireAvailable(url.deletingLastPathComponent())
        generationBaseline = try PrivateStateAccess.generation(url.deletingLastPathComponent())
        loaded = true
        guard FileManager.default.fileExists(atPath: url.path) else { return NativePreferences() }
        do {
            let size = try FileManager.default.attributesOfItem(atPath: url.path)[.size] as? NSNumber
            guard let size, size.int64Value <= 65_536 else { throw NativeError.message("Настройки слишком велики.") }
            let data = try Data(contentsOf: url)
            guard data.count <= 65_536 else { throw NativeError.message("Настройки слишком велики.") }
            let value = try JSONDecoder().decode(NativePreferences.self, from: data)
            guard [1, 2, 3].contains(value.version), value.version != 1 || !value.personaEnabled,
                  Set(value.rememberedAgentAccess.map(\.conversationID)).count == value.rememberedAgentAccess.count else {
                throw NativeError.message("Неизвестная версия настроек.")
            }
            return value
        } catch {
            writeBlocked = true
            throw NativeError.message("Настройки не прочитаны. Облачное разрешение и Brother Persona выключены; исходный файл не перезаписывается: \(url.path)")
        }
    }

    func save(_ preferences: NativePreferences) throws {
        try ChatHistoryFiles.withLock(in: url.deletingLastPathComponent(), write: true) {
            try saveLocked(preferences)
        }
    }

    private func saveLocked(_ preferences: NativePreferences) throws {
        try PrivateStateAccess.requireAvailable(url.deletingLastPathComponent())
        let currentGeneration = try PrivateStateAccess.generation(url.deletingLastPathComponent())
        guard !loaded || currentGeneration == generationBaseline else {
            throw NativeError.message("Данные восстановлены. Перезапустите Proto-Mind перед изменением настроек.")
        }
        guard !writeBlocked else { throw NativeError.message("Запись настроек заблокирована до ручной проверки файла.") }
        guard preferences.version == 3 else { throw NativeError.message("Записывать можно только текущую версию настроек.") }
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let data = try JSONEncoder().encode(preferences)
        guard data.count <= 65_536 else { throw NativeError.message("Настройки слишком велики. Изменение не сохранено; прежние настройки доступны.") }
        try data.write(to: url, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
    }
}

struct LaunchConfiguration {
    let projectRoot: URL
    let python: URL
    let stateDirectory: URL
    var pdfHelper: URL? = nil
    var sourceRoot: URL? = nil
    var codexExecutable: URL? = nil
    var isPortable = false

    var codeRoot: URL { sourceRoot ?? projectRoot }

    static func argument(_ name: String) -> String? {
        guard let index = CommandLine.arguments.firstIndex(of: name), index + 1 < CommandLine.arguments.count else { return nil }
        return CommandLine.arguments[index + 1]
    }

    static func load() -> LaunchConfiguration {
        let bundled = Bundle.main.url(forResource: "native-config", withExtension: "json")
            .flatMap { try? Data(contentsOf: $0) }
            .flatMap { try? JSONDecoder().decode([String: String].self, from: $0) } ?? [:]
        return resolve(arguments: CommandLine.arguments, environment: ProcessInfo.processInfo.environment,
                       bundled: bundled, resources: Bundle.main.resourceURL,
                       home: FileManager.default.homeDirectoryForCurrentUser,
                       currentDirectory: FileManager.default.currentDirectoryPath,
                       pdfHelper: Bundle.main.url(forAuxiliaryExecutable: "ProtoMindPDF"))
    }

    static func resolve(arguments: [String], environment env: [String: String], bundled: [String: String],
                        resources: URL?, home: URL, currentDirectory: String, pdfHelper: URL?) -> LaunchConfiguration {
        func option(_ name: String) -> String? {
            guard let index = arguments.firstIndex(of: name), index + 1 < arguments.count else { return nil }
            return arguments[index + 1]
        }
        if bundled["distribution"] == "portable" {
            // The bundle is read-only code. Updates replace it without replacing the user's profile.
            // Explicit profile overrides are for isolated QA; inherited developer paths are ignored.
            let profile = option("--profile-root").map { URL(fileURLWithPath: $0, isDirectory: true) }
                ?? home.appendingPathComponent("Library/Application Support/ProtoMind", isDirectory: true)
            let runtime = (resources ?? URL(fileURLWithPath: "/missing-protomind-resources"))
            return LaunchConfiguration(projectRoot: profile.appendingPathComponent("core", isDirectory: true),
                python: runtime.appendingPathComponent("runtime/python/bin/python3"),
                stateDirectory: profile.appendingPathComponent("native", isDirectory: true), pdfHelper: pdfHelper,
                sourceRoot: runtime.appendingPathComponent("core", isDirectory: true),
                codexExecutable: runtime.appendingPathComponent("runtime/codex/bin/codex"), isPortable: true)
        }
        let root = option("--project-root") ?? env["PROTO_MIND_PROJECT_ROOT"] ?? bundled["project_root"] ?? currentDirectory
        let python = option("--python") ?? env["PROTO_MIND_PYTHON"] ?? bundled["python"] ?? "/opt/homebrew/opt/python@3.11/bin/python3.11"
        let state = (option("--state-dir") ?? bundled["state_directory"]).map { URL(fileURLWithPath: $0, isDirectory: true) }
            ?? home.appendingPathComponent("Library/Application Support/ProtoMindNative", isDirectory: true)
        return LaunchConfiguration(projectRoot: URL(fileURLWithPath: root, isDirectory: true),
                                   python: URL(fileURLWithPath: python), stateDirectory: state,
                                   pdfHelper: option("--pdf-helper").map { URL(fileURLWithPath: $0).resolvingSymlinksInPath() } ?? pdfHelper)
    }
}
