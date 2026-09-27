import SwiftUI

struct PendingAgentAccess: Identifiable {
    let id = UUID()
    let conversationID: UUID
    let workspace: String?
    var provider: String = "codex"
}

struct AgentAccessGrant {
    let token: String
    let workspace: String?
    var bridgeGeneration: UUID? = nil
}

struct AgentAccessSheet: View {
    @ObservedObject var model: AppModel
    let request: PendingAgentAccess
    @State private var acknowledged = false
    private var computerUse: Bool { request.provider == "codex" && model.computerUseAvailable }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Label(computerUse || request.provider == "claude" ? L10n.text("Полный доступ к Mac, интернету и экрану") : L10n.text("Полный доступ к Mac и интернету"),
                  systemImage: "exclamationmark.shield")
                .font(.title2.weight(.semibold)).foregroundStyle(.orange)
            Text(computerUse
                 ? L10n.text("Модель сможет читать и менять файлы, запускать команды, использовать Web Search и официальный локальный Computer Use OpenAI: видеть содержимое приложений, нажимать, вводить текст и прокручивать экран. Подтверждения каждого действия не будет.")
                 : L10n.text("Модель сможет читать и менять файлы, запускать команды, использовать встроенный Web Search и обращаться к сети с правами вашего пользователя. Подтверждения каждой команды или поиска не будет. Computer Use сейчас недоступен."))
            Text(request.workspace.map { L10n.format("Начальная папка: \($0)") }
                 ?? L10n.text("Без проекта · команды начнут работу в домашней папке."))
                .font(.callout).textSelection(.enabled)
            Text(request.provider == "claude"
                 ? L10n.pick("Начальная папка не ограничивает доступ. Claude Code сможет читать и менять другие файлы Mac, выполнять команды, работать с интернетом, видеть экран и управлять приложениями мышью и клавиатурой с правами вашего пользователя, если macOS разрешила Proto-Mind запись экрана и универсальный доступ. Пока Claude работает в других приложениях, окна PM прячутся и возвращаются сами. Контекст, снимки экрана и результаты инструментов обрабатываются Anthropic. macOS продолжает управлять системными разрешениями.", "The initial folder is not an access boundary. Claude Code can read and change other Mac files, run commands, use the internet, see the screen and operate apps with the mouse and keyboard with your user permissions, if macOS allows Proto-Mind screen recording and accessibility. While Claude works in other apps, PM's windows hide and return by themselves. Anthropic processes context, screenshots and tool results. macOS still controls system permissions.")
                 : computerUse
                 ? L10n.text("Это начальная папка, не граница доступа. Доступны и другие файлы Mac и видимое содержимое экрана, включая личные данные. Запросы, страницы, скриншоты, прочитанный контекст и вывод инструментов могут обрабатываться OpenAI. Веб-страницы и экран считаются недоверенными данными. Это не root; macOS всё ещё управляет системными разрешениями.")
                 : L10n.text("Это начальная папка, не граница доступа. Доступны и другие файлы Mac, включая личные данные. Запросы, открытые страницы, прочитанный контекст и вывод инструментов могут передаваться OpenAI. Веб-страницы считаются недоверенными данными. Это не root; macOS всё ещё управляет системными разрешениями."))
                .font(.callout).foregroundStyle(.secondary)
            if computerUse {
                Label(L10n.format("OpenAI Computer Use \(model.computerUseVersion.isEmpty ? L10n.text("установлен") : model.computerUseVersion) · скриншоты, UI-дерево, координаты и введённый текст не сохраняются в журнал Proto-Mind."), systemImage: "display.and.arrow.down")
                    .font(.callout).foregroundStyle(.secondary)
            }
            Text(L10n.text("Выбор сохраняется для этого диалога после перезапуска. Смена папки, провайдера или выключение режима сбрасывают доступ. Stop или Esc прерывают ход, но не откатывают уже сделанное и не гарантируют завершения отделённых процессов."))
                .font(.callout).foregroundStyle(.secondary)
            Toggle(L10n.text("Понимаю область доступа и разрешаю инструменты"), isOn: $acknowledged)
            HStack {
                Button(L10n.text("Оставить обычный чат")) { model.pendingAgentAccess = nil }.keyboardShortcut(.cancelAction)
                Spacer()
                Button(L10n.text("Включить полный доступ")) { Task { await model.confirmAgentAccess() } }
                    .buttonStyle(.borderedProminent).nativeHoverSurface().disabled(!acknowledged || model.operationBusy || model.isRunning(request.conversationID))
            }
        }.padding(28).workspacePageSize(width: 600)
    }
}

struct AgentActivityView: View {
    let items: [JSONValue]
    var receipt: JSONValue = .null

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label(L10n.text("Действия модели"), systemImage: "terminal").font(.callout.weight(.semibold))
                Spacer()
                Text(statusLabel).font(.caption).foregroundStyle(receipt["status"].text == "completed" ? Color.secondary : .orange)
            }
            Text(L10n.text("Полный доступ · наблюдаемые действия, не внутренние рассуждения и не автоматическая проверка результата"))
                .font(.caption2).foregroundStyle(.secondary)
            if !receipt["contract_hash"].text.isEmpty {
                DisclosureGroup(L10n.format("Контракт запуска · \(receipt["contract_hash"].text.prefix(12))")) {
                    VStack(alignment: .leading, spacing: 5) {
                        Text(L10n.text("Провайдер: подписочный Codex · режим: полный доступ"))
                        if ["proto_mind.native_agent_contract.v2", "proto_mind.native_agent_contract.v3"].contains(receipt["contract"]["schema"].text) {
                            Text(L10n.text("Без ограничения длительности и количества действий · остановка кнопкой Стоп"))
                            Text(L10n.format("В локальном журнале — последние \(receipt["contract"]["limits"]["max_retained_items"].integer) действий"))
                        } else {
                            Text(L10n.format("Лимит этого старого запуска: \(receipt["contract"]["limits"]["max_seconds"].integer) с · \(receipt["contract"]["limits"]["max_observed_items"].integer) действий"))
                        }
                        Text(L10n.pick("Автоповтор действий выключен. Завершение ответа не является проверкой результата.", "Actions are not retried automatically. A completed response is not verified task success."))
                        if receipt["contract"]["schema"].text == "proto_mind.native_agent_contract.v3" {
                            Text(L10n.pick("Инструменты PM: задачи, вопросы, браузер, документы, память проекта и включённые MCP.", "PM tools: tasks, questions, browser, documents, project memory and enabled MCP connections."))
                        }
                        if receipt["runtime_inventory"]["verified"].flag {
                            Text(L10n.format("Runtime allowlist проверен: \(receipt["runtime_inventory"]["computer_use_tools"].items.count) Computer Use tools"))
                        }
                    }.font(.caption2).foregroundStyle(.secondary).textSelection(.enabled)
                }
            }
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                AgentToolRow(item: item)
            }
            if !receipt.isNull {
                if receipt["items_truncated"].flag {
                    Text(L10n.text("Сохранена последняя часть действий. Счётчики относятся к этому фрагменту."))
                        .font(.caption2).foregroundStyle(.secondary)
                }
                Text(L10n.format("Run \(receipt["run_id"].text.prefix(8)) · команд: \(receipt["command_count"].integer) · поисков: \(receipt["web_search_count"].integer) · экранных действий: \(receipt["computer_use_count"].integer) · \(receipt["finished_at"].text)"))
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
        case "completed": return L10n.text("Ход завершён")
        case "failed": return L10n.text("Ошибка · проверьте результат")
        case "interrupted": return L10n.text("Остановлен")
        default: return L10n.text("В работе")
        }
    }

}

struct AgentToolRow: View {
    let item: JSONValue

    var body: some View {
        DisclosureGroup {
            ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                if !item["cwd"].text.isEmpty { Text(L10n.format("Папка: \(item["cwd"].text)")) }
                if !item["exit_code"].isNull { Text(L10n.format("Код завершения: \(item["exit_code"].integer)")) }
                if !item["app"].text.isEmpty { Text(L10n.format("Приложение: \(item["app"].text)")) }
                if !item["note"].text.isEmpty { Text(item["note"].text) }
                if !item["failure_message"].text.isEmpty {
                    Text(item["failure_message"].text).foregroundStyle(.orange)
                }
                if !item["recovery"].text.isEmpty { Text(item["recovery"].text) }
                // A command's description is already its title.
                ForEach(["command", "query", "url", "output_preview", "diff_preview", "text", "path"].filter { item["kind"].text != "commandExecution" || $0 != "text" }, id: \.self) { key in
                    if !item[key].text.isEmpty { Text(item[key].text).fixedSize(horizontal: false, vertical: true) }
                }
                ForEach(Array(item["paths"].items.enumerated()), id: \.offset) { _, path in Text(path.text) }
            }.font(NativeTheme.codeFont).textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading).padding(12)
            }.frame(maxHeight: 230)
                .background(NativeTheme.composer, in: RoundedRectangle(cornerRadius: 9))
        } label: {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Image(systemName: Self.icon(item))
                Text(Self.title(item)).lineLimit(1).truncationMode(.middle)
                Spacer(minLength: 4)
                Text(status).font(.system(size: 11)).foregroundStyle(item["status"].text == "failed" ? Color.orange : .secondary)
            }.font(.system(size: 13)).foregroundStyle(.secondary)
        }
    }

    static func icon(_ item: JSONValue) -> String {
        switch item["kind"].text {
        case "commandExecution": return "terminal"
        case "fileChange": return "pencil"
        case "fileRead": return "doc.text"
        case "search": return "magnifyingglass"
        case "webSearch": return "globe"
        case "computerUse": return "display.and.arrow.down"
        case "dynamicToolCall": return "cube"
        case "agentTool": return "wrench.and.screwdriver"
        case "imageView": return "photo"
        default: return "list.bullet"
        }
    }

    static func title(_ item: JSONValue) -> String {
        let name = { (path: String) in URL(fileURLWithPath: path).lastPathComponent }
        switch item["kind"].text {
        case "commandExecution":
            // The model's own description reads better than a long command line.
            let command = item["command"].text.split(whereSeparator: \.isNewline).first.map(String.init) ?? ""
            return !item["text"].text.isEmpty ? item["text"].text : !command.isEmpty ? command : L10n.text("Команда в терминале")
        case "fileChange":
            let paths = item["paths"].items.map(\.text).filter { !$0.isEmpty }
            return paths.count == 1 && item["change_count"].integer <= 1 ? L10n.format("Изменение · \(name(paths[0]))")
                : L10n.format("Изменения файлов: \(item["change_count"].integer)")
        case "fileRead": return L10n.format("Чтение · \(name(item["path"].text))")
        case "search": return L10n.format("Поиск · \(item["query"].text)")
        case "agentTool": return item["text"].text.isEmpty ? item["tool"].text : "\(item["tool"].text) · \(item["text"].text)"
        case "imageView": return L10n.text("Просмотр изображения")
        case "dynamicToolCall":
            let tool = item["tool"].text
            // Earlier Claude turns recorded built-in tools (Bash, Read…) as PM tools.
            guard tool.hasPrefix("pm_") || tool.hasPrefix("mcp__pm__") else { return tool }
            return "PM · " + tool.replacingOccurrences(of: "mcp__pm__", with: "").replacingOccurrences(of: "pm_", with: "")
        case "webSearch": return item["query"].text.isEmpty ? (item["url"].text.isEmpty ? L10n.text("Поиск в интернете") : item["url"].text) : item["query"].text
        case "computerUse":
            let names = ["get_app_state": L10n.text("Состояние экрана"), "list_apps": L10n.text("Список приложений"), "click": L10n.text("Нажатие"),
                         "set_value": L10n.text("Ввод значения"), "type_text": L10n.text("Ввод текста"), "press_key": L10n.text("Клавиатура"),
                         "scroll": L10n.text("Прокрутка"), "drag": L10n.text("Перетаскивание"), "select_text": L10n.text("Выбор текста"),
                         "perform_secondary_action": L10n.text("Дополнительное действие"), "move": L10n.text("Перемещение курсора"),
                         "zoom": L10n.text("Приближение экрана"), "wait": L10n.text("Пауза"), "cursor": L10n.text("Позиция курсора"),
                         "batch": L10n.text("Серия действий")]
            let action = names[item["tool"].text] ?? "Computer Use"
            return item["app"].text.isEmpty ? action : "\(action) · \(item["app"].text)"
        default: return L10n.text("План работы")
        }
    }

    private var status: String {
        let duration = item["duration_ms"].isNull ? "" : " · " + WorkLogPresentation.duration(item["duration_ms"].integer)
        switch item["status"].text {
        case "completed": return L10n.text("Завершено") + duration
        case "failed": return L10n.text("Ошибка") + duration
        case "declined": return L10n.text("Отклонено")
        case "unknown": return L10n.text("Исход неизвестен")
        default: return L10n.text("Выполняется")
        }
    }
}
