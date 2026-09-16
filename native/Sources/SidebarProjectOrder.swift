import AppKit
import CryptoKit
import SwiftUI
import UniformTypeIdentifiers

/// Presentation preferences stay separate from conversation history and permissions.
enum NativeUIPreference {
    static func key(_ name: String, stateDirectory: URL) -> String {
        let digest = SHA256.hash(data: Data(stateDirectory.standardizedFileURL.path.utf8))
            .map { String(format: "%02x", $0) }.joined()
        return name + ".v1." + digest
    }
}

struct SidebarProjectTransfer: Codable, Transferable {
    let id: String
    let owner: UUID
    static var transferRepresentation: some TransferRepresentation {
        CodableRepresentation(contentType: .protoMindSidebarProject)
            .visibility(.ownProcess)
    }
}

extension UTType {
    static let protoMindSidebarProject = UTType(exportedAs: "local.proto-mind.sidebar-project", conformingTo: .data)
}

@MainActor
final class SidebarProjectOrder: ObservableObject {
    @Published private(set) var ids: [String]
    let owner = UUID()
    private let defaults: UserDefaults
    private let key: String

    init(stateDirectory: URL, defaults: UserDefaults = .standard) {
        self.defaults = defaults
        key = NativeUIPreference.key("sidebarProjectOrder", stateDirectory: stateDirectory)
        var seen = Set<String>()
        ids = (defaults.stringArray(forKey: key) ?? []).filter { seen.insert($0).inserted }
    }

    func groups(_ conversations: [Conversation]) -> [ConversationGroup] {
        let groups = ConversationGroup.make(conversations.sorted {
            $0.updatedAt == $1.updatedAt ? $0.id.uuidString < $1.id.uuidString : $0.updatedAt > $1.updatedAt
        })
        let byID = Dictionary(uniqueKeysWithValues: groups.map { ($0.id, $0) })
        let known = Set(ids)
        return ids.compactMap { byID[$0] } + groups.filter { !known.contains($0.id) }
    }

    @discardableResult
    func move(_ item: SidebarProjectTransfer, to target: String, after: Bool, conversations: [Conversation]) -> Bool {
        guard item.owner == owner, item.id != target else { return false }
        var order = groups(conversations).map(\.id)
        guard let source = order.firstIndex(of: item.id), order.contains(target) else { return false }
        order.remove(at: source)
        guard let destination = order.firstIndex(of: target) else { return false }
        order.insert(item.id, at: destination + (after ? 1 : 0))
        guard ids != order else { return true }
        ids = order
        defaults.set(order, forKey: key)
        return true
    }
}

struct SidebarProjectsView<Row: View>: View {
    @ObservedObject var app: AppModel
    @ObservedObject var order: SidebarProjectOrder
    @ObservedObject var drag: SidebarProjectDragSession
    let row: (Conversation) -> Row
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        ForEach(order.groups(app.visibleConversations)) { group in
            SidebarProjectSection(group: group, app: app, order: order, drag: drag, row: row)
        }
        .animation(reduceMotion ? nil : .easeInOut(duration: 0.22), value: order.ids)
    }
}

enum SidebarProjectEdge: Equatable {
    case before, after

    static func at(y: CGFloat, height: CGFloat, previous: Self? = nil) -> Self {
        // A small dead band prevents the insertion line flickering at the midpoint.
        let middle = height / 2
        if let previous, abs(y - middle) < 6 { return previous }
        return y < middle ? .before : .after
    }
}

/// A drag has one insertion marker across the entire sidebar. A destination's
/// dropExited is not guaranteed when SwiftUI moves/reuses rows after a drop.
@MainActor
final class SidebarProjectDragSession: ObservableObject {
    struct Insertion: Equatable {
        let group: String
        let edge: SidebarProjectEdge
    }
    @Published private(set) var insertion: Insertion?
    private(set) var source: String?
    private var timer: Timer?
    private var monitor: Any?
    private let primaryButtonDown: () -> Bool
    var isMonitoring: Bool { timer != nil || monitor != nil }

    init(primaryButtonDown: @escaping () -> Bool = { NSEvent.pressedMouseButtons & 1 != 0 }) {
        self.primaryButtonDown = primaryButtonDown
    }

    func begin(_ source: String) {
        finish()
        self.source = source
        // Native dragging uses a tracking run loop and can consume mouse-up
        // before ordinary event monitors. Watch release only during this drag.
        let timer = Timer(timeInterval: 0.075, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.checkForRelease() }
        }
        self.timer = timer
        RunLoop.main.add(timer, forMode: .common)
        RunLoop.main.add(timer, forMode: .eventTracking)
        monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            if event.keyCode == 53 { self?.finish() }
            return event
        }
    }

    func show(group: String, y: CGFloat, height: CGFloat) {
        guard source != nil else { return }
        guard primaryButtonDown() else { finish(); return }
        guard group != source else { if insertion != nil { insertion = nil }; return }
        let previous = insertion?.group == group ? insertion?.edge : nil
        let next = Insertion(group: group, edge: .at(y: y, height: height, previous: previous))
        if insertion != next { insertion = next }
    }

    func leave(_ group: String) {
        if insertion?.group == group { insertion = nil }
    }

    func checkForRelease() {
        if !primaryButtonDown() { finish() }
    }

    func finish() {
        source = nil
        if insertion != nil { insertion = nil }
        timer?.invalidate(); timer = nil
        if let monitor { NSEvent.removeMonitor(monitor) }; monitor = nil
    }

    deinit {
        timer?.invalidate()
        if let monitor { NSEvent.removeMonitor(monitor) }
    }
}

struct SidebarProjectDragCompletion: ViewModifier {
    let drag: SidebarProjectDragSession

    @ViewBuilder func body(content: Content) -> some View {
        if #available(macOS 26, *) {
            content.onDragSessionUpdated { session in
                if case .ended = session.phase { drag.finish() }
            }
        } else { content }
    }
}

private struct SidebarProjectSection<Row: View>: View {
    let group: ConversationGroup
    @ObservedObject var app: AppModel
    @ObservedObject var order: SidebarProjectOrder
    @ObservedObject var drag: SidebarProjectDragSession
    let row: (Conversation) -> Row
    @State private var height: CGFloat = 40
    private var edge: SidebarProjectEdge? { drag.insertion?.group == group.id ? drag.insertion?.edge : nil }

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            SidebarProjectHeading(group: group, app: app, order: order, drag: drag)
            ForEach(group.conversations) { row($0) }
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
        .background {
            GeometryReader { geometry in
                Color.clear.onAppear { height = geometry.size.height }
                    .onChange(of: geometry.size.height) { _, value in height = value }
            }
        }
        .overlay(alignment: edge == .after ? .bottom : .top) {
            if edge != nil {
                HStack(spacing: 0) {
                    Circle().fill(NativeTheme.accent).frame(width: 5, height: 5)
                    Capsule().fill(NativeTheme.accent).frame(height: 2)
                }.padding(.horizontal, 6).allowsHitTesting(false).accessibilityHidden(true)
            }
        }
        .onDrop(of: [.protoMindSidebarProject], delegate: SidebarProjectDrop(
            app: app, order: order, drag: drag, target: group.id, height: height))
        .onDisappear { drag.leave(group.id) }
    }
}

/// Hover only marks an insertion point. Esc or dropping outside never saves an order.
private struct SidebarProjectDrop: DropDelegate {
    let app: AppModel
    let order: SidebarProjectOrder
    let drag: SidebarProjectDragSession
    let target: String
    let height: CGFloat

    func validateDrop(info: DropInfo) -> Bool {
        !app.operationBusy && !app.privateBackupRestartRequired
            && info.itemProviders(for: [.protoMindSidebarProject]).count == 1
    }

    func dropEntered(info: DropInfo) { update(info) }
    func dropExited(info: DropInfo) { drag.leave(target) }
    func dropUpdated(info: DropInfo) -> DropProposal? {
        guard validateDrop(info: info) else { drag.leave(target); return DropProposal(operation: .forbidden) }
        update(info)
        return DropProposal(operation: .move)
    }

    func performDrop(info: DropInfo) -> Bool {
        defer { drag.finish() }
        guard validateDrop(info: info), let provider = info.itemProviders(for: [.protoMindSidebarProject]).first else { return false }
        let edge = drag.insertion?.group == target ? drag.insertion?.edge : nil
        let after = SidebarProjectEdge.at(y: info.location.y, height: height, previous: edge) == .after
        _ = provider.loadTransferable(type: SidebarProjectTransfer.self) { result in
            guard case .success(let item) = result else { return }
            Task { @MainActor in
                guard !app.operationBusy, !app.privateBackupRestartRequired else { return }
                order.move(item, to: target, after: after, conversations: app.listedConversations)
            }
        }
        return true
    }

    private func update(_ info: DropInfo) {
        drag.show(group: target, y: info.location.y, height: height)
    }
}

private struct SidebarProjectHeading: View {
    let group: ConversationGroup
    @ObservedObject var app: AppModel
    @ObservedObject var order: SidebarProjectOrder
    @ObservedObject var drag: SidebarProjectDragSession
    @State private var hovered = false

    var body: some View {
        HStack(spacing: 8) {
            Label(group.title, systemImage: "folder").lineLimit(1)
            Spacer(minLength: 0)
            Image(systemName: "line.3.horizontal").font(.system(size: 10))
                .opacity(hovered ? 0.6 : 0)
        }.font(.system(size: 13)).foregroundStyle(.secondary)
            .padding(.horizontal, 11).frame(height: 36).contentShape(Rectangle())
            .background(hovered ? Color.primary.opacity(0.035) : .clear, in: RoundedRectangle(cornerRadius: 7))
            .onHover { hovered = $0 }
            .help((group.workspace ?? "Диалоги без папки проекта") + "\nПеретащите, чтобы изменить порядок проектов")
            .onDrag {
                let provider = NSItemProvider()
                guard !app.operationBusy, !app.privateBackupRestartRequired else { return provider }
                drag.begin(group.id)
                let item = SidebarProjectTransfer(id: group.id, owner: order.owner)
                provider.register(item)
                return provider
            } preview: {
                SidebarProjectDragPreview(title: group.title, count: group.conversations.count)
            }
            .accessibilityElement(children: .combine)
            .accessibilityAction(named: Text("Переместить проект выше")) { moveBy(-1) }
            .accessibilityAction(named: Text("Переместить проект ниже")) { moveBy(1) }
            .contextMenu {
                Button("Переместить выше") { moveBy(-1) }.disabled(neighbour(-1) == nil || app.operationBusy)
                Button("Переместить ниже") { moveBy(1) }.disabled(neighbour(1) == nil || app.operationBusy)
            }
    }

    private func neighbour(_ offset: Int) -> String? {
        let ids = order.groups(app.visibleConversations).map(\.id)
        guard let index = ids.firstIndex(of: group.id), ids.indices.contains(index + offset) else { return nil }
        return ids[index + offset]
    }

    private func moveBy(_ offset: Int) {
        guard !app.operationBusy, !app.privateBackupRestartRequired, let target = neighbour(offset) else { return }
        order.move(.init(id: group.id, owner: order.owner), to: target, after: offset > 0, conversations: app.listedConversations)
    }
}

struct SidebarProjectDragPreview: View {
    let title: String
    let count: Int

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "folder").font(.system(size: 17)).foregroundStyle(.secondary)
            Text(title).font(.system(size: 13, weight: .medium)).lineLimit(1)
            Text(count.formatted()).font(.system(size: 11)).foregroundStyle(.secondary)
                .padding(.horizontal, 6).padding(.vertical, 3)
                .background(Color.primary.opacity(0.06), in: Capsule())
        }.padding(.horizontal, 13).padding(.vertical, 11)
            .frame(maxWidth: 260)
            .background(NativeTheme.sidebar, in: RoundedRectangle(cornerRadius: 11))
            .overlay(RoundedRectangle(cornerRadius: 11).strokeBorder(Color.primary.opacity(0.12)))
    }
}
