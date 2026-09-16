import AppKit
import SwiftUI

enum ModelSelectionPresentation {
    @MainActor static func localLabel(_ model: AppModel) -> String {
        if model.selected?.provider == "mock" { return L10n.text("Тестовый режим") }
        let selected = model.selected?.model ?? ""
        return selected.isEmpty ? model.providerLabel : selected
    }

    static func width(for label: String) -> CGFloat {
        min(220, ceil((label as NSString).size(withAttributes: [.font: NSFont.systemFont(ofSize: 12, weight: .medium)]).width) + 28)
    }
}

struct ModelSelectionMenu: View {
    @ObservedObject var model: AppModel
    var conversationID: UUID? = nil
    private var context: ConversationComposerContext { ConversationComposerContext(app: model, id: conversationID ?? model.selectedID) }
    let openSettings: () -> Void
    @State private var open = false

    private var isCodex: Bool { context.conversation?.provider == "codex" }
    private var accountPrefix: String { isCodex && model.codexAccounts.items.count > 1 ? model.codexAccount(for: context.id).shortName + " · " : "" }
    private var title: String {
        isCodex ? "\(accountPrefix)\(context.modelLabel) · \(context.effortLabel)" : localModelLabel
    }
    private var styledTitle: Text {
        let effort = Text(" · \(context.effortLabel)").foregroundColor(.secondary)
        let account = Text(accountPrefix).foregroundColor(.secondary)
        return isCodex
            ? Text("\(account)\(context.modelLabel)\(effort)")
            : Text(localModelLabel)
    }

    var body: some View {
        Button { open.toggle() } label: {
            HStack(spacing: 5) {
                styledTitle.lineLimit(1).truncationMode(.middle)
                Image(systemName: "chevron.up").font(.system(size: 9, weight: .semibold))
            }.font(.system(size: 12, weight: .medium))
                .padding(.horizontal, 5)
                .frame(minWidth: 70, idealWidth: ModelSelectionPresentation.width(for: title), maxWidth: ModelSelectionPresentation.width(for: title), minHeight: 32)
                .contentShape(Rectangle())
        }.buttonStyle(.nativeHover).fixedSize(horizontal: false, vertical: true).help(title).disabled(context.busy)
            .accessibilityLabel(isCodex ? L10n.pick("Модель \(context.modelLabel), усилие \(context.effortLabel)", "Model \(context.modelLabel), effort \(context.effortLabel)") : L10n.pick("Модель \(localModelLabel)", "Model \(localModelLabel)"))
            .composerPopover(isPresented: $open, width: 326, trailing: true) {
                ModelSelectionChoices(model: model, conversationID: context.id, open: $open, openSettings: openSettings)
            }
    }

    private var localModelLabel: String { context.localLabel }
}

struct ModelSelectionChoices: View {
    @ObservedObject var model: AppModel
    var conversationID: UUID? = nil
    private var context: ConversationComposerContext { ConversationComposerContext(app: model, id: conversationID ?? model.selectedID) }
    @Binding var open: Bool
    let openSettings: () -> Void
    @State private var section = "model"
    private var isCodex: Bool { context.conversation?.provider == "codex" }
    private var localModelLabel: String { context.localLabel }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text(isCodex ? "ChatGPT" : context.providerLabel).font(.system(size: 14, weight: .semibold))
                    Text(L10n.text("Для этого диалога")).font(.system(size: 11)).foregroundStyle(.secondary)
                }
                Spacer()
                if isCodex {
                    Button { Task { await model.refreshAccount( model.codexAccount(for: context.id)) } } label: {
                        Image(systemName: "arrow.clockwise").frame(width: 28, height: 28)
                    }.buttonStyle(.nativeHover).foregroundStyle(.secondary)
                        .disabled(model.connecting).help(L10n.text("Обновить доступные модели"))
                }
            }.padding(.horizontal, 8).padding(.top, 6)
            if isCodex, let id = context.id {
                ConversationAccountPicker(app: model, conversationID: id) { open = false }
            }
            if isCodex {
                HStack(spacing: 4) {
                    tab(L10n.text("Модель"), icon: "sparkle", id: "model")
                    tab(L10n.text("Усилие"), icon: "slider.horizontal.3", id: "effort")
                }.padding(4).background(.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 11))
            }
            VStack(spacing: 3) {
                if isCodex && section == "effort" {
                    choice(L10n.text("По умолчанию"), subtitle: context.selectedModel?.defaultEffort?.title,
                           selected: (context.conversation?.reasoningEffort ?? "").isEmpty) {
                        context.setEffort(""); open = false
                    }
                    ForEach((context.selectedModel?.efforts ?? [])) { effort in
                        choice(effort.title, selected: context.conversation?.reasoningEffort == effort.rawValue, effort: effort) {
                            context.setEffort(effort.rawValue); open = false
                        }
                    }
                    if let selected = context.conversation?.reasoningEffort, !selected.isEmpty,
                       !(context.selectedModel?.efforts ?? []).contains(where: { $0.rawValue == selected }) {
                        Text(L10n.text("Выбранное усилие сейчас недоступно")).font(.caption).foregroundStyle(.secondary).padding(10)
                    }
                } else if isCodex {
                    choice(L10n.text("Автоматически"), subtitle: L10n.text("По умолчанию для аккаунта"), selected: (context.conversation?.model ?? "").isEmpty) {
                        context.setModel(""); open = false
                    }
                    ForEach(context.models) { item in
                        choice(item.displayName, selected: context.conversation?.model == item.id) {
                            context.setModel(item.id); open = false
                        }
                    }
                    if let selected = context.conversation?.model, !selected.isEmpty, context.selectedModel == nil {
                        Text(L10n.format("\(selected) · недоступна")).font(.caption).foregroundStyle(.secondary).padding(10)
                    }
                } else {
                    choice(localModelLabel, selected: true) { open = false }
                }
            }.disabled(context.busy)
            Divider().opacity(0.5)
            if let id = context.id {
                ConversationProviderChoices(app: model, connections: model.apiConnections, conversationID: id) { open = false }
            }
            ComposerMenuRow(title: L10n.text("Настройки модели"), icon: "slider.horizontal.3") {
                open = false
                Task { @MainActor in await Task.yield(); model.settingsSection = .models; openSettings() }
            }.foregroundStyle(.secondary)
        }.padding(10)
    }

    private func tab(_ title: String, icon: String, id: String) -> some View {
        Button { section = id } label: {
            Label(title, systemImage: icon).font(.system(size: 12, weight: .medium))
                .frame(maxWidth: .infinity).padding(.vertical, 9)
                .background(section == id ? NativeTheme.selection : .clear, in: RoundedRectangle(cornerRadius: 8))
        }.buttonStyle(.plain).foregroundStyle(section == id ? .primary : .secondary)
            .accessibilityAddTraits(section == id ? .isSelected : [])
    }

    private func choice(_ title: String, subtitle: String? = nil, selected: Bool,
                        effort: CodexReasoningEffort? = nil, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 10) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(title).font(.system(size: 13, weight: selected ? .medium : .regular))
                    if let subtitle { Text(subtitle).font(.system(size: 11)).foregroundStyle(.secondary) }
                }
                Spacer(minLength: 8)
                if let effort, let rank = CodexReasoningEffort.allCases.firstIndex(of: effort) {
                    HStack(spacing: 3) {
                        ForEach(0..<CodexReasoningEffort.allCases.count, id: \.self) { step in
                            Capsule().fill(.primary.opacity(step <= rank ? 0.5 : 0.1)).frame(width: 3, height: 10)
                        }
                    }.accessibilityHidden(true)
                }
                Image(systemName: "checkmark").font(.system(size: 11, weight: .semibold))
                    .opacity(selected ? 1 : 0).frame(width: 14)
            }.padding(.horizontal, 11).padding(.vertical, 10).frame(maxWidth: .infinity, alignment: .leading)
                .background(selected ? NativeTheme.selection : .clear, in: RoundedRectangle(cornerRadius: 9))
                .contentShape(RoundedRectangle(cornerRadius: 9))
        }.buttonStyle(.nativeHover).accessibilityAddTraits(selected ? .isSelected : [])
    }


}

struct CodexModelPicker: View {
    @ObservedObject var model: AppModel

    var body: some View {
        Picker(L10n.text("Модель Codex"), selection: Binding(get: { model.selected?.model ?? "" }, set: model.setModel)) {
            Text(L10n.text("По умолчанию для аккаунта")).tag("")
            ForEach(model.codexModels) { item in Text(item.displayName).tag(item.id) }
            if let selected = model.selected?.model, !selected.isEmpty, model.selectedCodexModel == nil {
                Text(L10n.format("\(selected) · недоступна")).tag(selected)
            }
        }.pickerStyle(.inline)
    }
}

struct CodexEffortPicker: View {
    @ObservedObject var model: AppModel

    var body: some View {
        Picker(L10n.text("Усилие рассуждения"), selection: Binding(get: { model.selected?.reasoningEffort ?? "" }, set: model.setReasoningEffort)) {
            Text(model.selectedCodexModel?.defaultEffort.map { L10n.format("По умолчанию · \($0.title)") } ?? L10n.text("По умолчанию")).tag("")
            ForEach(model.availableReasoningEfforts) { effort in Text(effort.title).tag(effort.rawValue) }
            if let selected = model.selected?.reasoningEffort, !selected.isEmpty,
               !model.availableReasoningEfforts.contains(where: { $0.rawValue == selected }) {
                Text(L10n.format("\(selected) · недоступно")).tag(selected)
            }
        }.pickerStyle(.inline)
    }
}
