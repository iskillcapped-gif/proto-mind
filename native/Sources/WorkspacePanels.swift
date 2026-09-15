import Combine
import CryptoKit
import SwiftUI

enum WorkspacePanelPosition: String, CaseIterable, Identifiable {
    case upper, lower
    var id: String { rawValue }
    var title: String { self == .upper ? "Верхняя панель" : "Нижняя панель" }
}

/// Layout ownership is independent of the documents, terminals and conversations it displays.
@MainActor
final class WorkspacePanels: ObservableObject {
    let upper = WorkspacePanelModel()
    let lower = WorkspacePanelModel()
    @Published var active: WorkspacePanelPosition = .upper
    @Published var horizontalFraction: CGFloat = 0.48
    @Published var verticalFraction: CGFloat = 0.5
    @Published private(set) var lowerEnabled: Bool
    private let defaults: UserDefaults?
    private let preferenceKey: String
    private var observations: [AnyCancellable] = []

    init(stateDirectory: URL? = nil, defaults: UserDefaults? = nil) {
        self.defaults = defaults
        preferenceKey = "workspacePanels.lower." + (stateDirectory.map {
            SHA256.hash(data: Data($0.standardizedFileURL.path.utf8)).map { String(format: "%02x", $0) }.joined()
        } ?? "transient")
        lowerEnabled = defaults?.bool(forKey: preferenceKey) ?? false
        observations = [upper, lower].map { panel in
            panel.objectWillChange.sink { [weak self] in self?.objectWillChange.send() }
        }
    }

    var visible: Bool { upper.visible || (lowerEnabled && lower.visible) }
    var expanded: WorkspacePanelPosition? { upper.expanded ? .upper : lower.expanded ? .lower : nil }
    func panel(_ position: WorkspacePanelPosition) -> WorkspacePanelModel { position == .upper ? upper : lower }
    var activePanel: WorkspacePanelModel { panel(active) }

    func show(_ position: WorkspacePanelPosition = .upper) {
        if position == .lower { setLowerEnabled(true) }
        active = position
        panel(position).visible = true
    }

    func toggle() {
        if visible { upper.visible = false; lower.visible = false }
        else { upper.visible = true; lower.visible = lowerEnabled }
        upper.expanded = false; lower.expanded = false
    }

    func setLowerEnabled(_ enabled: Bool) {
        guard enabled != lowerEnabled else { return }
        let wasVisible = visible
        lowerEnabled = enabled
        lower.visible = enabled && wasVisible
        lower.expanded = false
        if !enabled { active = .upper; if wasVisible { upper.visible = true } }
        defaults?.set(enabled, forKey: preferenceKey)
    }

    func toggleExpansion(_ position: WorkspacePanelPosition) {
        let next = expanded != position
        upper.expanded = false; lower.expanded = false
        show(position)
        panel(position).expanded = next
    }

    func closeAll() { upper.closeAll(); lower.closeAll() }
}

struct WorkspacePanelsLayout {
    let main: CGRect
    let upper: CGRect
    let lower: CGRect
    let columnDivider: CGRect
    let rowDivider: CGRect

    init(size: CGSize, visible: Bool, expanded: WorkspacePanelPosition?, horizontal: CGFloat, vertical: CGFloat, lowerEnabled: Bool = true) {
        let size = CGSize(width: max(0, size.width), height: max(0, size.height))
        let gap = WorkspacePanelLayout.divider
        let side = WorkspacePanelLayout.width(total: size.width, fraction: horizontal)
        let x = max(0, size.width - side)
        let availableHeight = max(0, size.height - gap)
        let minimum = min(170, availableHeight / 2)
        let top = min(availableHeight - minimum, max(minimum, availableHeight * vertical))
        let full = CGRect(origin: .zero, size: size)
        main = CGRect(x: 0, y: 0, width: visible ? max(0, x - gap) : size.width, height: size.height)
        upper = expanded == .upper ? full : CGRect(x: x, y: 0, width: side, height: lowerEnabled ? top : size.height)
        lower = expanded == .lower ? full : CGRect(x: x, y: top + gap, width: side, height: availableHeight - top)
        columnDivider = CGRect(x: max(0, x - gap), y: 0, width: gap, height: size.height)
        rowDivider = CGRect(x: x, y: top, width: side, height: gap)
    }
}
