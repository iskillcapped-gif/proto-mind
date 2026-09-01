import Foundation

enum LibraryCollection: String, Codable, CaseIterable, Identifiable {
    case memory, goals, skills
    var id: String { rawValue }
    var section: WorkspaceSection {
        switch self { case .memory: return .memory; case .goals: return .goals; case .skills: return .skills }
    }
    var title: String {
        switch self { case .memory: return "Память"; case .goals: return "Цели"; case .skills: return "Навыки" }
    }
    var symbol: String {
        switch self { case .memory: return "brain"; case .goals: return "scope"; case .skills: return "books.vertical" }
    }
    var subtitle: String {
        switch self {
        case .memory: return "Долговременная и рабочая память. Поиск не изменяет записи."
        case .goals: return "Фокус и состояния целей. Никакого автоматического планирования."
        case .skills: return "Сохранённые описания и процедуры. Просмотр не запускает навык."
        }
    }
    var manualDoctor: String {
        switch self { case .memory: return "/memory doctor"; case .goals: return "/loop doctor"; case .skills: return "/skills provenance-doctor" }
    }
}

enum LibraryFilter: String, Codable, CaseIterable, Identifiable {
    case current, history, all
    var id: String { rawValue }
    var title: String {
        switch self { case .current: return "Текущие"; case .history: return "История"; case .all: return "Все" }
    }
}

struct LibrarySource: Decodable, Identifiable, Equatable {
    var store: String
    var path: String
    var exists: Bool
    var health: String
    var recordCount: Int
    var skippedCount: Int
    var sha256: String
    var modifiedAt: String
    var message: String
    var id: String { store }
    var title: String { Self.title(store) }
    static func title(_ store: String) -> String {
        switch store {
        case "persistent": return "Долговременная память"
        case "working": return "Рабочая память"
        case "goals": return "Goal Stack"
        case "skills": return "Skill Library"
        default: return store
        }
    }
}

struct LibraryItem: Decodable, Identifiable, Equatable {
    var id: String
    var recordId: String
    var store: String
    var title: String
    var preview: String
    var status: String
    var current: Bool
    var focused: Bool
    var priority: String
    var subtype: String
    var tags: [String]
    var createdAt: String
    var updatedAt: String
    var source: String
    var storeSha256: String

    var stateLabel: String {
        switch status {
        case "active": return "Активно"
        case "paused": return "На паузе"
        case "completed": return "Завершено"
        case "cancelled": return "Отменено"
        case "superseded": return "Заменено"
        case "inactive": return "Неактивно"
        case "archived": return "В архиве"
        default: return "Статус неизвестен"
        }
    }
    var priorityLabel: String {
        switch priority { case "high": return "Высокий"; case "normal": return "Обычный"; case "low": return "Низкий"; default: return "Неизвестно" }
    }
}

private func decodeLibrary<T: Decodable>(_ type: T.Type, _ value: JSONValue) throws -> T {
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    return try decoder.decode(type, from: JSONEncoder().encode(value))
}

enum LocalKnowledgeEnvelope {
    static func structured(_ value: JSONValue, capability: String) throws -> JSONValue {
        guard ["search", "fetch"].contains(capability),
              case .object(let root) = value,
              Set(root.keys) == Set(["structuredContent", "content", "_meta"]),
              case .array(let content) = root["content"], content.count == 1,
              content[0]["type"].text == "text", !content[0]["text"].text.isEmpty,
              case .object(let metadata) = root["_meta"],
              case .object(let local) = metadata["proto_mind"],
              local["capability"] == .string(capability),
              local["contract_version"] == .number(1),
              local["local_only"] == .bool(true),
              local["transport"] == .string("private_stdio"),
              local["network_access"] == .bool(false),
              local["store_mutation"] == .bool(false),
              local["model_dispatch"] == .bool(false),
              let structured = root["structuredContent"], !structured.isNull else {
            throw NativeError.message("Неожиданный локальный capability-конверт. Данные не изменены.")
        }
        return structured
    }
}

struct LibraryPage: Decodable {
    var schema: String
    var readOnly: Bool
    var collection: LibraryCollection
    var query: String
    var filter: LibraryFilter
    var offset: Int
    var limit: Int
    var totalRecords: Int
    var currentRecords: Int
    var matchingRecords: Int
    var omittedRecords: Int
    var items: [LibraryItem]
    var sources: [LibrarySource]
    var warnings: [String]

    static func decode(_ value: JSONValue, for collection: LibraryCollection) throws -> LibraryPage {
        let page = try decodeLibrary(Self.self, value)
        guard page.schema == "proto_mind.native_library.page.v1", page.readOnly, page.collection == collection,
              page.offset >= 0, (1...100).contains(page.limit), page.items.count <= page.limit,
              page.totalRecords >= 0, page.currentRecords >= 0, page.currentRecords <= page.totalRecords,
              page.matchingRecords >= 0, page.omittedRecords >= 0,
              Set(page.items.map(\.id)).count == page.items.count else {
            throw NativeError.message("Неожиданный контракт просмотра. Данные не изменены.")
        }
        return page
    }
}

struct LibraryBlock: Decodable, Identifiable {
    var key: String
    var text: String
    var truncated: Bool
    var id: String { key }
    var title: String {
        switch key { case "content": return "Содержание"; case "title", "name": return "Название"; case "description": return "Описание"; case "summary": return "Кратко"; case "body": return "Текст навыка"; default: return key }
    }
}

struct LibraryField: Decodable, Identifiable {
    var key: String
    var value: String
    var id: String { key }
    var title: String {
        ["id": "ID записи", "source": "Источник", "type": "Тип", "category": "Категория",
         "importance": "Важность", "confidence": "Сохранённая уверенность", "weight": "Вес",
         "timestamp": "Дата записи", "created_at": "Создано", "updated_at": "Обновлено",
         "last_used": "Последнее использование", "usage_count": "Счётчик использований",
         "last_used_at": "Последнее использование", "uses": "Счётчик использований",
         "superseded_by": "Заменено записью", "superseded_at": "Дата замены", "superseded_reason": "Причина замены",
         "provenance": "Схема происхождения", "lifecycle": "Схема жизненного цикла"][key] ?? key
    }
}

struct LibraryDetail: Decodable {
    var schema: String
    var readOnly: Bool
    var collection: LibraryCollection
    var item: LibraryItem?
    var blocks: [LibraryBlock]
    var fields: [LibraryField]
    var sources: [LibrarySource]
    var warnings: [String]
    var changedSinceList: Bool
    var message: String

    static func decode(_ value: JSONValue, for collection: LibraryCollection, recordKey: String) throws -> LibraryDetail {
        let detail = try decodeLibrary(Self.self, value)
        guard detail.schema == "proto_mind.native_library.detail.v1", detail.readOnly, detail.collection == collection,
              detail.item == nil || detail.item?.id == recordKey,
              detail.blocks.count <= 3, detail.blocks.allSatisfy({ $0.text.count <= 24_000 }),
              Set(detail.fields.map(\.id)).count == detail.fields.count,
              Set(detail.blocks.map(\.id)).count == detail.blocks.count else {
            throw NativeError.message("Неожиданный контракт карточки. Данные не изменены.")
        }
        return detail
    }
}
