import SwiftUI

struct GitHubConnectionView: View {
    @ObservedObject var app: AppModel
    @ObservedObject var github: GitHubModel

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                Image(systemName: "point.3.connected.trianglepath.dotted").font(.system(size: 24)).foregroundStyle(.secondary)
                VStack(alignment: .leading, spacing: 4) {
                    Text("GitHub").font(.system(size: 17, weight: .semibold))
                    Text(github.connected ? L10n.format("Подключён · @\(github.status["login"].text)") : L10n.text("Репозитории, pull requests и задачи"))
                        .font(.system(size: 12)).foregroundStyle(.secondary)
                }
                Spacer()
                if github.loading { ProgressView().controlSize(.small) }
            }
            HStack(spacing: 12) {
                if github.connected {
                    Button(L10n.text("Отключить")) { Task { await github.disconnect(app: app) } }
                } else if !github.status["available_login"].text.isEmpty {
                    Button(L10n.format("Подключить @\(github.status["available_login"].text)")) { Task { await github.connect(app: app) } }.buttonStyle(.borderedProminent)
                } else if !github.status.isNull {
                    Button(github.status["installed"].flag ? L10n.text("Войти в GitHub…") : L10n.text("Установить GitHub CLI…")) { github.openLogin() }
                }
                Button(L10n.text("Проверить")) { Task { await github.refresh(app: app) } }
                if github.status["enabled"].flag && !github.connected {
                    Button(L10n.text("Отключить")) { Task { await github.disconnect(app: app) } }
                }
            }.disabled(github.loading || app.busy)
            if !github.status["notice"].text.isEmpty {
                Text(github.status["notice"].text).font(.system(size: 12)).foregroundStyle(.secondary)
            }
            Text(L10n.text("Используется вход GitHub CLI на этом Mac. Для работы помощника с GitHub включите «Доступ к Mac» в диалоге."))
                .font(.system(size: 12)).foregroundStyle(.secondary)
            if let error = github.error { Text(error).font(.system(size: 12)).foregroundStyle(.orange).textSelection(.enabled) }
        }.padding(.vertical, 8)
    }
}

struct GitHubView: View {
    @ObservedObject var app: AppModel
    @ObservedObject var github: GitHubModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                HStack {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("GitHub").font(.system(size: 28, weight: .semibold))
                        Text(L10n.text("Ваши проекты и текущая работа")).foregroundStyle(.secondary)
                    }
                    Spacer()
                    if github.loading { ProgressView().controlSize(.small) }
                }
                if !github.connected {
                    GitHubConnectionView(app: app, github: github)
                } else if !github.repository.isNull {
                    repositoryDetail
                } else {
                    repositories
                }
                if github.connected, let error = github.error {
                    Text(error).foregroundStyle(.orange).font(.callout).textSelection(.enabled)
                }
            }.frame(maxWidth: 850, alignment: .leading).padding(32).frame(maxWidth: .infinity)
        }.background(NativeTheme.canvas).font(NativeTheme.interfaceFont).buttonStyle(.nativeHover)
            .task {
                await github.refresh(app: app)
                if github.connected && github.repositories.isEmpty { await github.loadRepositories(app: app) }
            }
            .onChange(of: github.connected) { _, connected in
                if connected { Task { await github.loadRepositories(app: app) } }
            }
    }

    private var repositories: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                TextField(L10n.text("Найти среди загруженных репозиториев"), text: $github.query).textFieldStyle(.roundedBorder)
                Button { Task { await github.loadRepositories(app: app) } } label: { Image(systemName: "arrow.clockwise") }
                    .help(L10n.text("Обновить репозитории")).accessibilityLabel(L10n.text("Обновить репозитории")).disabled(github.loading || app.busy)
            }
            Text(L10n.format("@\(github.status["login"].text) · сначала недавно обновлённые")).font(.caption).foregroundStyle(.secondary)
            LazyVStack(spacing: 6) {
                ForEach(Array(github.filteredRepositories.enumerated()), id: \.offset) { _, item in
                    Button { Task { await github.inspect(item["name"].text, app: app) } } label: {
                        HStack(alignment: .top, spacing: 12) {
                            Image(systemName: item["private"].flag ? "lock" : "folder").foregroundStyle(.secondary).frame(width: 20)
                            VStack(alignment: .leading, spacing: 5) {
                                Text(item["name"].text).font(.system(size: 14, weight: .medium)).lineLimit(2)
                                if !item["description"].text.isEmpty { Text(item["description"].text).font(.system(size: 12)).foregroundStyle(.secondary).lineLimit(2) }
                            }
                            Spacer()
                            Image(systemName: "chevron.right").foregroundStyle(.tertiary)
                        }.padding(16).frame(maxWidth: .infinity, alignment: .leading)
                            .background(NativeTheme.composer, in: RoundedRectangle(cornerRadius: 12))
                    }.disabled(github.loading || app.busy)
                }
            }
            if github.filteredRepositories.isEmpty && !github.loading {
                Text(github.query.isEmpty ? L10n.text("Репозитории пока не найдены.") : L10n.text("Среди загруженных репозиториев совпадений нет."))
                    .foregroundStyle(.secondary).padding(.vertical, 20)
            }
            if github.nextPage != nil {
                Button(L10n.text("Показать ещё")) { Task { await github.loadRepositories(app: app, more: true) } }.disabled(github.loading || app.busy)
            }
        }
    }

    private var repositoryDetail: some View {
        VStack(alignment: .leading, spacing: 24) {
            Button { github.back() } label: { Label(L10n.text("Репозитории"), systemImage: "chevron.left") }
            VStack(alignment: .leading, spacing: 12) {
                Text(github.repository["name"].text).font(.system(size: 22, weight: .semibold)).textSelection(.enabled)
                HStack(spacing: 16) {
                    if let url = URL(string: github.repository["url"].text) { Link(L10n.text("Открыть на GitHub"), destination: url) }
                    Button(L10n.text("Обсудить репозиторий")) { github.discuss(L10n.format("Посмотри репозиторий \(github.repository["url"].text)"), app: app) }.disabled(app.busy)
                }
            }
            ForEach(["pr", "issue"], id: \.self) { kind in
                VStack(alignment: .leading, spacing: 12) {
                    Text(kind == "pr" ? L10n.text("Открытые pull requests") : L10n.text("Открытые задачи")).font(.system(size: 17, weight: .semibold))
                    ForEach(Array(github.repository[kind].items.enumerated()), id: \.offset) { _, item in
                        HStack(alignment: .top, spacing: 12) {
                            Text("#\(item["number"].integer)").foregroundStyle(.secondary).monospacedDigit()
                            VStack(alignment: .leading, spacing: 8) {
                                Text(item["title"].text).lineLimit(3)
                                HStack(spacing: 16) {
                                    if let url = URL(string: item["url"].text) { Link(L10n.text("Открыть"), destination: url) }
                                    Button(L10n.text("Обсудить")) { github.discuss(L10n.format("Посмотри \(kind == "pr" ? "pull request" : L10n.text("задачу")) \(item["url"].text)"), app: app) }.disabled(app.busy)
                                }.font(.caption)
                            }
                            Spacer(minLength: 0)
                        }.padding(14).frame(maxWidth: .infinity, alignment: .leading)
                            .background(NativeTheme.composer, in: RoundedRectangle(cornerRadius: 10))
                    }
                    if github.repository[kind].items.isEmpty { Text(L10n.format("Открытых \(kind == "pr" ? "pull requests" : L10n.text("задач")) нет.")).foregroundStyle(.secondary) }
                    if github.repository[kind].items.count == 20 { Text(L10n.text("Показаны первые 20. Остальные доступны на GitHub.")).font(.caption).foregroundStyle(.secondary) }
                }
            }
        }
    }
}
