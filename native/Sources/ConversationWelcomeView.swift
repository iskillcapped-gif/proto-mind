import SwiftUI

struct ConversationWelcomeView: View {
    @ObservedObject var model: AppModel
    var conversationID: UUID? = nil
    var panel: WorkspacePanelModel? = nil
    @Environment(\.workspacePresentations) private var presentations
    private var context: ConversationComposerContext { ConversationComposerContext(app: model, id: conversationID ?? model.selectedID) }

    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            Image(systemName: "cube.transparent.fill")
                .font(.system(size: 32, weight: .light)).foregroundStyle(NativeTheme.accent)
                .frame(width: 62, height: 62).background(NativeTheme.accent.opacity(0.09), in: RoundedRectangle(cornerRadius: 18))
            VStack(alignment: .leading, spacing: 11) {
                Text(L10n.text("Чем займёмся?")).font(.system(size: 34, weight: .semibold))
                Text(L10n.text("Разберём идею, поработаем над проектом\nили вспомним важное."))
                    .font(.system(size: 16)).foregroundStyle(.secondary).lineSpacing(5)
            }
            // Two columns keep the four cards balanced at every width (an adaptive grid gave 3 + 1).
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(minimum: 130), spacing: 12), count: 2), alignment: .leading, spacing: 12) {
                card(L10n.text("Вернуться к работе"), detail: L10n.text("Найти и продолжить прежний диалог"), icon: "clock.arrow.circlepath") {
                    model.openConversationHistory()
                }
                card(L10n.text("Обсудить идею"), detail: L10n.text("Разложить мысли по полочкам"), icon: "lightbulb") {
                    let prompt = L10n.text("Помоги мне разобраться с идеей: ")
                    context.setDraft(context.draft.isEmpty ? prompt : context.draft + "\n" + prompt)
                }
                card(L10n.text("Открыть проект"), detail: L10n.text("Выбрать папку для работы"), icon: "folder") { if let id = conversationID { model.choosePanelWorkspace(conversationID: id, in: panel) } else { model.chooseWorkspace() } }
                card(L10n.text("Вспомнить важное"), detail: L10n.text("Открыть сохранённую память"), icon: "brain") {
                    Task {
                        if context.conversation?.workspacePath != nil { await model.openProjectMemory(conversationID: context.id, in: presentations) }
                        else if conversationID == nil { await model.showLibrary(.memory) }
                        else if let id = context.id { model.choosePanelWorkspace(conversationID: id, in: panel) }
                    }
                }
            }.padding(.top, 6)
            Text(L10n.text("Или просто напишите сообщение ниже.")).font(.system(size: 12)).foregroundStyle(.secondary)
        }.frame(maxWidth: 620, alignment: .leading).padding(.horizontal, 36).frame(maxWidth: .infinity)
    }

    private func card(_ title: String, detail: String, icon: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 10) {
                Image(systemName: icon).font(.system(size: 19)).foregroundStyle(NativeTheme.accent)
                    .frame(width: 24, height: 24, alignment: .leading)
                Text(title).font(.system(size: 13, weight: .medium))
                Text(detail).font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(2)
            }.frame(maxWidth: .infinity, minHeight: 99, alignment: .topLeading).padding(16)
                .background(NativeTheme.composer, in: RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(NativeTheme.hairline))
        }.buttonStyle(.nativeHover).disabled(context.busy)
    }
}
