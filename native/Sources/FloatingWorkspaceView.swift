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
    private func openSettings() { app.openSettings() }
    @State private var libraryExpanded = false

    var body: some View {
        GeometryReader { geometry in
            HStack(spacing: 10) {
                SidebarView(model: app, libraryExpanded: $libraryExpanded, openSettings: { openSettings() })
                    .frame(width: DesktopGeometry.sidebarWidth(total: geometry.size.width))
                    .background(DesktopGlassBackground(transparency: desktop.sidebarTransparency, tint: NativeTheme.sidebar))
                    .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
                    .overlay(glassBorder(radius: 22))
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
                    WorkspaceContentHost(app: app, presentations: app.presentations)
                }
                .background(DesktopGlassBackground(transparency: desktop.chatTransparency, tint: NativeTheme.canvas))
                .clipShape(RoundedRectangle(cornerRadius: 26, style: .continuous))
                .overlay(glassBorder(radius: 26))
            }
        }
        .background(DesktopWorkspaceHoverRegion(desktop: desktop))
        .environment(\.desktopGlass, true)
        .ignoresSafeArea()
        .toolbar(.hidden, for: .windowToolbar)
        .onChange(of: app.section) { _, next in if next.libraryCollection != nil { libraryExpanded = true } }
        .onExitCommand { if app.presentations.pages.isEmpty { desktop.collapse() } else { app.presentations.dismissTop() } }
    }

    private func glassBorder(radius: CGFloat) -> some View {
        RoundedRectangle(cornerRadius: radius, style: .continuous)
            .strokeBorder(LinearGradient(colors: [.white.opacity(0.25), .white.opacity(0.04), .white.opacity(0.12)],
                                         startPoint: .topLeading, endPoint: .bottomTrailing), lineWidth: 1)
            .allowsHitTesting(false)
    }

    private var header: some View {
        HStack(spacing: 8) {
            Text(app.selected?.displayTitle ?? L10n.text("Новый диалог"))
                .font(.system(size: 13, weight: .medium)).lineLimit(1)
                .frame(maxWidth: 260, alignment: .leading)
            // Only the empty header area drags the window; buttons and text keep their own input.
            DesktopWindowDragArea().frame(height: 36).frame(maxWidth: .infinity)
            headerButton(L10n.text("Рабочие панели"), icon: "rectangle.split.2x2") { app.workspacePanels.toggle() }
            headerButton(L10n.text("Свернуть в ядро · Esc"), icon: "minus") { desktop.collapse() }
                .accessibilityLabel(L10n.text("Свернуть в ядро"))
        }.padding(.horizontal, 20).padding(.vertical, 14)
    }

    private func headerButton(_ title: String, icon: String, action: @escaping () -> Void) -> some View {
        Button(action: action) { Image(systemName: icon).font(.system(size: 13)).frame(width: 28, height: 30) }
            .buttonStyle(.nativeHover).foregroundStyle(.secondary).help(title).accessibilityLabel(title)
    }

}

struct FloatingWelcomeView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            CubeEmblem().frame(width: 44, height: 51).padding(.bottom, 8)
            Text(L10n.text("Я рядом.")).font(.system(size: 30, weight: .medium))
            Text(L10n.text("Продолжим работу или начнём с новой идеи?"))
                .font(.system(size: 15)).foregroundStyle(.secondary)
            HStack(spacing: 7) {
                Image(systemName: "waveform")
                Text(L10n.text("Можно написать или включить голос"))
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
    var body: some View {
        HStack(spacing: 4) {
            // Small controls; their groups keep the former slots, so the cube itself never moves.
            VStack(spacing: 2) {
                ForEach(DesktopCompanionID.allCases) { id in
                    Button { desktop.companions.toggle(id) } label: {
                        Text(id == .first ? "1" : "2").font(.system(size: 10, weight: .medium))
                            .frame(width: 22, height: 22).contentShape(Rectangle())
                            .background(desktop.companions.surface(id).visible ? Color.teal.opacity(0.22) : .clear, in: RoundedRectangle(cornerRadius: 6))
                    }.buttonStyle(.nativeHover(minSize: 22)).foregroundStyle(.primary)
                        .help(L10n.text("Показать или скрыть · ") + id.title)
                        .accessibilityLabel(L10n.text("Боковое ") + id.title.lowercased())
                        .accessibilityValue(desktop.companions.surface(id).visible ? L10n.text("Показано") : L10n.text("Скрыто"))
                }
            }.padding(2).background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
                .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(.white.opacity(0.15)).allowsHitTesting(false))
                .frame(width: 40, alignment: .trailing)
                .padding(.bottom, 38)
                .opacity(desktop.coreHovered ? 1 : 0).allowsHitTesting(desktop.coreHovered)
                .animation(reduceMotion ? nil : .easeOut(duration: 0.15), value: desktop.coreHovered)
        VStack(spacing: 4) {
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
                if voice.inCall {
                    Circle().fill(voice.connected && !voice.muted ? Color.teal : .secondary)
                        .frame(width: 5, height: 5).offset(x: 25, y: 26)
                }
            }.frame(width: 80, height: 78)
                .overlay(DesktopCoreHandle(desktop: desktop))
                .overlay(alignment: .topTrailing) { CoreResponseBadge(app: app).offset(x: 3, y: -2) }
            HStack(spacing: 1) {
                Button { desktop.openVoice() } label: {
                    Image(systemName: voice.inCall ? (voice.muted ? "mic.slash.fill" : "mic.fill") : "mic")
                        .foregroundStyle(voice.inCall ? Color.teal : .primary)
                        .frame(width: 26, height: 22).contentShape(Rectangle())
                }.help(voice.inCall ? L10n.text("Управление разговором") : L10n.text("Начать голосовой разговор"))
                    .accessibilityLabel(L10n.text("Голос Proto-Mind"))
                Button { desktop.restoreWindow() } label: {
                    Image(systemName: "arrow.up.left.and.arrow.down.right").frame(width: 26, height: 22).contentShape(Rectangle())
                }.help(L10n.text("Обычное окно")).accessibilityLabel(L10n.text("Обычное окно"))
            }.font(.system(size: 10, weight: .medium)).buttonStyle(.nativeHover(minSize: 22, cornerRadius: 11)).padding(2)
                .background(.regularMaterial, in: Capsule())
                .overlay(Capsule().strokeBorder(.white.opacity(0.15)).allowsHitTesting(false))
                .frame(height: 38, alignment: .top)
                .opacity(desktop.coreHovered ? 1 : 0)
                .allowsHitTesting(desktop.coreHovered)
                .animation(reduceMotion ? nil : .easeOut(duration: 0.15), value: desktop.coreHovered)
        }.frame(width: 88, height: DesktopGeometry.coreSize.height)
        }.frame(width: DesktopGeometry.coreSize.width, height: DesktopGeometry.coreSize.height)
            .contentShape(Rectangle())
            .help(voice.connected ? (voice.muted ? L10n.text("Микрофон выключен") : L10n.text("Голос включён"))
                  : voice.inCall ? L10n.text("Подключение или завершение разговора…") : L10n.text("Proto-Mind · микрофон выключен"))
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

struct DesktopGlassBackground: View {
    let transparency: Double
    let tint: Color
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    var body: some View {
        ZStack {
            if reduceTransparency { tint }
            else {
                DesktopGlassMaterial().opacity(1 - transparency)
                tint.opacity(1 - transparency)
                LinearGradient(colors: [.white.opacity(0.045), .clear, .teal.opacity(0.025)],
                               startPoint: .topLeading, endPoint: .bottomTrailing)
                    .opacity(1 - transparency)
            }
        }.allowsHitTesting(false).accessibilityHidden(true)
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

struct DesktopWindowDragArea: NSViewRepresentable {
    func makeNSView(context: Context) -> DragArea { DragArea() }
    func updateNSView(_ view: DragArea, context: Context) {}
    final class DragArea: NSView {
        override var mouseDownCanMoveWindow: Bool { false }
        override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
        override func mouseDown(with event: NSEvent) {
            // WindowServer tracks the pointer and moves the parent/child group.
            // Re-converting queued mouse events through an already moved window
            // feeds its previous movement back into the next frame and causes jumps.
            window?.performDrag(with: event)
        }
    }
}

enum DesktopPointer {
    static func screenLocation(of event: NSEvent, in window: NSWindow?) -> NSPoint {
        // Unlike locationInWindow, this coordinate belongs to the event itself
        // and does not change when a previous drag/resize event moves the window.
        event.cgEvent?.unflippedLocation ?? window?.convertPoint(toScreen: event.locationInWindow) ?? event.locationInWindow
    }
}
