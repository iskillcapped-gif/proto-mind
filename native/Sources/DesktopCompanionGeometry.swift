import AppKit

enum DesktopCompanionID: String, CaseIterable, Identifiable {
    case first, second
    var id: String { rawValue }
    var title: String { self == .first ? "Окно 1" : "Окно 2" }
    var position: WorkspacePanelPosition { self == .first ? .upper : .lower }
}

/// Global AppKit coordinates. Attached surfaces form a horizontal row beside the workspace.
enum DesktopCompanionGeometry {
    static let gap: CGFloat = 8
    static let minimum = NSSize(width: 280, height: 320)

    struct Row {
        let workspace: NSRect
        let panels: [DesktopCompanionID: NSRect]
        var bounds: NSRect { panels.values.reduce(workspace) { $0.union($1) } }
        var expanded: NSRect {
            let left = workspace.minX + DesktopGeometry.sidebarWidth(total: workspace.width) + 10
            return NSRect(x: left, y: workspace.minY, width: max(1, bounds.maxX - left), height: workspace.height)
        }
    }

    static func row(workspace: NSRect, widths: [DesktopCompanionID: CGFloat], screen: NSRect) -> Row {
        let slots = DesktopCompanionID.allCases.filter { widths[$0] != nil }
        guard !slots.isEmpty else { return Row(workspace: DesktopGeometry.fit(workspace, within: screen), panels: [:]) }
        let available = max(1, screen.width - CGFloat(slots.count) * gap)
        let mainMinimum = min(640, available * 0.52)
        let panelMinimum = min(minimum.width, max(1, (available - mainMinimum) / CGFloat(slots.count)))
        var sizes = slots.map { max(panelMinimum, min(screen.width, (widths[$0] ?? 380).isFinite ? widths[$0]! : 380)) }
        var mainWidth = min(available, max(mainMinimum, workspace.width.isFinite ? workspace.width : 1080))
        var excess = max(0, mainWidth + sizes.reduce(0, +) - available)
        let mainReduction = min(excess, mainWidth - mainMinimum)
        mainWidth -= mainReduction; excess -= mainReduction
        if excess > 0 {
            let capacity = sizes.reduce(0) { $0 + max(0, $1 - panelMinimum) }
            if capacity > 0 { sizes = sizes.map { $0 - excess * max(0, $0 - panelMinimum) / capacity } }
        }
        let total = mainWidth + sizes.reduce(0, +) + CGFloat(slots.count) * gap
        let fitted = DesktopGeometry.fit(NSRect(x: workspace.minX, y: workspace.minY, width: total, height: workspace.height), within: screen)
        let main = NSRect(x: fitted.minX, y: fitted.minY, width: mainWidth, height: fitted.height)
        var x = main.maxX + gap
        var panels: [DesktopCompanionID: NSRect] = [:]
        for (index, id) in slots.enumerated() {
            panels[id] = NSRect(x: x, y: fitted.minY, width: sizes[index], height: fitted.height)
            x += sizes[index] + gap
        }
        return Row(workspace: main, panels: panels)
    }

    static func shouldAttach(_ frame: NSRect, beside anchor: NSRect) -> Bool {
        let overlap = max(0, min(frame.maxY, anchor.maxY) - max(frame.minY, anchor.minY))
        return abs(frame.minX - (anchor.maxX + gap)) <= 28
            && overlap >= min(frame.height, anchor.height) * 0.45
    }

    static func enlarged(_ frame: NSRect, screen: NSRect) -> NSRect {
        let size = NSSize(width: max(frame.width, min(1000, screen.width * 0.8)),
                          height: max(frame.height, min(820, screen.height * 0.9)))
        return DesktopGeometry.fit(NSRect(x: frame.midX - size.width / 2, y: frame.midY - size.height / 2,
                                         width: size.width, height: size.height), within: screen)
    }
}
