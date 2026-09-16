import Foundation

struct NativeWorkSessionPage {
    let runs: [NativeWorkSession]
    let total: Int
    let path: String
    let warning: String?
    let nextCursor: JSONValue?

    init(_ value: JSONValue, conversation: UUID, project: URL, cursor: JSONValue? = nil) throws {
        let fields: Set<String> = ["schema", "read_only", "path", "conversation_id", "project_root", "total", "warnings",
                                   "cursor", "next_cursor", "partial", "runs"]
        guard case .object(let object) = value, Set(object.keys) == fields,
              value["schema"] == .string("proto_mind.native_work_sessions.v1"), value["read_only"] == .bool(true),
              value["conversation_id"].text == conversation.uuidString.lowercased(),
              Self.matchesProject(value["project_root"], project), value["path"].text.hasPrefix("/"),
              value["cursor"] == (cursor ?? .null),
              case .array(let rawRuns) = value["runs"], rawRuns.count <= 30,
              case .number(let count) = value["total"], count.isFinite, count.rounded() == count,
              count >= Double(rawRuns.count), count <= Double(Int.max / 2),
              case .array(let warnings) = value["warnings"], warnings.count <= 20,
              warnings.allSatisfy({ if case .string(let text) = $0 { return text.unicodeScalars.count <= 1000 }; return false }),
              value["partial"] == .bool(!value["next_cursor"].isNull) else { throw Self.error() }
        let runs = try rawRuns.map(NativeWorkSession.init)
        guard Set(runs.map(\.id)).count == runs.count,
              runs.allSatisfy({ UUID(uuidString: $0.value["conversation_id"].text) == conversation
                  && Self.matchesProject($0.value["project_root"], project) && Self.validDateText($0.value["created_at"]) }),
              zip(runs, runs.dropFirst()).allSatisfy({ Self.key($0) > Self.key($1) }) else { throw Self.error() }
        if let cursor {
            guard Self.validCursor(cursor, conversation: conversation, project: project),
                  runs.allSatisfy({ Self.key($0) < (cursor["created_at"].text, cursor["run_id"].text) }) else { throw Self.error() }
        }
        if !value["next_cursor"].isNull {
            let next = value["next_cursor"]
            guard let last = runs.last, Self.validCursor(next, conversation: conversation, project: project),
                  next["run_id"].text == last.id, next["created_at"] == last.value["created_at"], count > Double(runs.count) else { throw Self.error() }
        }
        self.runs = runs
        total = Int(count)
        path = value["path"].text
        warning = warnings.isEmpty ? nil : warnings.map(\.text).joined(separator: "\n")
        nextCursor = value["next_cursor"].isNull ? nil : value["next_cursor"]
    }

    static func key(_ run: NativeWorkSession) -> (String, String) { (run.value["created_at"].text, run.id) }

    static func matchesProject(_ value: JSONValue, _ project: URL) -> Bool {
        value.text.hasPrefix("/") && URL(fileURLWithPath: value.text).resolvingSymlinksInPath().path == project.resolvingSymlinksInPath().path
    }

    private static func validDateText(_ value: JSONValue) -> Bool {
        guard case .string(let text) = value else { return false }
        return (1...80).contains(text.unicodeScalars.count) && !text.unicodeScalars.contains(where: { $0.value < 32 })
    }

    private static func validCursor(_ value: JSONValue, conversation: UUID, project: URL) -> Bool {
        guard case .object(let fields) = value else { return false }
        return Set(fields.keys) == ["conversation_id", "project_root", "created_at", "run_id"]
            && value["conversation_id"].text == conversation.uuidString.lowercased()
            && matchesProject(value["project_root"], project) && validDateText(value["created_at"])
            && UUID(uuidString: value["run_id"].text)?.uuidString.lowercased() == value["run_id"].text
    }

    static func error() -> NativeError { .message(L10n.text("Не удалось проверить страницу журнала или её связь с диалогом. Обновите журнал.")) }
}
