import CryptoKit
import Foundation

func memorySuggestionError() -> NativeError {
    .message("Источник предложения изменился или не прошёл проверку. Ничего не сохранено; проверьте сообщение и заметки проекта.")
}

func suggestionTextHash(_ text: String) -> String {
    SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
}

struct MemorySuggestion: Identifiable, Equatable {
    let value: JSONValue
    var id: String { value["id"].text }
    var kind: String { value["kind"].text }
    func quote(in text: String) throws -> String {
        let characters = Array(text.unicodeScalars)
        let start = value["start"].integer, end = value["end"].integer
        guard start >= 0, end > start, end <= characters.count else { throw memorySuggestionError() }
        let quote = String(String.UnicodeScalarView(characters[start..<end]))
        guard suggestionTextHash(quote) == value["content_sha256"].text else { throw memorySuggestionError() }
        return quote
    }
}

struct MemorySuggestionsReport {
    let value: JSONValue
    var source: JSONValue { value["source"] }
    var items: [MemorySuggestion] { value["candidates"].items.map { MemorySuggestion(value: $0) } }
    var reference: JSONValue { .object(["run_id": source["run_id"], "fingerprint": source["fingerprint"]]) }

    init(_ value: JSONValue, text: String? = nil, run: JSONValue? = nil) throws {
        let fields: Set<String> = ["schema", "algorithm", "source", "state", "reason", "candidates", "omitted_count", "read_only", "model_call_performed", "automatic_save", "permission_granted"]
        let source = value["source"]
        guard case .object(let raw) = value, Set(raw.keys) == fields,
              value["schema"] == .string("proto_mind.native_memory_suggestions.v1"),
              value["algorithm"] == .string("explicit_operator_statements_v1"),
              case .object(let origin) = source, Set(origin.keys) == ["conversation_id", "workspace", "input_sha256", "input_chars", "run_id", "fingerprint"],
              let conversation = UUID(uuidString: source["conversation_id"].text),
              UUID(uuidString: source["run_id"].text)?.uuidString.lowercased() == source["run_id"].text,
              ProjectMemoryScope(conversationID: conversation, workspace: source["workspace"]["path"].text).matches(source["workspace"]),
              source["workspace"]["path"].text.hasPrefix("/"),
              ["input_sha256", "fingerprint"].allSatisfy({ decisionHashValue(source[$0].text) }),
              Self.count(source["input_chars"], in: 1...32_000), Self.count(value["omitted_count"], in: 0...1000),
              case .array(let candidates) = value["candidates"], candidates.count <= 2,
              Set(candidates.map { $0["id"].text }).count == candidates.count,
              value["read_only"] == .bool(true),
              ["model_call_performed", "automatic_save", "permission_granted"].allSatisfy({ value[$0] == .bool(false) }) else { throw memorySuggestionError() }
        let reasons = ["suggested": ["explicit_operator_statement"], "no_candidates": ["no_explicit_statement", "already_in_current_notes"],
                       "unavailable": ["scope_settings_or_notes_need_review"]]
        guard reasons[value["state"].text]?.contains(value["reason"].text) == true,
              (value["state"] == .string("suggested")) == !candidates.isEmpty,
              !candidates.isEmpty || value["omitted_count"] == .number(0) else { throw memorySuggestionError() }
        var previousEnd = 0
        for candidate in candidates {
            guard case .object(let fields) = candidate, Set(fields.keys) == ["id", "kind", "start", "end", "content_sha256"],
                  ProjectNote.kinds.contains(candidate["kind"].text), decisionHashValue(candidate["content_sha256"].text),
                  Self.count(candidate["start"], in: previousEnd...12_000), Self.count(candidate["end"], in: 1...12_000),
                  (12...600).contains(candidate["end"].integer - candidate["start"].integer),
                  candidate["end"].integer <= source["input_chars"].integer else { throw memorySuggestionError() }
            let material = "\(source["run_id"].text)\n\(source["input_sha256"].text)\n\(candidate["kind"].text)\n\(candidate["start"].integer):\(candidate["end"].integer)\n\(candidate["content_sha256"].text)"
            guard candidate["id"] == .string(suggestionTextHash(material)) else { throw memorySuggestionError() }
            previousEnd = candidate["end"].integer
        }
        if let text {
            guard source["input_sha256"] == .string(suggestionTextHash(text)), source["input_chars"].integer == text.unicodeScalars.count else { throw memorySuggestionError() }
            for candidate in candidates { _ = try MemorySuggestion(value: candidate).quote(in: text) }
        }
        if let run {
            guard run["status"] == .string("completed"), run["display_status"] == .string("completed"), run["provider"] == .string("codex"),
                  run["id"] == source["run_id"], run["fingerprint"] == source["fingerprint"],
                  ["conversation_id", "workspace", "input_sha256", "input_chars"].allSatisfy({ run[$0] == source[$0] }) else { throw memorySuggestionError() }
        }
        self.value = value
    }

    private static func count(_ value: JSONValue, in range: ClosedRange<Int>) -> Bool {
        if case .number(let number) = value {
            return number.isFinite && number.rounded() == number && (Double(range.lowerBound)...Double(range.upperBound)).contains(number)
        }
        return false
    }
}

func validateMemorySuggestionHistory(_ messages: [ChatMessage], conversation: UUID) throws {
    for message in messages {
        guard let value = message.memorySuggestions else {
            if message.memorySuggestionSourceID != nil { throw memorySuggestionError() }
            continue
        }
        guard message.role == "assistant", !message.isError, let id = message.memorySuggestionSourceID,
              let source = messages.first(where: { $0.id == id }), source.role == "user", !source.isError, source.operatorInput != true else { throw memorySuggestionError() }
        let report = try MemorySuggestionsReport(value, text: source.text)
        guard UUID(uuidString: report.source["conversation_id"].text) == conversation else { throw memorySuggestionError() }
    }
}
