import AppKit
import CryptoKit
import SwiftUI
import WebKit

enum MessengerService: String, CaseIterable, Identifiable {
    case telegram, whatsapp
    var id: String { rawValue }
    var title: String { self == .telegram ? "Telegram" : "WhatsApp" }
    var url: URL { URL(string: self == .telegram ? "https://web.telegram.org/a/" : "https://web.whatsapp.com/")! }
    func accepts(_ url: URL) -> Bool {
        url.scheme == "https" && url.user == nil && url.password == nil && url.host == self.url.host
    }
    func storeID(profile: URL) -> UUID {
        let bytes = Array(SHA256.hash(data: Data((profile.standardizedFileURL.path + ":messenger:" + rawValue).utf8)).prefix(16))
        return UUID(uuid: (bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5], bytes[6], bytes[7],
                           bytes[8], bytes[9], bytes[10], bytes[11], bytes[12], bytes[13], bytes[14], bytes[15]))
    }
}

@MainActor
final class MessengerConnections: ObservableObject {
    let profile: URL
    @Published private(set) var clearing: Set<MessengerService> = []
    init(profile: URL) { self.profile = profile }
    func store(_ service: MessengerService) -> WKWebsiteDataStore {
        WKWebsiteDataStore(forIdentifier: service.storeID(profile: profile))
    }
    func clear(_ service: MessengerService, app: AppModel) async {
        guard clearing.insert(service).inserted else { return }
        defer { clearing.remove(service) }
        for panel in app.allWorkspacePanels {
            let ids = panel.tabs.compactMap { tab -> UUID? in
                if case .browser(let browser) = tab.content, browser.messenger == service { return tab.id }
                return nil
            }
            ids.forEach { panel.close($0) }
        }
        await store(service).removeData(ofTypes: WKWebsiteDataStore.allWebsiteDataTypes(), modifiedSince: .distantPast)
    }
}

extension AppModel {
    var allWorkspacePanels: [WorkspacePanelModel] {
        [workspacePanels.upper, workspacePanels.lower] + desktop.companions.surfaces.map(\.panel)
    }
    func openMessenger(_ service: MessengerService, in destination: WorkspacePanelModel? = nil) {
        guard !messengers.clearing.contains(service) else { return }
        let panel: WorkspacePanelModel
        if let destination { panel = destination }
        else if desktop.enabled {
            let surface = desktop.companions.surface(.first)
            if !surface.visible { desktop.companions.toggle(.first) }
            panel = surface.panel
        } else { panel = workspacePanel }
        if let existing = panel.tabs.first(where: {
            if case .browser(let browser) = $0.content { return browser.messenger == service }; return false
        }) { panel.visible = true; panel.selectedID = existing.id; return }
        let browser = NativeBrowserTab(store: messengers.store(service), messenger: service)
        guard panel.open(.browser(browser)) != nil else { return }
        browser.openTab = { [weak panel, weak browser] url in
            if service.accepts(url) { browser?.navigate(url.absoluteString) }
            else { panel?.openBrowser(url) }
        }
        browser.navigate(service.url.absoluteString)
    }
}

struct MessengerSettings: View {
    @ObservedObject var app: AppModel
    @ObservedObject var connections: MessengerConnections
    @Environment(\.workspacePresentations) private var presentations
    @WorkspaceDismiss private var dismiss
    @State private var reset: MessengerService?
    var body: some View {
        Section {
            ForEach(MessengerService.allCases) { service in
                HStack(spacing: 10) {
                    RoundedRectangle(cornerRadius: 6, style: .continuous).fill((service == .telegram ? Color(red: 0.16, green: 0.62, blue: 0.9) : Color.green).gradient)
                        .frame(width: 24, height: 24)
                        .overlay(Image(systemName: service == .telegram ? "paperplane.fill" : "phone.fill").font(.system(size: 11, weight: .semibold)).foregroundStyle(.white))
                        .accessibilityHidden(true)
                    Text(service.title)
                    Spacer()
                    if connections.clearing.contains(service) { ProgressView().controlSize(.small) }
                    Button(L10n.pick("Открыть", "Open")) {
                        guard presentations?.locked != true else { return }
                        let panel = app.allWorkspacePanels.first { $0.presentations === presentations && presentations != nil }
                        dismiss()
                        app.openMessenger(service, in: panel)
                    }
                    SettingsMoreMenu {
                        Button(L10n.pick("Сбросить вход…", "Reset sign-in…"), role: .destructive) { reset = service }
                    }
                }.disabled(connections.clearing.contains(service))
                    .contextMenu { Button(L10n.pick("Сбросить вход…", "Reset sign-in…"), role: .destructive) { reset = service } }
            }
        } header: { Text(L10n.pick("Сервисы", "Services")) } footer: {
            Text(L10n.pick("Вход сохраняется на этом Mac отдельно для каждого сервиса. Выделите сообщения и нажмите «В задачу», чтобы обсудить их с PM. Звонки и системные уведомления пока не поддерживаются; для скачивания файлов используйте внешний браузер.", "Sign-in stays on this Mac separately for each service. Select messages and choose Use in a task to discuss them with PM. Calls and system notifications are not supported yet; use your external browser for downloads."))
                .font(.caption).foregroundStyle(.secondary)
        }.workspaceConfirmationDialog(L10n.pick("Сбросить вход на этом Mac?", "Reset sign-in on this Mac?"),
            isPresented: Binding(get: { reset != nil }, set: { if !$0 { reset = nil } }), titleVisibility: .visible) {
                Button(L10n.pick("Сбросить вход", "Reset sign-in"), role: .destructive) {
                    guard let service = reset else { return }; reset = nil
                    Task { await connections.clear(service, app: app) }
                }
                Button(L10n.text("Отмена"), role: .cancel) { reset = nil }
            } message: {
                Text(L10n.pick("Вкладки этого мессенджера закроются. Переписка в самом сервисе останется; для нового входа потребуется телефон.", "This messenger's tabs will close. Your messages remain in the service; signing in again requires your phone."))
            }
    }
}
