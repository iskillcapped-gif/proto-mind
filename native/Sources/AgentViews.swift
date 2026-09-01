import SwiftUI

struct PendingAgentAccess: Identifiable {
    let id = UUID()
    let conversationID: UUID
    let workspace: String
}

struct AgentAccessGrant {
    let token: String
    let workspace: String
}

struct AgentAccessSheet: View {
    @ObservedObject var model: AppModel
    let request: PendingAgentAccess
    @State private var acknowledged = false

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Label(model.computerUseAvailable ? "Полный доступ к Mac, интернету и экрану" : "Полный доступ к Mac и интернету",
                  systemImage: "exclamationmark.shield")
                .font(.title2.weight(.semibold)).foregroundStyle(.orange)
            Text(model.computerUseAvailable
                 ? "Модель сможет читать и менять файлы, запускать команды, использовать Web Search и официальный локальный Computer Use OpenAI: видеть содержимое приложений, нажимать, вводить текст и прокручивать экран. Подтверждения каждого действия не будет."
                 : "Модель сможет читать и менять файлы, запускать команды, использовать встроенный Web Search и обращаться к сети с правами вашего пользователя. Подтверждения каждой команды или поиска не будет. Computer Use сейчас недоступен.")
            Text("Рабочая папка: \(request.workspace)").font(.system(.callout, design: .monospaced)).textSelection(.enabled)
            Text(model.computerUseAvailable
                 ? "Это начальная папка, не граница доступа. Доступны и другие файлы Mac и видимое содержимое экрана, включая личные данные. Запросы, страницы, скриншоты, прочитанный контекст и вывод инструментов могут обрабатываться OpenAI. Веб-страницы и экран считаются недоверенными данными. Это не root; macOS всё ещё управляет системными разрешениями."
                 : "Это начальная папка, не граница доступа. Доступны и другие файлы Mac, включая личные данные. Запросы, открытые страницы, прочитанный контекст и вывод инструментов могут передаваться OpenAI. Веб-страницы считаются недоверенными данными. Это не root; macOS всё ещё управляет системными разрешениями.")
                .font(.callout).foregroundStyle(.secondary)
            if model.computerUseAvailable {
                Label("OpenAI Computer Use \(model.computerUseVersion.isEmpty ? "установлен" : model.computerUseVersion) · скриншоты, UI-дерево, координаты и введённый текст не сохраняются в журнал Proto-Mind.", systemImage: "display.and.arrow.down")
                    .font(.callout).foregroundStyle(.secondary)
            }
            Text("Разрешение действует для этого диалога до перезапуска приложения, смены папки/провайдера или выключения режима. Stop или Esc позволяют прервать ход и вернуть управление, но не откатывают уже сделанное и не гарантируют завершения отделённых процессов.")
                .font(.callout).foregroundStyle(.secondary)
            Toggle("Понимаю область доступа и разрешаю инструменты", isOn: $acknowledged)
            HStack {
                Button("Оставить обычный чат") { model.pendingAgentAccess = nil }.keyboardShortcut(.cancelAction)
                Spacer()
                Button("Включить полный доступ") { Task { await model.confirmAgentAccess() } }
                    .buttonStyle(.borderedProminent).nativeHoverSurface().disabled(!acknowledged || model.busy)
            }
        }.padding(28).frame(width: 600)
    }
}

struct AgentActivityView: View {
    let items: [JSONValue]
    var receipt: JSONValue = .null

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label("Действия модели", systemImage: "terminal").font(.callout.weight(.semibold))
                Spacer()
                Text(statusLabel).font(.caption).foregroundStyle(receipt["status"].text == "completed" ? Color.secondary : .orange)
            }
            Text("Полный доступ · наблюдаемые действия, не внутренние рассуждения и не автоматическая проверка результата")
                .font(.caption2).foregroundStyle(.secondary)
            if !receipt["contract_hash"].text.isEmpty {
                DisclosureGroup("Контракт запуска · \(receipt["contract_hash"].text.prefix(12))") {
                    VStack(alignment: .leading, spacing: 5) {
                        Text("Провайдер: подписочный Codex · режим: полный доступ")
                        Text("Лимит: \(receipt["contract"]["limits"]["max_seconds"].integer) с · \(receipt["contract"]["limits"]["max_observed_items"].integer) наблюдаемых действий")
                        Text("Автоповтор: нет · фоновая работа: нет · provider completion не считается проверкой")
                        if receipt["runtime_inventory"]["verified"].flag {
                            Text("Runtime allowlist проверен: \(receipt["runtime_inventory"]["computer_use_tools"].items.count) Computer Use tools")
                        }
                    }.font(.caption2).foregroundStyle(.secondary).textSelection(.enabled)
                }
            }
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                AgentToolRow(item: item)
            }
            if !receipt.isNull {
                Text("Run \(receipt["run_id"].text.prefix(8)) · команд: \(receipt["command_count"].integer) · поисков: \(receipt["web_search_count"].integer) · экранных действий: \(receipt["computer_use_count"].integer) · \(receipt["finished_at"].text)")
                    .font(.caption2).foregroundStyle(.secondary).textSelection(.enabled)
                ForEach(Array(receipt["warnings"].items.enumerated()), id: \.offset) { _, warning in
                    Text(warning.text).font(.caption2).foregroundStyle(.secondary).textSelection(.enabled)
                }
            }
        }.padding(14).background(Color.orange.opacity(0.045), in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.orange.opacity(0.15)))
    }

    private var statusLabel: String {
        switch receipt["status"].text {
        case "completed": return "Ход завершён"
        case "failed": return "Ошибка · проверьте результат"
        case "interrupted": return "Остановлен"
        default: return "В работе"
        }
    }

}

struct AgentToolRow: View {
    let item: JSONValue

    var body: some View {
        DisclosureGroup {
            VStack(alignment: .leading, spacing: 8) {
                if !item["cwd"].text.isEmpty { Text("Папка: \(item["cwd"].text)") }
                if !item["exit_code"].isNull { Text("Код завершения: \(item["exit_code"].integer)") }
                if !item["app"].text.isEmpty { Text("Приложение: \(item["app"].text)") }
                if !item["note"].text.isEmpty { Text(item["note"].text) }
                if !item["failure_message"].text.isEmpty {
                    Text(item["failure_message"].text).foregroundStyle(.orange)
                }
                if !item["recovery"].text.isEmpty { Text(item["recovery"].text) }
                ForEach(["command", "query", "url", "output_preview", "diff_preview", "text", "path"], id: \.self) { key in
                    if !item[key].text.isEmpty { Text(item[key].text).fixedSize(horizontal: false, vertical: true) }
                }
                ForEach(Array(item["paths"].items.enumerated()), id: \.offset) { _, path in Text(path.text) }
            }.font(NativeTheme.codeFont).textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading).padding(12)
                .background(NativeTheme.composer, in: RoundedRectangle(cornerRadius: 9))
        } label: {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Image(systemName: item["kind"].text == "commandExecution" ? "terminal" : item["kind"].text == "webSearch" ? "globe" : item["kind"].text == "computerUse" ? "display.and.arrow.down" : "doc.text")
                Text(title).lineLimit(2)
                Spacer(minLength: 4)
                Text(status).font(.system(size: 11)).foregroundStyle(item["status"].text == "failed" ? Color.orange : .secondary)
            }.font(.system(size: 13)).foregroundStyle(.secondary)
        }
    }

    private var title: String {
        switch item["kind"].text {
        case "commandExecution": return item["command"].text
        case "fileChange": return "Изменения файлов: \(item["change_count"].integer)"
        case "imageView": return "Просмотр изображения"
        case "webSearch": return item["query"].text.isEmpty ? "Поиск в интернете" : item["query"].text
        case "computerUse":
            let names = ["get_app_state": "Состояние экрана", "list_apps": "Список приложений", "click": "Нажатие",
                         "set_value": "Ввод значения", "type_text": "Ввод текста", "press_key": "Клавиатура",
                         "scroll": "Прокрутка", "drag": "Перетаскивание", "select_text": "Выбор текста",
                         "perform_secondary_action": "Дополнительное действие"]
            let action = names[item["tool"].text] ?? "Computer Use"
            return item["app"].text.isEmpty ? action : "\(action) · \(item["app"].text)"
        default: return "План работы"
        }
    }

    private var status: String {
        switch item["status"].text {
        case "completed": return "Завершено"
        case "failed": return "Ошибка"
        case "declined": return "Отклонено"
        case "unknown": return "Исход неизвестен"
        default: return "Выполняется"
        }
    }
}
