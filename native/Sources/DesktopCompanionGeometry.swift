import AppKit

enum DesktopCompanionID: String, CaseIterable, Identifiable {
    case first, second
    var id: String { rawValue }
    var title: String { self == .first ? "Окно 1" : "Окно 2" }
    var position: WorkspacePanelPosition { self == .first ? .upper : .lower }
}

/// Global AppKit coordinates. Attached surfaces share a vertical column beside the workspace.
enum DesktopCompanionGeometry {
    static let gap: CGFloat = 8
    static let defaultWidth: CGFloat = 380
    static let minimum = NSSize(width: 280, height: 320)
    static let minimumStackHeight: CGFloat = 200

    struct Row {
        let workspace: NSRect
        let panels: [DesktopCompanionID: NSRect]
        var bounds: NSRect { panels.values.reduce(workspace) { $0.union($1) } }
        var expanded: NSRect {
            let left = workspace.minX + DesktopGeometry.sidebarWidth(total: workspace.width) + 10
            return NSRect(x: left, y: workspace.minY, width: max(1, bounds.maxX - left), height: workspace.height)
        }
        func moved(to origin: NSPoint) -> Row {
            let dx = origin.x - workspace.minX, dy = origin.y - workspace.minY
            return Row(workspace: workspace.offsetBy(dx: dx, dy: dy),
                       panels: panels.mapValues { $0.offsetBy(dx: dx, dy: dy) })
        }
    }

    static func row(workspace: NSRect, widths: [DesktopCompanionID: CGFloat], screen: NSRect, topFraction: CGFloat = 0.5) -> Row {
        let slots = DesktopCompanionID.allCases.filter { widths[$0] != nil }
        guard !slots.isEmpty else { return Row(workspace: DesktopGeometry.fit(workspace, within: screen), panels: [:]) }
        let available = max(1, screen.width - gap)
        let mainMinimum = min(640, available * 0.52)
        let panelMinimum = min(minimum.width, max(1, available - mainMinimum))
        var panelWidth = max(panelMinimum, min(screen.width, widths.values.filter(\.isFinite).max() ?? 380))
        var mainWidth = min(available, max(mainMinimum, workspace.width.isFinite ? workspace.width : 1080))
        var excess = max(0, mainWidth + panelWidth - available)
        let mainReduction = min(excess, mainWidth - mainMinimum)
        mainWidth -= mainReduction; excess -= mainReduction
        panelWidth -= min(excess, panelWidth - panelMinimum)
        mainWidth = mainWidth.rounded(.down)
        panelWidth = panelWidth.rounded(.down)
        let total = mainWidth + panelWidth + gap
        let fitted = DesktopGeometry.fit(NSRect(x: workspace.minX, y: workspace.minY, width: total, height: workspace.height), within: screen)
        let main = NSRect(x: fitted.minX, y: fitted.minY, width: mainWidth, height: fitted.height)
        let column = NSRect(x: main.maxX + gap, y: main.minY, width: panelWidth, height: main.height)
        let top = topHeight(total: main.height, fraction: topFraction)
        let frames: [DesktopCompanionID: NSRect] = [
            .first: NSRect(x: column.minX, y: column.maxY - top, width: panelWidth, height: top),
            .second: NSRect(x: column.minX, y: column.minY, width: panelWidth, height: max(1, main.height - gap - top))
        ]
        // Each identity keeps its own slot even when its neighbour is hidden/free.
        return Row(workspace: main, panels: frames.filter { slots.contains($0.key) })
    }

    static func topHeight(total: CGFloat, fraction: CGFloat) -> CGFloat {
        let available = max(2, total - gap)
        let minimum = min(minimumStackHeight, available / 2)
        // AppKit rounds native window frames to screen coordinates. Split once,
        // then derive the other height so independent rounding cannot grow the pair.
        return min(available - minimum, max(minimum, (available * (fraction.isFinite ? fraction : 0.5)).rounded()))
    }

    static func shouldStack(_ frame: NSRect, with sibling: NSRect, id: DesktopCompanionID) -> Bool {
        let overlap = max(0, min(frame.maxX, sibling.maxX) - max(frame.minX, sibling.minX))
        let distance = id == .first ? frame.minY - sibling.maxY : sibling.minY - frame.maxY
        return abs(distance - gap) <= 28 && overlap >= min(frame.width, sibling.width) * 0.45
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
