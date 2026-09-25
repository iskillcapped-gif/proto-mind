import SwiftUI

struct ClaudeModelChoices: View {
    @ObservedObject var app: AppModel
    @ObservedObject var account: ClaudeAccountModel
    let conversationID: UUID?
    let close: () -> Void
    @State private var effortTab = false
    @State private var custom = false
    @State private var customID = ""
    private var context: ConversationComposerContext { ConversationComposerContext(app: app, id: conversationID) }
    private var selection: String { context.conversation?.model ?? "" }
    private var option: ClaudeModelOption? { account.snapshot?.model(selection) }

    var body: some View {
        VStack(spacing: 7) {
            HStack(spacing: 4) {
                tab(L10n.text("Модель"), icon: "sparkle", effort: false)
                tab(L10n.text("Усилие"), icon: "slider.horizontal.3", effort: true)
            }.padding(4).background(.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 11))
            if effortTab {
                row(L10n.text("Авто"), selected: (context.conversation?.reasoningEffort ?? "").isEmpty) { context.setEffort(""); close() }
                ForEach(option?.efforts ?? [], id: \.self) { effort in
                    row(ClaudeSelection.effortTitle(effort), selected: context.conversation?.reasoningEffort == effort) {
                        context.setEffort(effort); close()
                    }
                }
                if option?.efforts.isEmpty != false {
                    Text(L10n.pick("Для этой модели Claude Code не указал уровни усилия.", "Claude Code did not list effort levels for this model."))
                        .font(.caption).foregroundStyle(.secondary).padding(8)
                }
            } else {
                row(L10n.text("Автоматически"), subtitle: account.snapshot?.model("").map { "\($0.title) · " + L10n.text("По умолчанию для аккаунта") }, selected: selection.isEmpty) {
                    context.setModel(""); close()
                }
                ForEach(account.snapshot?.models.filter { !$0.isDefault } ?? []) { item in
                    row(item.title, subtitle: item.description, selected: item.matches(selection)) {
                        context.setModel(item.id); close()
                    }
                }
                if !selection.isEmpty, option == nil {
                    row(account.label(for: selection), subtitle: L10n.pick("Свой ID · доступность не подтверждена", "Custom ID · availability unconfirmed"), selected: true) { close() }
                }
                if account.snapshot?.models.isEmpty != false {
                    Text(account.refreshing ? L10n.text("Обновляю…") : L10n.pick("Каталог Claude пока недоступен. Проверьте подключение.", "Claude's catalog is unavailable. Check the connection."))
                        .font(.caption).foregroundStyle(.secondary).padding(8)
                } else if account.error != nil || account.snapshot?.modelsError.isEmpty == false {
                    Text(L10n.pick("Не удалось обновить каталог. Показаны последние данные.", "Could not refresh the catalog. Showing the last reading."))
                        .font(.caption).foregroundStyle(.secondary).padding(8)
                }
                Button { custom.toggle(); customID = selection } label: {
                    HStack { Text(L10n.pick("Указать ID модели…", "Enter a model ID…")); Spacer(); Image(systemName: custom ? "chevron.up" : "chevron.down") }
                        .font(.system(size: 11)).foregroundStyle(.secondary).padding(10).contentShape(Rectangle())
                }.buttonStyle(.nativeHover)
                if custom {
                    HStack {
                        TextField("claude-…", text: $customID).textFieldStyle(.roundedBorder).onSubmit(applyCustom)
                        Button(action: applyCustom) { Image(systemName: "checkmark") }.disabled(customID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }.padding(.horizontal, 8)
                }
            }
        }.task { await account.refresh(app: app) }
    }
    private func applyCustom() {
        let value = customID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return }
        context.setModel(value); close()
    }
    private func tab(_ title: String, icon: String, effort: Bool) -> some View {
        Button { effortTab = effort } label: {
            Label(title, systemImage: icon).font(.system(size: 12, weight: .medium)).frame(maxWidth: .infinity).padding(.vertical, 9)
                .background(effortTab == effort ? NativeTheme.selection : .clear, in: RoundedRectangle(cornerRadius: 8))
        }.buttonStyle(.plain).foregroundStyle(effortTab == effort ? .primary : .secondary)
    }
    private func row(_ title: String, subtitle: String? = nil, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 10) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(title).font(.system(size: 13, weight: selected ? .medium : .regular))
                    if let subtitle, !subtitle.isEmpty { Text(subtitle).font(.system(size: 10.5)).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true) }
                }
                Spacer(minLength: 4)
                Image(systemName: "checkmark").font(.system(size: 11, weight: .semibold)).opacity(selected ? 1 : 0).frame(width: 14)
            }.padding(.horizontal, 11).padding(.vertical, 9).frame(maxWidth: .infinity, alignment: .leading)
                .background(selected ? NativeTheme.selection : .clear, in: RoundedRectangle(cornerRadius: 9)).contentShape(Rectangle())
        }.buttonStyle(.nativeHover).accessibilityAddTraits(selected ? .isSelected : [])
    }
}
