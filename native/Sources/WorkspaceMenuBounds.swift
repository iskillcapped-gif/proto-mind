import AppKit
import SwiftUI

/// A mounted surface supplies its current rectangle without owning its contents.
@MainActor
final class WorkspaceMenuBounds: ObservableObject {
    weak var view: NSView?

    func frame(in window: NSWindow) -> CGRect? {
        guard let view, view.window === window else { return nil }
        return window.convertToScreen(view.convert(view.bounds, to: nil))
    }
}

private struct WorkspaceMenuBoundsKey: EnvironmentKey {
    static let defaultValue: WorkspaceMenuBounds? = nil
}

extension EnvironmentValues {
    var workspaceMenuBounds: WorkspaceMenuBounds? {
        get { self[WorkspaceMenuBoundsKey.self] }
        set { self[WorkspaceMenuBoundsKey.self] = newValue }
    }
}

extension View {
    func workspaceMenuBoundary() -> some View { modifier(WorkspaceMenuBoundary()) }
}

private struct WorkspaceMenuBoundary: ViewModifier {
    @StateObject private var bounds = WorkspaceMenuBounds()
    func body(content: Content) -> some View {
        content.background(BoundaryAnchor(bounds: bounds)).environment(\.workspaceMenuBounds, bounds)
    }
}

private struct BoundaryAnchor: NSViewRepresentable {
    let bounds: WorkspaceMenuBounds
    func makeNSView(context: Context) -> NSView {
        let view = NSView(); bounds.view = view; return view
    }
    func updateNSView(_ view: NSView, context: Context) { bounds.view = view }
}
