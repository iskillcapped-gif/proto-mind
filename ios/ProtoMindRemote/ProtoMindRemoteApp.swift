import SwiftUI
import UIKit

@main
@MainActor
struct ProtoMindRemoteApp: App {
    @StateObject private var model = makeRemoteModel()
    var body: some Scene {
        WindowGroup { RemoteRootView(model: model).tint(.cyan) }
    }
}

struct RemoteRootView: View {
    @ObservedObject var model: RemoteModel
    @Environment(\.scenePhase) private var scene
    @State private var pairingLink = ""
    @State private var settings = false
    @State private var search = ""
    var body: some View {
        NavigationStack {
            Group {
                if model.connection == nil { RemotePairView(model: model, link: $pairingLink) }
                else { chats }
            }
            .navigationTitle(model.connection == nil ? "" : "Proto-Mind")
            .toolbar {
                if model.connection != nil {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button { settings = true } label: { Image(systemName: "slider.horizontal.3") }
                            .accessibilityLabel(R("Подключение", "Connection"))
                    }
                }
            }
            .navigationDestination(item: $model.selected) { id in RemoteChatView(model: model, id: id) }
        }
        .sheet(isPresented: $settings) { RemoteConnectionView(model: model) }
        .task(id: scene == .active) {
            guard scene == .active else { return }
            while !Task.isCancelled {
                await model.refresh()
                do { try await Task.sleep(for: .seconds(model.selected == nil ? 4 : 2)) } catch { return }
            }
        }
        .onOpenURL { url in if model.connection == nil { pairingLink = url.absoluteString } }
    }
    private var chats: some View {
        List {
            Section {
                HStack(spacing: 10) {
                    Image(systemName: model.connected ? "desktopcomputer" : "wifi.slash").foregroundStyle(model.connected ? .cyan : .secondary)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(model.waitingForApproval ? R("Подтвердите на Mac", "Approve on your Mac") : model.connected ? R("На связи с Mac", "Connected to your Mac") : R("Ожидаем Mac", "Waiting for your Mac")).font(.subheadline.weight(.medium))
                        Text(model.waitingForApproval ? R("Настройки PM → Подключения → iPhone", "PM Settings → Connections → iPhone") : R("Задачи продолжаются, даже когда вы закрываете приложение", "Tasks keep running when you close this app"))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }.padding(.vertical, 6)
            }
            if let error = model.error { Section { Text(error).font(.callout).foregroundStyle(.orange) } }
            let filtered = model.chats.filter { search.isEmpty || ($0.title + " " + $0.projectName).localizedCaseInsensitiveContains(search) }
            let groups = Dictionary(grouping: filtered, by: \.projectID)
            ForEach(groups.keys.sorted { (groups[$0]?.first?.projectName ?? "") < (groups[$1]?.first?.projectName ?? "") }, id: \.self) { key in
                Section(groups[key]?.first?.projectName ?? "") {
                    ForEach(groups[key] ?? []) { chat in
                        Button { model.selected = chat.id } label: {
                            HStack(spacing: 12) {
                                VStack(alignment: .leading, spacing: 6) {
                                    Text(chat.title).font(.body).foregroundStyle(.primary).lineLimit(2)
                                    Text(chat.model.isEmpty ? chat.provider : chat.model).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                                }
                                Spacer(minLength: 8)
                                if chat.status == "running" { ProgressView().controlSize(.small) }
                                else { Image(systemName: chat.status == "needs_attention" ? "exclamationmark.circle" : "chevron.right").font(.caption).foregroundStyle(.secondary) }
                            }.padding(.vertical, 5)
                        }
                    }
                }
            }
            if filtered.isEmpty && !model.waitingForApproval {
                ContentUnavailableView(R("Здесь будут ваши чаты", "Your chats will appear here"), systemImage: "bubble.left.and.bubble.right",
                    description: Text(R("В PM на Mac откройте настройки iPhone и выберите чаты, которыми хотите управлять.", "Open iPhone settings in PM on your Mac and choose which chats to share.")))
                    .listRowBackground(Color.clear)
            }
        }.listStyle(.insetGrouped)
            .searchable(text: $search, prompt: R("Проект или чат", "Project or chat"))
            .refreshable { await model.refresh() }
    }
}

struct RemotePairView: View {
    @ObservedObject var model: RemoteModel
    @Binding var link: String
    @State private var scan = false
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Image(systemName: "cube.transparent.fill").font(.system(size: 62, weight: .light)).foregroundStyle(.cyan).padding(.top, 32)
                VStack(alignment: .leading, spacing: 12) {
                    Text(R("Ваш Mac.\nВаша команда.\nВсегда рядом.", "Your Mac.\nYour team.\nWithin reach.")).font(.largeTitle.bold())
                    Text(R("Управляйте чатами Proto-Mind с iPhone. Модели и задачи работают на вашем Mac.", "Manage Proto-Mind conversations from your iPhone. Models and tasks run on your Mac."))
                        .font(.body).foregroundStyle(.secondary)
                }
                VStack(alignment: .leading, spacing: 12) {
                    Label(R("Подключите Tailscale на обоих устройствах", "Connect Tailscale on both devices"), systemImage: "network")
                    Label(R("На Mac: Настройки → Подключения → iPhone", "On your Mac: Settings → Connections → iPhone"), systemImage: "desktopcomputer")
                    Label(R("Сканируйте код и подтвердите телефон на Mac", "Scan the code and approve your phone on your Mac"), systemImage: "qrcode.viewfinder")
                }.font(.subheadline).foregroundStyle(.secondary)
                Button { scan = true } label: { Label(R("Сканировать QR-код", "Scan QR code"), systemImage: "qrcode.viewfinder").frame(maxWidth: .infinity).padding(.vertical, 6) }
                    .buttonStyle(.borderedProminent).controlSize(.large)
                DisclosureGroup(R("Или вставьте ссылку подключения", "Or paste a pairing link")) {
                    TextField("protomind-remote://…", text: $link, axis: .vertical)
                        .textInputAutocapitalization(.never).autocorrectionDisabled().lineLimit(2...4).textFieldStyle(.roundedBorder)
                    PasteButton(payloadType: String.self) { strings in link = strings.first ?? "" }
                }.font(.subheadline)
                if !link.isEmpty {
                    Button(R("Подключиться", "Connect")) {
                        Task { if let token = try? RemoteStorage.token() { await model.pair(link, name: UIDevice.current.name, token: token) }; link = "" }
                    }.buttonStyle(.borderedProminent).disabled(model.busy)
                }
                if let error = model.error { Text(error).font(.callout).foregroundStyle(.orange) }
            }.padding(28).frame(maxWidth: 560)
        }.sheet(isPresented: $scan) {
            RemoteQRScanner { result in link = result; scan = false }
                .ignoresSafeArea().overlay(alignment: .topTrailing) {
                    Button(R("Закрыть", "Close")) { scan = false }.buttonStyle(.borderedProminent).padding()
                }
        }
    }
}

struct RemoteConnectionView: View {
    @ObservedObject var model: RemoteModel
    @Environment(\.dismiss) private var dismiss
    @State private var confirm = false
    var body: some View {
        NavigationStack {
            Form {
                Section(R("Ваш Mac", "Your Mac")) {
                    Text(model.connection?.endpoint ?? "").font(.callout).textSelection(.enabled)
                    Label(model.connected ? R("Подключён", "Connected") : R("Нет связи", "Not connected"), systemImage: model.connected ? "checkmark.circle" : "wifi.slash")
                    Text(R("Mac должен бодрствовать, PM и подключение iPhone должны быть включены. Закрытие этого приложения не останавливает задачи.", "Keep your Mac awake, PM open, and the iPhone connection enabled. Closing this app does not stop tasks."))
                        .font(.caption).foregroundStyle(.secondary)
                    Button(R("Обновить подключение", "Refresh connection")) { Task { await model.refresh() } }
                }
                Section {
                    Text(R("Переписка и права на задачи определяются выбранными чатами на Mac. Новому чату нужно отдельно выдать полный доступ на Mac.", "Conversation access and task permissions come from the chats you share on your Mac. Grant full access to a new chat separately on your Mac."))
                        .font(.caption).foregroundStyle(.secondary)
                    Button(R("Отключить этот iPhone", "Disconnect this iPhone"), role: .destructive) { confirm = true }.disabled(model.busy)
                }
                Section { Text("PM Remote · 0.1.0").foregroundStyle(.secondary) }
            }.navigationTitle(R("Подключение", "Connection"))
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button(R("Готово", "Done")) { dismiss() } } }
                .confirmationDialog(R("Удалить подключение и черновики с iPhone?", "Remove this connection and iPhone drafts?"), isPresented: $confirm, titleVisibility: .visible) {
                    Button(R("Отключить", "Disconnect"), role: .destructive) { model.disconnect(); if model.connection == nil { dismiss() } }
                } message: { Text(R("Чаты и принятые задачи на Mac сохранятся. Для отзыва доступа также удалите этот iPhone в настройках PM на Mac.", "Chats and accepted tasks stay on your Mac. Also remove this iPhone from PM settings on your Mac to revoke access.")) }
        }
    }
}
