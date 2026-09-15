import AppKit
import SwiftUI

/// Transient navigation only. Each source binding retains ownership of its operation.
@MainActor
final class WorkspacePresentations: ObservableObject {
    struct Page: Identifiable {
        let id: UUID
        var content: AnyView
        let clearBinding: () -> Void
        let onDismiss: () -> Void
        let dismiss: () -> Void
        var dismissalDisabled = false
    }
    @Published private(set) var pages: [Page] = []
    weak var window: NSWindow?
    var reveal: () -> Void = {}
    private weak var priorResponder: NSResponder?
    var locked: Bool { pages.contains { $0.dismissalDisabled } }

    func present(id: UUID, content: AnyView, clearBinding: @escaping () -> Void, onDismiss: @escaping () -> Void = {}) {
        guard !pages.contains(where: { $0.id == id }) else { return }
        if pages.isEmpty { priorResponder = window?.firstResponder }
        pages.append(Page(id: id, content: content, clearBinding: clearBinding, onDismiss: onDismiss,
                          dismiss: { [weak self] in self?.dismiss(id: id) }))
        reveal()
        window?.makeFirstResponder(nil)
    }

    func update(id: UUID, content: AnyView) {
        guard let index = pages.firstIndex(where: { $0.id == id }) else { return }
        pages[index].content = content
    }

    func setDismissalDisabled(_ disabled: Bool, id: UUID) {
        guard let index = pages.firstIndex(where: { $0.id == id }), pages[index].dismissalDisabled != disabled else { return }
        pages[index].dismissalDisabled = disabled
    }

    func dismissTop() {
        guard !locked, let id = pages.last?.id else { return }
        remove(id: id)
    }

    func dismiss(id: UUID) {
        guard !locked, pages.last?.id == id else { return }
        remove(id: id)
    }

    @discardableResult func dismissAll() -> Bool {
        guard !locked else { return false }
        if let first = pages.first { remove(id: first.id) }
        return true
    }

    /// A model can close its own finished/invalidated page, including any child previews.
    func remove(id: UUID) {
        guard let index = pages.firstIndex(where: { $0.id == id }) else { return }
        let removed = Array(pages[index...].reversed())
        pages.removeSubrange(index...)
        for page in removed { page.clearBinding(); page.onDismiss() }
        if pages.isEmpty, window?.isKeyWindow == true, let priorResponder { window?.makeFirstResponder(priorResponder) }
    }

    func shutdown() { pages = []; priorResponder = nil; window = nil; reveal = {} }
}

private struct WorkspacePresentationsKey: EnvironmentKey { static let defaultValue: WorkspacePresentations? = nil }
private struct WorkspaceInlineKey: EnvironmentKey { static let defaultValue = false }
private struct WorkspaceDismissKey: EnvironmentKey { static let defaultValue: (() -> Void)? = nil }
extension EnvironmentValues {
    var workspacePresentations: WorkspacePresentations? {
        get { self[WorkspacePresentationsKey.self] }
        set { self[WorkspacePresentationsKey.self] = newValue }
    }
    var workspaceInline: Bool {
        get { self[WorkspaceInlineKey.self] }
        set { self[WorkspaceInlineKey.self] = newValue }
    }
    var workspaceDismiss: (() -> Void)? {
        get { self[WorkspaceDismissKey.self] }
        set { self[WorkspaceDismissKey.self] = newValue }
    }
}

@propertyWrapper struct WorkspaceDismiss: DynamicProperty {
    @Environment(\.dismiss) private var systemDismiss
    @Environment(\.workspaceDismiss) private var inlineDismiss
    var wrappedValue: () -> Void { inlineDismiss ?? { systemDismiss() } }
}

private struct WorkspaceDismissalPreference: PreferenceKey {
    static let defaultValue = false
    static func reduce(value: inout Bool, nextValue: () -> Bool) { value = value || nextValue() }
}

extension View {
    func workspaceSheet<Page: View>(isPresented: Binding<Bool>, onDismiss: (() -> Void)? = nil,
                                   @ViewBuilder content: @escaping () -> Page) -> some View {
        modifier(WorkspaceSheetModifier(isPresented: isPresented, onDismiss: onDismiss, page: content))
    }
    func workspaceSheet<Item: Identifiable, Page: View>(item: Binding<Item?>, onDismiss: (() -> Void)? = nil,
                                                       @ViewBuilder content: @escaping (Item) -> Page) -> some View {
        modifier(WorkspaceItemSheetModifier(item: item, onDismiss: onDismiss, page: content))
    }
    func workspaceDismissDisabled(_ disabled: Bool) -> some View {
        preference(key: WorkspaceDismissalPreference.self, value: disabled).interactiveDismissDisabled(disabled)
    }
    func workspacePageSize(width: CGFloat, height: CGFloat? = nil) -> some View {
        modifier(WorkspacePageSize(width: width, height: height))
    }
    func workspaceBackground(_ color: Color) -> some View { modifier(WorkspaceBackground(color: color)) }
    func workspaceConfirmationDialog<Actions: View, Message: View>(_ title: String, isPresented: Binding<Bool>,
            titleVisibility: Visibility = .visible, @ViewBuilder actions: @escaping () -> Actions,
            @ViewBuilder message: @escaping () -> Message) -> some View {
        workspaceSheet(isPresented: isPresented) {
            VStack(alignment: .leading, spacing: 22) {
                Text(title).font(.title2.weight(.semibold))
                message().foregroundStyle(.secondary)
                HStack(spacing: 12) { actions() }.buttonStyle(.bordered).controlSize(.large)
            }.padding(26).workspacePageSize(width: 550)
        }
    }
    func workspaceAlert<Value, Actions: View, Message: View>(_ title: String, isPresented: Binding<Bool>, presenting value: Value?,
            @ViewBuilder actions: @escaping (Value) -> Actions, @ViewBuilder message: @escaping (Value) -> Message) -> some View {
        workspaceSheet(isPresented: isPresented) {
            if let value {
                VStack(alignment: .leading, spacing: 22) {
                    Text(title).font(.title2.weight(.semibold))
                    message(value).foregroundStyle(.secondary)
                    HStack(spacing: 12) { actions(value) }.buttonStyle(.bordered).controlSize(.large)
                }.padding(26).workspacePageSize(width: 550)
            }
        }
    }
}

private struct WorkspaceSheetModifier<Page: View>: ViewModifier {
    @Environment(\.workspacePresentations) private var presentations
    @Binding var isPresented: Bool
    let onDismiss: (() -> Void)?
    @ViewBuilder let page: () -> Page
    @State private var id = UUID()
    func body(content: Content) -> some View {
        // Refresh derived content when its source re-renders (for example a confirmation's
        // busy state). The source does not observe the destination's page collection.
        let sourceRevision = UUID()
        // Build in the SwiftUI body so reads of the source's @State are tracked.
        let renderedPage = isPresented ? AnyView(page()) : nil
        if let presentations {
            content.onChange(of: isPresented, initial: true) { _, shown in
                if shown, let renderedPage { presentations.present(id: id, content: renderedPage, clearBinding: { isPresented = false }, onDismiss: onDismiss ?? {}) }
                else { presentations.remove(id: id) }
            }.onChange(of: sourceRevision) { _, _ in
                if isPresented, let renderedPage { presentations.update(id: id, content: renderedPage) }
            }.onDisappear { presentations.remove(id: id) }
        } else { content.sheet(isPresented: $isPresented, onDismiss: onDismiss, content: page) }
    }
}

private struct WorkspaceItemSheetModifier<Item: Identifiable, Page: View>: ViewModifier {
    @Environment(\.workspacePresentations) private var presentations
    @Binding var item: Item?
    let onDismiss: (() -> Void)?
    @ViewBuilder let page: (Item) -> Page
    @State private var id = UUID()
    func body(content: Content) -> some View {
        let sourceRevision = UUID()
        let value = item
        let renderedPage = value.map { AnyView(page($0)) }
        if let presentations {
            content.onChange(of: item?.id, initial: true) { old, new in
                // Clear only the item represented by this page; never erase its replacement.
                if old != nil { presentations.remove(id: id); id = UUID() }
                if let value, let renderedPage {
                    let expected = value.id
                    presentations.present(id: id, content: renderedPage, clearBinding: {
                        if item?.id == expected { item = nil }
                    }, onDismiss: onDismiss ?? {})
                }
            }.onChange(of: sourceRevision) { _, _ in
                if let renderedPage { presentations.update(id: id, content: renderedPage) }
            }.onDisappear { presentations.remove(id: id) }
        } else { content.sheet(item: $item, onDismiss: onDismiss, content: page) }
    }
}

private struct WorkspacePageSize: ViewModifier {
    @Environment(\.workspaceInline) private var inline
    let width: CGFloat
    let height: CGFloat?
    @ViewBuilder func body(content: Content) -> some View {
        if inline {
            if height == nil { ScrollView { content.frame(maxWidth: .infinity, alignment: .topLeading) } }
            else { content.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading) }
        } else { content.frame(width: width, height: height) }
    }
}

private struct WorkspaceBackground: ViewModifier {
    @Environment(\.desktopGlass) private var glass
    let color: Color
    func body(content: Content) -> some View { content.background(glass ? Color.clear : color) }
}

struct WorkspaceContentHost: View {
    @ObservedObject var app: AppModel
    @ObservedObject var presentations: WorkspacePresentations
    var body: some View {
        ZStack {
            WorkspaceSplitView(model: app, panel: app.workspacePanel)
                .opacity(presentations.pages.isEmpty ? 1 : 0)
                .allowsHitTesting(presentations.pages.isEmpty)
                .disabled(!presentations.pages.isEmpty)
                .accessibilityHidden(!presentations.pages.isEmpty)
            ForEach(presentations.pages) { page in
                VStack(spacing: 0) {
                    HStack {
                        Button { presentations.dismissTop() } label: {
                            Label(presentations.pages.count == 1 ? "К чату" : "Назад", systemImage: "chevron.left")
                        }.buttonStyle(.nativeHover).disabled(presentations.locked)
                        Spacer()
                    }.font(.system(size: 12)).foregroundStyle(.secondary).padding(.horizontal, 20).padding(.vertical, 12)
                    Divider().opacity(0.4)
                    page.content
                        .environment(\.workspaceInline, true)
                        .environment(\.workspaceDismiss, page.dismiss)
                        .onPreferenceChange(WorkspaceDismissalPreference.self) { presentations.setDismissalDisabled($0, id: page.id) }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .opacity(page.id == presentations.pages.last?.id ? 1 : 0)
                .allowsHitTesting(page.id == presentations.pages.last?.id)
                .disabled(page.id != presentations.pages.last?.id)
                .accessibilityHidden(page.id != presentations.pages.last?.id)
                .onExitCommand { presentations.dismissTop() }
            }
        }
    }
}

extension AppModel {
    func openSettings() { showSettings = true }

    /// OS pickers remain native, attached to the actual workspace rather than a transient menu.
    func presentFilePicker(_ panel: NSSavePanel, completion: @escaping (NSApplication.ModalResponse) -> Void) {
        if desktop.enabled { desktop.revealMainContent() }
        if let window = desktop.window {
            guard window.attachedSheet == nil else { return }
            window.makeKeyAndOrderFront(nil)
            panel.beginSheetModal(for: window, completionHandler: completion)
        } else { panel.begin(completionHandler: completion) }
    }
}
