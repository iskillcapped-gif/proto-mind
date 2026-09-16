import AppKit
import SwiftUI
import Combine

/// Only intentional input selects a sidebar destination. Merely showing a cube preview,
/// moving the pointer or clicking the sidebar never takes ownership from a side window.
@MainActor
final class ConversationRouting: ObservableObject {
    @Published private(set) var panel: WorkspacePanelModel?
    private weak var region: ConversationInteractionRegion.Probe?
    private var regions: [ObjectIdentifier: WeakRegion] = [:]
    private var monitor: Any?
    private struct WeakRegion { weak var view: ConversationInteractionRegion.Probe? }

    func activate(_ panel: WorkspacePanelModel?, region: ConversationInteractionRegion.Probe? = nil) {
        let changed = self.panel !== panel
        if changed { self.panel = panel }
        if let region { self.region = region } else if changed { self.region = nil }
    }
    var destination: WorkspacePanelModel? {
        guard let panel, panel.visible else { return nil }
        if let region, !region.available { return nil }
        return panel
    }
    func register(_ view: ConversationInteractionRegion.Probe) {
        regions[ObjectIdentifier(view)] = WeakRegion(view: view)
        guard monitor == nil else { return }
        monitor = NSEvent.addLocalMonitorForEvents(matching: [.leftMouseDown, .rightMouseDown, .keyDown]) { [weak self] event in
            MainActor.assumeIsolated {
                self?.receive(event)
            }
            return event
        }
    }
    func unregister(_ view: ConversationInteractionRegion.Probe) {
        regions[ObjectIdentifier(view)] = nil
        if region === view { panel = nil; region = nil }
        if regions.isEmpty, let monitor { NSEvent.removeMonitor(monitor); self.monitor = nil }
    }
    private func receive(_ event: NSEvent) {
        let candidates = regions.values.compactMap(\.view).filter { view in
            guard view.available, view.window === event.window else { return false }
            if event.type == .keyDown {
                guard let responder = event.window?.firstResponder as? NSView else { return false }
                let rect = responder.convert(responder.bounds, to: nil)
                return view.convert(view.bounds, to: nil).contains(CGPoint(x: rect.midX, y: rect.midY))
            }
            return view.bounds.contains(view.convert(event.locationInWindow, from: nil))
        }
        // An expanded internal panel covers the main reader in the same NSWindow.
        if let view = candidates.sorted(by: { ($0.panel == nil ? 0 : 1) > ($1.panel == nil ? 0 : 1) }).first {
            activate(view.panel, region: view)
        }
    }
}

struct ConversationInteractionRegion: NSViewRepresentable {
    let routing: ConversationRouting
    var panel: WorkspacePanelModel? = nil
    var enabled = true
    func makeNSView(context: Context) -> Probe {
        let view = Probe(); view.routing = routing; routing.register(view); return view
    }
    func updateNSView(_ view: Probe, context: Context) { view.panel = panel; view.enabled = enabled }
    static func dismantleNSView(_ view: Probe, coordinator: ()) { view.routing?.unregister(view) }
    final class Probe: NSView {
        weak var routing: ConversationRouting?
        weak var panel: WorkspacePanelModel?
        var enabled = true
        var available: Bool { enabled && window?.isVisible == true && !isHiddenOrHasHiddenAncestor }
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override var acceptsFirstResponder: Bool { false }
    }
}

extension AppModel {
    func newSidebarConversation() {
        if let panel = conversationRouting.destination { newPanelConversation(in: panel) }
        else { newConversation() }
    }
    /// Sidebar navigation is a window action; it must not replace the main editor
    /// or consume a browser/terminal tab in the destination window.
    func openSidebarConversation(_ id: UUID, messageID: UUID? = nil) {
        guard canNavigateConversations, let chat = conversations.first(where: { $0.id == id }),
              messageID == nil || chat.messages.contains(where: { $0.id == messageID }) else { return }
        guard let panel = conversationRouting.destination else {
            conversationRouting.activate(nil)
            returnToConversation(id, messageID: messageID)
            return
        }
        let source = panel.presentations ?? presentations
        guard !source.locked else { return }
        guard panel.open(.conversation(id)) != nil else { return }
        source.dismissAll()
        panel.onConversationClosed = { [weak self] in self?.finishPanelDraft($0) }
        panel.transcriptDestination = TranscriptDestination(conversationID: id, messageID: messageID)
        source.reveal()
    }
}
