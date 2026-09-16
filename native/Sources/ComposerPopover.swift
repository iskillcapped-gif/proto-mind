import AppKit
import SwiftUI

// AppKit menus and NSPopover may flip below the anchor. Composer panels instead
// occupy only the available space above it; long contents scroll within that space.
enum ComposerPopoverPlacement {
    static func frame(anchor: CGRect, screen: CGRect, size: CGSize, trailing: Bool, confinedToColumn: Bool = false, columnWidth: CGFloat? = nil) -> CGRect {
        let bounds = screen.insetBy(dx: 8, dy: 8)
        let column = confinedToColumn ? bounds.intersection(CGRect(x: anchor.minX, y: bounds.minY, width: columnWidth ?? anchor.width, height: bounds.height)) : bounds
        guard !column.isNull, column.width > 0 else { return .zero }
        let width = min(size.width, column.width)
        let bottom = max(bounds.minY, anchor.maxY + 8)
        let height = max(0, min(size.height, bounds.maxY - bottom))
        let left = trailing ? anchor.maxX - width : anchor.minX
        return CGRect(x: min(max(left, column.minX), column.maxX - width), y: bottom, width: width, height: height)
    }
}

extension View {
    func composerPopover<Content: View>(isPresented: Binding<Bool>, width: CGFloat = 300, trailing: Bool = false, confinedToColumn: Bool = false, columnWidth: CGFloat? = nil,
                                       @ViewBuilder content: @escaping () -> Content) -> some View {
        background(ComposerPopoverAnchor(isPresented: isPresented, width: width, trailing: trailing, confinedToColumn: confinedToColumn, columnWidth: columnWidth, content: content))
    }
}

private struct ComposerPopoverAnchor<Content: View>: NSViewRepresentable {
    @Binding var isPresented: Bool
    @Environment(\.workspacePresentations) private var presentations
    @Environment(\.desktopGlass) private var desktopGlass
    let width: CGFloat
    let trailing: Bool
    let confinedToColumn: Bool
    let columnWidth: CGFloat?
    @ViewBuilder let content: () -> Content

    func makeCoordinator() -> Coordinator { Coordinator() }
    func makeNSView(context: Context) -> NSView { NSView() }
    func updateNSView(_ view: NSView, context: Context) {
        let coordinator = context.coordinator
        coordinator.dismiss = { isPresented = false }
        if isPresented {
            // Hosting updates cannot synchronously change the source SwiftUI tree.
            DispatchQueue.main.async { [weak view, weak coordinator] in
                guard let view, let coordinator, isPresented else { return }
                coordinator.show(anchor: view, width: width, trailing: trailing, confinedToColumn: confinedToColumn, columnWidth: columnWidth,
                                 content: AnyView(content().environment(\.workspacePresentations, presentations).environment(\.desktopGlass, desktopGlass)))
            }
        } else { coordinator.close() }
    }
    static func dismantleNSView(_ view: NSView, coordinator: Coordinator) { coordinator.close() }

    final class Panel: NSPanel {
        override var canBecomeKey: Bool { true }
        override var canBecomeMain: Bool { false }
    }

    final class Coordinator {
        var dismiss: (() -> Void)?
        private var panel: Panel?
        private var monitor: Any?
        private var observers: [NSObjectProtocol] = []
        private weak var priorResponder: NSResponder?
        private weak var owner: NSWindow?

        func show(anchor: NSView, width: CGFloat, trailing: Bool, confinedToColumn: Bool, columnWidth: CGFloat?, content: AnyView) {
            guard let window = anchor.window, let screen = window.screen else { return }
            let rect = window.convertToScreen(anchor.convert(anchor.bounds, to: nil))
            let bounds = confinedToColumn ? screen.visibleFrame.intersection(window.frame) : screen.visibleFrame
            let fittedWidth = min(width, confinedToColumn ? (columnWidth ?? rect.width) : width, max(0, bounds.width - 16))
            let measured = NSHostingController(rootView: content.frame(width: fittedWidth))
                .sizeThatFits(in: CGSize(width: fittedWidth, height: 10000))
            let frame = ComposerPopoverPlacement.frame(anchor: rect, screen: bounds,
                                                       size: CGSize(width: fittedWidth, height: measured.height), trailing: trailing,
                                                       confinedToColumn: confinedToColumn, columnWidth: columnWidth)
            guard frame.height > 0 else { dismiss?(); return }
            let root = AnyView(
                ScrollView { content.frame(maxWidth: .infinity, alignment: .leading) }
                    .frame(width: frame.width, height: frame.height)
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 13))
                    .overlay(RoundedRectangle(cornerRadius: 13).stroke(NativeTheme.hairline))
                    .clipShape(RoundedRectangle(cornerRadius: 13))
            )
            if let panel {
                (panel.contentView as? NSHostingView<AnyView>)?.rootView = root
                panel.setFrame(frame, display: true)
                return
            }
            let panel = Panel(contentRect: frame, styleMask: [.borderless], backing: .buffered, defer: false)
            panel.isReleasedWhenClosed = false
            panel.isOpaque = false
            panel.backgroundColor = .clear
            panel.hasShadow = true
            panel.level = .popUpMenu
            panel.contentView = NSHostingView(rootView: root)
            self.panel = panel
            owner = window
            priorResponder = window.firstResponder
            window.addChildWindow(panel, ordered: .above)
            panel.makeKeyAndOrderFront(nil)
            monitor = NSEvent.addLocalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown, .otherMouseDown, .keyDown]) { [weak self] event in
                guard let self, let panel = self.panel else { return event }
                if event.type == .keyDown {
                    if event.keyCode == 53 { self.dismiss?(); self.close(); return nil }
                } else if event.window !== panel {
                    let anchorClicked = event.window === window && rect.contains(window.convertPoint(toScreen: event.locationInWindow))
                    self.dismiss?(); self.close()
                    if anchorClicked { return nil }
                }
                return event
            }
            for name in [NSWindow.didResizeNotification, NSWindow.didMoveNotification, NSWindow.willCloseNotification] {
                observers.append(NotificationCenter.default.addObserver(forName: name, object: window, queue: .main) { [weak self] _ in
                    self?.dismiss?(); self?.close()
                })
            }
            observers.append(NotificationCenter.default.addObserver(forName: NSApplication.didResignActiveNotification, object: nil, queue: .main) { [weak self] _ in
                self?.dismiss?(); self?.close()
            })
        }

        func close() {
            if let monitor { NSEvent.removeMonitor(monitor) }; monitor = nil
            observers.forEach(NotificationCenter.default.removeObserver); observers = []
            guard let panel else { return }
            let wasKey = panel.isKeyWindow
            self.panel = nil
            owner?.removeChildWindow(panel)
            panel.orderOut(nil)
            panel.close()
            if wasKey, NSApp.isActive, let owner, owner.isVisible, owner.attachedSheet == nil {
                owner.makeKeyAndOrderFront(nil)
                if let priorResponder { owner.makeFirstResponder(priorResponder) }
            }
        }
    }
}

struct ComposerMenuRow: View {
    let title: String
    var icon: String? = nil
    var selected = false
    var detail: String? = nil
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                if let icon { Image(systemName: icon).frame(width: 18) }
                VStack(alignment: .leading, spacing: 3) {
                    Text(title).lineLimit(2)
                    if let detail { Text(detail).font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(3) }
                }
                Spacer(minLength: 6)
                if selected { Image(systemName: "checkmark").font(.system(size: 11, weight: .semibold)) }
            }.font(.system(size: 13)).padding(.horizontal, 10).padding(.vertical, 8)
                .frame(maxWidth: .infinity, alignment: .leading).contentShape(Rectangle())
        }.buttonStyle(.nativeHover).accessibilityAddTraits(selected ? [.isSelected] : [])
    }
}
