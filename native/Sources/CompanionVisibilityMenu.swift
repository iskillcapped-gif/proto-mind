import AppKit
import SwiftUI

struct CompanionVisibilityMenu: View {
    @ObservedObject var owner: DesktopCompanionWindows

    var body: some View {
        Menu {
            Toggle(L10n.text("Боковое окно 1"), isOn: visibility(.first))
            Toggle(L10n.text("Боковое окно 2"), isOn: visibility(.second))
        } label: {
            Image(systemName: owner.surfaces.contains(where: \.visible) ? "rectangle.on.rectangle.fill" : "rectangle.on.rectangle")
        }
        .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
        .help(L10n.text("Боковые окна · ⌥⌘1 / ⌥⌘2"))
        .accessibilityLabel(L10n.text("Боковые окна"))
    }

    private func visibility(_ id: DesktopCompanionID) -> Binding<Bool> {
        Binding(get: { owner.surface(id).visible }, set: { value in
            if value != owner.surface(id).visible { owner.toggle(id) }
        })
    }
}

/// Measure the real detail column after sidebar resizing/collapse and toolbar
/// layout. Window-relative coordinates remain correct as AppKit moves the group.
struct RegularWorkspaceContentRegion: NSViewRepresentable {
    let desktop: DesktopPresentation
    func makeNSView(context: Context) -> Region { let view = Region(); view.desktop = desktop; return view }
    func updateNSView(_ view: Region, context: Context) { view.desktop = desktop; view.reportFrame() }

    final class Region: NSView {
        weak var desktop: DesktopPresentation?
        private var reportPending = false
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func viewDidMoveToWindow() { super.viewDidMoveToWindow(); reportFrame() }
        override func layout() { super.layout(); reportFrame() }
        override func setFrameSize(_ newSize: NSSize) { super.setFrameSize(newSize); reportFrame() }
        override func setFrameOrigin(_ newOrigin: NSPoint) { super.setFrameOrigin(newOrigin); reportFrame() }
        func reportFrame() {
            guard !reportPending else { return }
            reportPending = true
            DispatchQueue.main.async { [weak self] in
                guard let self else { return }
                self.reportPending = false
                guard let window = self.window else { return }
                self.desktop?.updateRegularContentRect(self.convert(self.bounds, to: nil), in: window)
            }
        }
    }
}
