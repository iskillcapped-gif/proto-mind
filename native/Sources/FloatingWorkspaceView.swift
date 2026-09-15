import AppKit
import SwiftUI

private struct DesktopGlassKey: EnvironmentKey { static let defaultValue = false }
extension EnvironmentValues {
    var desktopGlass: Bool {
        get { self[DesktopGlassKey.self] }
        set { self[DesktopGlassKey.self] = newValue }
    }
}

struct FloatingWorkspaceView: View {
    @ObservedObject var app: AppModel
    @ObservedObject var desktop: DesktopPresentation
    @Environment(\.openSettings) private var openSettings
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @State private var conversationsOpen = false

    var body: some View {
        VStack(spacing: 0) {
            header
            Rectangle().fill(Color.primary.opacity(0.07)).frame(height: 1).padding(.horizontal, 20)
            HistoryPersistenceNotice(model: app)
            if let error = app.error, error != app.historyPersistence.failure {
                HStack(alignment: .top) {
                    Image(systemName: "exclamationmark.circle").foregroundStyle(.orange)
                    Text(error).font(.callout).textSelection(.enabled)
                    Spacer()
                    Button { app.clearError() } label: { Image(systemName: "xmark") }
                }.padding(14).background(Color.orange.opacity(0.08))
            }
            WorkspaceSplitView(model: app, panel: app.workspacePanel)
        }
        .environment(\.desktopGlass, true)
        .background {
            if reduceTransparency { NativeTheme.canvas }
            else {
                DesktopGlassMaterial()
                NativeTheme.canvas.opacity(0.66)
                LinearGradient(colors: [Color.white.opacity(0.055), .clear, Color.teal.opacity(0.025)], startPoint: .topLeading, endPoint: .bottomTrailing)
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: 26, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 26, style: .continuous)
                .strokeBorder(LinearGradient(colors: [.white.opacity(0.25), .white.opacity(0.04), .white.opacity(0.12)], startPoint: .topLeading, endPoint: .bottomTrailing), lineWidth: 1)
                .allowsHitTesting(false)
        }
        .ignoresSafeArea()
        .toolbar(.hidden, for: .windowToolbar)
        .onExitCommand { desktop.collapse() }
    }

    private var header: some View {
        HStack(spacing: 8) {
            CubeEmblem().frame(width: 25, height: 29).padding(.trailing, 5)
            Button { conversationsOpen.toggle() } label: {
                VStack(alignment: .leading, spacing: 3) {
                    Text("Proto-Mind").font(.system(size: 12, weight: .semibold))
                    HStack(spacing: 5) {
                        Text(app.selected?.title ?? "Новый диалог").lineLimit(1)
                        Image(systemName: "chevron.down").font(.system(size: 8, weight: .semibold))
                    }.font(.system(size: 11)).foregroundStyle(.secondary)
                }.frame(maxWidth: 260, alignment: .leading).contentShape(Rectangle())
            }.buttonStyle(.nativeHover).help("Переключить диалог").accessibilityLabel("Диалоги")
                .popover(isPresented: $conversationsOpen, arrowEdge: .bottom) { conversationPicker }
            // Only the empty header area drags the window; buttons and text keep their own input.
            DesktopWindowDragArea().frame(height: 36).frame(maxWidth: .infinity)
            headerButton("Новый диалог", icon: "square.and.pencil") { app.newConversation(); app.section = .chat }
                .disabled(!app.canNavigateConversations)
            headerButton("Файлы и браузер", icon: "sidebar.right") {
                app.workspacePanel.visible.toggle(); app.workspacePanel.expanded = false
                if app.workspacePanel.visible && app.workspacePanel.selectedID == nil { Task { await app.refreshWorkspace() } }
            }
            Menu {
                Button("Журнал работы") { app.openWorkSessions() }
                Button("Лимиты Codex") { app.showCodexUsage = true }
                Button("Настройки") { openSettings() }
                Divider()
                Button("Обычное окно") { desktop.restoreWindow() }
            } label: { Image(systemName: "ellipsis").frame(width: 28, height: 30) }
                .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize().help("Меню")
            headerButton("Обычное окно", icon: "arrow.up.left.and.arrow.down.right") { desktop.restoreWindow() }
            headerButton("Свернуть в ядро · Esc", icon: "minus") { desktop.collapse() }
                .accessibilityLabel("Свернуть в ядро")
        }.padding(.horizontal, 20).padding(.vertical, 14)
    }

    private func headerButton(_ title: String, icon: String, action: @escaping () -> Void) -> some View {
        Button(action: action) { Image(systemName: icon).font(.system(size: 13)).frame(width: 28, height: 30) }
            .buttonStyle(.nativeHover).foregroundStyle(.secondary).help(title).accessibilityLabel(title)
    }

    private var conversationPicker: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Диалоги").font(.system(size: 14, weight: .semibold))
                Spacer()
                Button("История") { conversationsOpen = false; app.showConversationHistory = true }
            }.padding(.horizontal, 10).padding(.top, 8)
            ScrollView {
                LazyVStack(spacing: 2) {
                    ForEach(app.conversations.filter { !$0.archived }.prefix(40)) { conversation in
                        Button {
                            app.select(conversation.id); app.section = .chat; conversationsOpen = false
                        } label: {
                            HStack(spacing: 10) {
                                Image(systemName: conversation.workspacePath == nil ? "bubble.left" : "folder").foregroundStyle(.secondary)
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(conversation.title).font(.system(size: 13)).lineLimit(1)
                                    if let path = conversation.workspacePath {
                                        Text(URL(fileURLWithPath: path).lastPathComponent).font(.system(size: 11)).foregroundStyle(.secondary)
                                    }
                                }
                                Spacer()
                                if app.isRunning(conversation.id) { ProgressView().controlSize(.mini) }
                                else if app.selectedID == conversation.id { Image(systemName: "checkmark").font(.system(size: 11)) }
                            }.padding(10).contentShape(Rectangle())
                        }.buttonStyle(.nativeHover).disabled(!app.canNavigateConversations)
                    }
                }
            }.frame(maxHeight: 360)
        }.padding(8).frame(width: 330)
    }
}

struct FloatingWelcomeView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            CubeEmblem().frame(width: 44, height: 51).padding(.bottom, 8)
            Text("Я рядом.").font(.system(size: 30, weight: .medium))
            Text("Продолжим работу или начнём с новой идеи?")
                .font(.system(size: 15)).foregroundStyle(.secondary)
            HStack(spacing: 7) {
                Image(systemName: "waveform")
                Text("Можно написать или включить голос")
            }.font(.system(size: 11)).foregroundStyle(.tertiary).padding(.top, 5)
        }.frame(maxWidth: .infinity, alignment: .leading).padding(.vertical, 28).padding(.horizontal, 24)
    }
}

struct DesktopCoreView: View {
    @ObservedObject var app: AppModel
    @ObservedObject var voice: LiveVoiceModel
    @ObservedObject var desktop: DesktopPresentation
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var working: Bool { app.executions.values.contains { $0.running } }
    private var active: Bool { working || voice.inCall }
    private var voiceLevel: Double { max(voice.inputLevel, voice.outputLevel) }
    private var statusIcon: String {
        if voice.connected { return voice.muted ? "mic.slash.fill" : "mic.fill" }
        if voice.inCall { return "ellipsis" }
        if working { return "ellipsis" }
        return "mic.slash"
    }

    var body: some View {
        VStack(spacing: 6) {
            ZStack {
                Ellipse().fill(Color.teal.opacity(active ? 0.18 : 0.07)).frame(width: 57, height: 29).blur(radius: 10).offset(y: 27)
                if working {
                    TimelineView(.animation(minimumInterval: 1 / 20, paused: reduceMotion)) { context in
                        let angle = reduceMotion ? 0 : context.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 3) / 3 * 360
                        Circle().trim(from: 0.05, to: 0.75).stroke(AngularGradient(colors: [.clear, .teal.opacity(0.3), .white.opacity(0.8)], center: .center), style: StrokeStyle(lineWidth: 1.5, lineCap: .round))
                            .frame(width: 72, height: 72).rotationEffect(.degrees(angle))
                    }
                }
                CubeEmblem().frame(width: 51, height: 60)
                    .shadow(color: Color.teal.opacity(voice.connected ? 0.16 + voiceLevel * 0.5 : 0.1), radius: 8)
                    .scaleEffect(reduceMotion ? 1 : 1 + voiceLevel * 0.045)
                    .animation(reduceMotion ? nil : .easeOut(duration: 0.1), value: voiceLevel)
            }.frame(width: 80, height: 78)
            HStack(spacing: 4) {
                Image(systemName: statusIcon).font(.system(size: 8, weight: .medium))
                if voice.connected && !voice.muted {
                    ForEach(0..<3) { index in
                        Capsule().frame(width: 2, height: 3 + voice.inputLevel * Double(index == 1 ? 8 : 5))
                    }
                }
            }.foregroundStyle(voice.connected && !voice.muted ? Color.teal : Color.secondary)
                .padding(.horizontal, 7).frame(height: 16)
                .background(.regularMaterial, in: Capsule())
        }.frame(width: 88, height: 108)
            .help(voice.connected ? (voice.muted ? "Микрофон выключен" : "Голос включён")
                  : voice.inCall ? (voice.phase == .connecting ? "Подключение голоса…" : "Завершение разговора…") : "Proto-Mind · микрофон выключен")
    }
}

/// A vector counterpart of the app's cube, crisp at small desktop sizes.
struct CubeEmblem: View {
    var body: some View {
        Canvas { context, size in
            let sx = size.width / 100, sy = size.height / 114
            func path(_ points: [CGPoint], close: Bool = true) -> Path {
                var result = Path()
                for (index, point) in points.enumerated() {
                    let point = CGPoint(x: point.x * sx, y: point.y * sy)
                    if index == 0 { result.move(to: point) } else { result.addLine(to: point) }
                }
                if close { result.closeSubpath() }
                return result
            }
            let top = path([CGPoint(x: 50, y: 3), CGPoint(x: 94, y: 28), CGPoint(x: 50, y: 53), CGPoint(x: 6, y: 28)])
            let left = path([CGPoint(x: 6, y: 33), CGPoint(x: 47, y: 57), CGPoint(x: 47, y: 108), CGPoint(x: 6, y: 84)])
            let right = path([CGPoint(x: 53, y: 57), CGPoint(x: 94, y: 33), CGPoint(x: 94, y: 84), CGPoint(x: 53, y: 108)])
            context.fill(top, with: .linearGradient(Gradient(colors: [Color(red: 0.88, green: 0.99, blue: 0.97), Color(red: 0.47, green: 0.79, blue: 0.77)]), startPoint: .zero, endPoint: CGPoint(x: size.width, y: size.height * 0.5)))
            context.fill(left, with: .linearGradient(Gradient(colors: [Color(red: 0.24, green: 0.5, blue: 0.49), Color(red: 0.10, green: 0.23, blue: 0.26)]), startPoint: .zero, endPoint: CGPoint(x: size.width * 0.5, y: size.height)))
            context.fill(right, with: .linearGradient(Gradient(colors: [Color(red: 0.35, green: 0.63, blue: 0.61), Color(red: 0.12, green: 0.3, blue: 0.31)]), startPoint: CGPoint(x: size.width, y: 0), endPoint: CGPoint(x: size.width * 0.5, y: size.height)))
            for face in [top, left, right] { context.stroke(face, with: .color(.white.opacity(0.3)), lineWidth: max(0.5, sx)) }
            let ink = Color(red: 0.05, green: 0.17, blue: 0.2)
            context.stroke(path([CGPoint(x: 59, y: 17), CGPoint(x: 39, y: 28), CGPoint(x: 59, y: 39)], close: false), with: .color(ink), style: StrokeStyle(lineWidth: 5 * sx, lineCap: .round, lineJoin: .round))
            for points in [[CGPoint(x: 19, y: 50), CGPoint(x: 19, y: 75), CGPoint(x: 35, y: 84)],
                           [CGPoint(x: 81, y: 50), CGPoint(x: 81, y: 75), CGPoint(x: 65, y: 84)]] {
                context.stroke(path(points, close: false), with: .color(.white.opacity(0.83)), style: StrokeStyle(lineWidth: 4.5 * sx, lineCap: .round, lineJoin: .round))
            }
        }.accessibilityHidden(true)
    }
}

private struct DesktopGlassMaterial: NSViewRepresentable {
    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = .hudWindow; view.blendingMode = .behindWindow; view.state = .active
        return view
    }
    func updateNSView(_ view: NSVisualEffectView, context: Context) {}
}

private struct DesktopWindowDragArea: NSViewRepresentable {
    func makeNSView(context: Context) -> DragArea { DragArea() }
    func updateNSView(_ view: DragArea, context: Context) {}
    final class DragArea: NSView {
        override var mouseDownCanMoveWindow: Bool { true }
        override func mouseDown(with event: NSEvent) { window?.performDrag(with: event) }
    }
}
