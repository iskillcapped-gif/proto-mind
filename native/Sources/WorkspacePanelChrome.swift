import AppKit
import Combine
import SwiftUI

/// Transient presentation state. Hiding controls never replaces a tab or its content.
@MainActor
final class WorkspacePanelChrome: ObservableObject {
    @Published private(set) var visible = false
    private(set) weak var window: NSWindow?
    private var hovered = false
    private var holds = Set<UUID>()
    private var menus = Set<ObjectIdentifier>()
    private var observers: [AnyCancellable] = []
    private var pendingHide: Task<Void, Never>?

    func attach(to window: NSWindow) {
        self.window = window
        observers = [
            NotificationCenter.default.publisher(for: NSMenu.didBeginTrackingNotification).sink { [weak self] note in
                guard let self, self.window?.isKeyWindow == true, let menu = note.object as? NSMenu else { return }
                self.menus.insert(ObjectIdentifier(menu)); self.refresh()
            },
            NotificationCenter.default.publisher(for: NSMenu.didEndTrackingNotification).sink { [weak self] note in
                guard let self, let menu = note.object as? NSMenu else { return }
                self.menus.remove(ObjectIdentifier(menu)); self.refresh()
            }
        ]
    }

    func setHovered(_ value: Bool) { hovered = value; refresh() }

    func hold(_ id: UUID, while active: Bool) {
        if active { holds.insert(id) } else { holds.remove(id) }
        refresh()
    }

    func reset() {
        pendingHide?.cancel(); pendingHide = nil
        hovered = false; holds.removeAll(); menus.removeAll()
        if visible { visible = false }
    }

    func shutdown() { reset(); observers.removeAll(); window = nil }

    private func refresh() {
        pendingHide?.cancel(); pendingHide = nil
        if hovered || !holds.isEmpty || !menus.isEmpty {
            if !visible { visible = true }
        } else if visible {
            // Bridge small edge crossings and the hand-off into a native popup menu.
            pendingHide = Task { @MainActor [weak self] in
                do { try await Task.sleep(for: .milliseconds(120)) } catch { return }
                guard let self else { return }
                self.visible = false; self.pendingHide = nil
            }
        }
    }
}

private struct WorkspaceChromeVisibleKey: EnvironmentKey { static let defaultValue = true }
private struct WorkspaceChromeKey: EnvironmentKey { static let defaultValue: WorkspacePanelChrome? = nil }

extension EnvironmentValues {
    var workspaceChromeVisible: Bool {
        get { self[WorkspaceChromeVisibleKey.self] }
        set { self[WorkspaceChromeVisibleKey.self] = newValue }
    }
    var workspaceChrome: WorkspacePanelChrome? {
        get { self[WorkspaceChromeKey.self] }
        set { self[WorkspaceChromeKey.self] = newValue }
    }
}

extension View {
    func workspacePanelHeader() -> some View { modifier(WorkspacePanelHeader()) }
    func workspaceChromeField(_ focus: FocusState<Bool>.Binding) -> some View {
        modifier(WorkspaceChromeField(focus: focus))
    }
}

private struct WorkspacePanelHeader: ViewModifier {
    @Environment(\.workspaceChromeVisible) private var visible
    func body(content: Content) -> some View {
        content.fixedSize(horizontal: false, vertical: true)
            .frame(height: visible ? nil : 0, alignment: .top).clipped()
            .opacity(visible ? 1 : 0).allowsHitTesting(visible).disabled(!visible)
            .accessibilityHidden(!visible)
    }
}

/// An address/filter being edited stays reachable even if the pointer leaves.
/// Enter/Escape, tab changes, or leaving the window release this temporary hold.
private struct WorkspaceChromeField: ViewModifier {
    let focus: FocusState<Bool>.Binding
    @Environment(\.workspaceChrome) private var chrome
    @Environment(\.isEnabled) private var enabled
    @State private var holdID = UUID()
    func body(content: Content) -> some View {
        content
            .onChange(of: focus.wrappedValue) { _, value in chrome?.hold(holdID, while: value) }
            .onChange(of: enabled) { _, value in if !value { focus.wrappedValue = false } }
            .onReceive(NotificationCenter.default.publisher(for: NSWindow.didResignKeyNotification)) { note in
                if let window = note.object as? NSWindow, window === chrome?.window { focus.wrappedValue = false }
            }
            .onDisappear { chrome?.hold(holdID, while: false) }
    }
}
