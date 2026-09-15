import AppKit
import SwiftUI

/// Tracking only; the existing sidebar, chat and their controls keep all mouse input.
struct DesktopWorkspaceHoverRegion: NSViewRepresentable {
    let desktop: DesktopPresentation

    func makeNSView(context: Context) -> TrackingView {
        let view = TrackingView(); view.desktop = desktop; return view
    }
    func updateNSView(_ view: TrackingView, context: Context) { view.desktop = desktop }

    final class TrackingView: NSView {
        weak var desktop: DesktopPresentation?
        private var hoverArea: NSTrackingArea?
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
        override func updateTrackingAreas() {
            super.updateTrackingAreas()
            if let hoverArea { removeTrackingArea(hoverArea) }
            let area = NSTrackingArea(rect: bounds, options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect],
                                      owner: self, userInfo: nil)
            addTrackingArea(area); hoverArea = area
        }
        override func mouseEntered(with event: NSEvent) { desktop?.updateWorkspaceHover(true) }
        override func mouseExited(with event: NSEvent) { desktop?.updateWorkspaceHover(false) }
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            if window == nil { desktop?.updateWorkspaceHover(false) }
        }
    }
}
