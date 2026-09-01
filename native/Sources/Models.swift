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
        case id, title, createdAt, updatedAt, messages, provider, model, reasoningEffort, archived, draft, workspacePath, pendingFiles, pendingImages, pendingPDFs, pendingCriteria, draftContinuation, dismissedWorkSessionWarnings
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
        pendingCriteria = try NativeTaskCriteria.validate(values.decodeIfPresent([String].self, forKey: .pendingCriteria) ?? [])
        draftContinuation = try values.decodeIfPresent(JSONValue.self, forKey: .draftContinuation)
        dismissedWorkSessionWarnings = try values.decodeIfPresent([NativeWorkSessionNotice].self, forKey: .dismissedWorkSessionWarnings) ?? []
        try NativeWorkSessionNotice.validate(dismissedWorkSessionWarnings)
    }

    var history: [JSONValue] {
        messages.filter { ["user", "assistant"].contains($0.role) && !$0.isError && $0.operatorInput != true && !($0.role == "user" && $0.text.hasPrefix("/")) }
            .suffix(12).map { message in
                var note = message.role == "user" && message.imageContext?.isEmpty == false
                    ? "[Earlier image bytes are NOT included in this turn. Reattach the image to inspect it again.]\n" : ""
                if message.role == "user" && message.pdfContext?.isEmpty == false {
                    note += "[Earlier PDF page text is NOT included in this turn. Reattach selected pages to inspect them again.]\n"
                }
                return .object(["role": .string(message.role), "content": .string(String((note + message.text).prefix(2000)))])
            }
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

final class ChatStore {
    let url: URL
    private(set) var writeBlocked = false

    init(directory: URL) { url = directory.appendingPathComponent("conversations.json") }

    func load() throws -> ChatArchive {
        guard FileManager.default.fileExists(atPath: url.path) else {
            return ChatArchive(conversations: [], selectedID: nil)
        }
        do {
            let size = try FileManager.default.attributesOfItem(atPath: url.path)[.size] as? NSNumber
            guard let size, size.int64Value < 50 * 1024 * 1024 else { throw NativeError.message("История слишком велика для автоматической загрузки.") }
            let data = try Data(contentsOf: url)
            guard data.count < 50 * 1024 * 1024 else { throw NativeError.message("История слишком велика для автоматической загрузки.") }
            let archive = try JSONDecoder().decode(ChatArchive.self, from: data)
            guard [1, 2, 3, 4, 5].contains(archive.version), Set(archive.conversations.map(\.id)).count == archive.conversations.count else {
                throw NativeError.message("Неизвестная версия или повторяющиеся ID истории.")
            }
            return archive
        } catch {
            writeBlocked = true
            throw NativeError.message("Не удалось прочитать локальную историю. Файл сохранён без изменений: \(url.path)")
        }
    }

    func save(_ archive: ChatArchive) throws {
        guard !writeBlocked else { throw NativeError.message("Запись истории заблокирована, чтобы не перезаписать повреждённый файл.") }
        for conversation in archive.conversations {
            try NativeWorkSessionNotice.validate(conversation.dismissedWorkSessionWarnings)
            try NativeImageAttachment.validate(conversation.pendingImages)
            try NativePDFAttachment.validate(conversation.pendingPDFs)
            for message in conversation.messages { try NativePDFAttachment.validate(message.pdfContext ?? []) }
            for message in conversation.messages { try NativeImageAttachment.validate(message.imageContext ?? []) }
        }
        let directory = url.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(archive)
        guard data.count < 50 * 1024 * 1024 else { throw NativeError.message("История достигла локального лимита 50 MB; существующий файл не перезаписан.") }
        try data.write(to: url, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
    }
}

struct NativePreferences: Codable, Equatable {
    var version: Int
    var cloudProcessingAllowed: Bool
    var personaEnabled: Bool

    init(version: Int = 2, cloudProcessingAllowed: Bool = false, personaEnabled: Bool = false) {
        self.version = version
        self.cloudProcessingAllowed = cloudProcessingAllowed
        self.personaEnabled = personaEnabled
    }

    enum CodingKeys: String, CodingKey { case version, cloudProcessingAllowed, personaEnabled }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        version = try values.decode(Int.self, forKey: .version)
        cloudProcessingAllowed = try values.decode(Bool.self, forKey: .cloudProcessingAllowed)
        if version >= 2 {
            personaEnabled = try values.decodeIfPresent(Bool.self, forKey: .personaEnabled) ?? false
        } else {
            personaEnabled = false
        }
    }
}

final class PreferenceStore {
    let url: URL
    private(set) var writeBlocked = false
    init(directory: URL) { url = directory.appendingPathComponent("preferences.json") }

    func load() throws -> NativePreferences {
        guard FileManager.default.fileExists(atPath: url.path) else { return NativePreferences() }
        do {
            let size = try FileManager.default.attributesOfItem(atPath: url.path)[.size] as? NSNumber
            guard let size, size.int64Value <= 65_536 else { throw NativeError.message("Настройки слишком велики.") }
            let data = try Data(contentsOf: url)
            guard data.count <= 65_536 else { throw NativeError.message("Настройки слишком велики.") }
            let value = try JSONDecoder().decode(NativePreferences.self, from: data)
            guard [1, 2].contains(value.version), value.version != 1 || !value.personaEnabled else {
                throw NativeError.message("Неизвестная версия настроек.")
            }
            return value
        } catch {
            writeBlocked = true
            throw NativeError.message("Настройки не прочитаны. Облачное разрешение и Brother Persona выключены; исходный файл не перезаписывается: \(url.path)")
        }
    }

    func save(_ preferences: NativePreferences) throws {
        guard !writeBlocked else { throw NativeError.message("Запись настроек заблокирована до ручной проверки файла.") }
        guard preferences.version == 2 else { throw NativeError.message("Записывать можно только текущую версию настроек.") }
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        try JSONEncoder().encode(preferences).write(to: url, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
    }
}

struct LaunchConfiguration {
    let projectRoot: URL
    let python: URL
    let stateDirectory: URL
    var pdfHelper: URL? = nil

    static func argument(_ name: String) -> String? {
        guard let index = CommandLine.arguments.firstIndex(of: name), index + 1 < CommandLine.arguments.count else { return nil }
        return CommandLine.arguments[index + 1]
    }

    static func load() -> LaunchConfiguration {
        let env = ProcessInfo.processInfo.environment
        let bundled = Bundle.main.url(forResource: "native-config", withExtension: "json")
            .flatMap { try? Data(contentsOf: $0) }
            .flatMap { try? JSONDecoder().decode([String: String].self, from: $0) } ?? [:]
        let root = argument("--project-root") ?? env["PROTO_MIND_PROJECT_ROOT"] ?? bundled["project_root"] ?? FileManager.default.currentDirectoryPath
        let python = argument("--python") ?? env["PROTO_MIND_PYTHON"] ?? bundled["python"] ?? "/opt/homebrew/opt/python@3.11/bin/python3.11"
        let state = argument("--state-dir").map { URL(fileURLWithPath: $0, isDirectory: true) }
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/ProtoMindNative", isDirectory: true)
        return LaunchConfiguration(projectRoot: URL(fileURLWithPath: root, isDirectory: true),
                                   python: URL(fileURLWithPath: python), stateDirectory: state,
                                   pdfHelper: argument("--pdf-helper").map { URL(fileURLWithPath: $0).resolvingSymlinksInPath() }
                                    ?? Bundle.main.url(forAuxiliaryExecutable: "ProtoMindPDF"))
    }
}
