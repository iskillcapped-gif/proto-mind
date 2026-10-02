import AppKit
import CoreImage.CIFilterBuiltins
import SwiftUI

struct MobileRemoteSettings: View {
    @ObservedObject var app: AppModel
    @ObservedObject var remote: MobileRemoteModel
    @State private var endpoint = ""
    @State private var showSetup = false
    var body: some View {
        Section {
            HStack {
                TextField(L10n.pick("Адрес Mac", "Mac address"), text: $endpoint, prompt: Text(verbatim: "https://your-mac.your-tailnet.ts.net"))
                    .textFieldStyle(.roundedBorder).labelsHidden().disabled(remote.running || remote.connecting)
                    .accessibilityLabel(L10n.pick("Защищённый адрес Mac", "Secure Mac address"))
                Button(L10n.text("Сохранить")) { act { try remote.setEndpoint(endpoint) } }
                    .disabled(remote.running || remote.connecting || MobileWire.endpoint(endpoint) == nil || endpoint == remote.state.endpoint)
            }
            DisclosureGroup(L10n.pick("Как подключить", "Connection setup"), isExpanded: $showSetup) {
                VStack(alignment: .leading, spacing: 8) {
                    Text(L10n.pick("1. Установите Tailscale на Mac и iPhone и войдите в один аккаунт.\n2. На Mac включите частный HTTPS-адрес командой ниже и вставьте выданный адрес в поле выше.\n3. Включите подключение, выберите чаты и отсканируйте QR-код в PM Remote.\n4. Подтвердите свой телефон здесь.", "1. Install Tailscale on your Mac and iPhone and sign in to the same account.\n2. Enable a private HTTPS address on your Mac with the command below, then paste the address above.\n3. Enable the connection, share chats, and scan the QR code in PM Remote.\n4. Approve your phone here."))
                    Text("tailscale serve --bg 8765").font(.callout.monospaced()).textSelection(.enabled)
                    Text(L10n.pick("Используйте частный Serve, без публичного Funnel. Сервер PM принимает соединения только с этого Mac. После перезапуска PM подключение нужно включить снова.", "Use private Serve, without public Funnel. The PM server accepts connections only from this Mac. Enable the connection again after restarting PM."))
                        .foregroundStyle(.secondary)
                    Link(L10n.pick("Инструкция Tailscale Serve", "Tailscale Serve guide"), destination: URL(string: "https://tailscale.com/docs/features/tailscale-serve")!)
                }.font(.caption).padding(.vertical, 6)
            }
        } header: { Text(L10n.pick("Адрес Mac", "Mac address")) } footer: {
            Text(L10n.pick("Ваши проекты и чаты — с телефона. Читайте ответы, отправляйте задачи и уточнения, останавливайте работу. PM должен быть открыт, а Mac — бодрствовать.", "Your projects and chats, on your phone. Read replies, send tasks and updates, and stop work. PM must be open and your Mac awake."))
                .font(.caption).foregroundStyle(.secondary)
        }.onAppear { endpoint = remote.state.endpoint }
        Section {
            Toggle(L10n.pick("Принимать команды из PM Remote", "Accept commands from PM Remote"), isOn: Binding(
                get: { remote.running || remote.connecting }, set: { value in
                    if value { act { try remote.start(app: app) } } else { remote.stop() }
                }))
                .disabled(!remote.running && (remote.state.endpoint.isEmpty || app.operationBusy || app.privateBackupRestartRequired))
            Label(remote.running ? L10n.pick("Подключение включено", "Connection enabled") : remote.connecting ? L10n.pick("Подключаем…", "Connecting…") : L10n.pick("Подключение выключено", "Connection off"),
                  systemImage: remote.running ? "checkmark.circle.fill" : "iphone")
                .font(.caption).foregroundStyle(.secondary)
            if let pending = remote.pending {
                VStack(alignment: .leading, spacing: 8) {
                    Text(L10n.pick("Запрос на подключение: ", "Pairing request: ") + pending.name).font(.headline)
                    Text(L10n.pick("Подтверждайте только свой телефон. Он получит доступ к выбранным ниже чатам и их текущим разрешениям.", "Approve only your own phone. It will have access to the chats selected below and their current permissions."))
                        .font(.caption).foregroundStyle(.secondary)
                    HStack {
                        Spacer()
                        Button(L10n.pick("Отклонить", "Reject")) { act { try remote.beginPairing() } }
                        Button(L10n.pick("Разрешить этому iPhone", "Approve this iPhone")) { act { try remote.approve() } }
                            .buttonStyle(.borderedProminent)
                    }
                }
            } else if remote.running {
                if let pairing = remote.pairing, let link = pairing.link {
                    HStack(alignment: .top, spacing: 16) {
                        if let image = Self.qr(link) {
                            Image(nsImage: image).interpolation(.none).resizable().frame(width: 176, height: 176)
                                .padding(8).background(.white, in: RoundedRectangle(cornerRadius: 12))
                                .accessibilityLabel(L10n.pick("QR-код подключения", "Pairing QR code"))
                        }
                        VStack(alignment: .leading, spacing: 8) {
                            Text(L10n.pick("Откройте PM Remote на iPhone и отсканируйте код. Ссылка одноразовая, действует 10 минут.", "Open PM Remote on your iPhone and scan the code. The link can be used once and expires in 10 minutes."))
                                .font(.caption).foregroundStyle(.secondary)
                            Button(L10n.pick("Скопировать ссылку", "Copy pairing link")) {
                                NSPasteboard.general.clearContents(); NSPasteboard.general.setString(link, forType: .string)
                            }
                            Button(L10n.pick("Новый код", "New code")) { act { try remote.beginPairing() } }
                        }
                    }.padding(.vertical, 6)
                } else {
                    HStack {
                        Spacer()
                        Button(L10n.pick("Подключить iPhone", "Pair an iPhone")) { act { try remote.beginPairing() } }
                            .buttonStyle(.borderedProminent).disabled(remote.state.devices.count >= 8)
                    }
                }
            }
        } header: { Text(L10n.pick("Подключение", "Connection")) }
        if !remote.state.devices.isEmpty {
            Section {
                ForEach(remote.state.devices) { device in
                    HStack(spacing: 10) {
                        Image(systemName: "iphone").font(.system(size: 15)).foregroundStyle(.secondary).frame(width: 20).accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(device.name)
                            Text(L10n.pick("Подключён ", "Paired ") + device.pairedAt.formatted(.dateTime.day().month(.abbreviated).hour().minute().locale(L10n.locale)))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer(minLength: 8)
                        Button(L10n.pick("Отвязать", "Unpair")) { act { try remote.revoke(device.id) } }
                    }
                }
            } header: { Text(L10n.pick("Устройства", "Devices")) }
        }
        Section {
            DisclosureGroup(L10n.pick("Доступные чаты", "Shared chats") + " · \(remote.state.allowed.count)") {
                Text(L10n.pick("Телефон сможет читать переписку и запускать задачи с уже выданными этому чату правами, включая доступ к Mac. Новые чаты с телефона начинают без полного доступа. Закрытие приложения на iPhone не останавливает принятые задачи.", "Your phone can read conversations and run tasks with permissions already granted to each chat, including Mac access. Chats created on your phone start without full access. Closing the iPhone app does not stop accepted tasks."))
                    .font(.caption).foregroundStyle(.secondary)
                ForEach(app.listedConversations.filter { !$0.archived }) { chat in
                    Toggle(isOn: Binding(get: { remote.state.allowed.contains(chat.id) },
                        set: { enabled in act { try remote.allow(chat.id, enabled: enabled) } })) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(chat.displayTitle).lineLimit(1)
                            if let path = chat.workspacePath { Text(URL(fileURLWithPath: path).lastPathComponent).font(.caption).foregroundStyle(.secondary) }
                        }
                    }
                }
            }
            if let error = remote.error { Text(error).font(.caption).foregroundStyle(.orange).textSelection(.enabled) }
        }
    }
    private func act(_ operation: () throws -> Void) {
        do { try operation(); remote.error = nil } catch { remote.error = error.localizedDescription }
    }
    private static func qr(_ value: String) -> NSImage? {
        let filter = CIFilter.qrCodeGenerator(); filter.message = Data(value.utf8); filter.correctionLevel = "M"
        guard let output = filter.outputImage?.transformed(by: CGAffineTransform(scaleX: 6, y: 6)),
              let image = CIContext().createCGImage(output, from: output.extent) else { return nil }
        return NSImage(cgImage: image, size: NSSize(width: output.extent.width, height: output.extent.height))
    }
}
