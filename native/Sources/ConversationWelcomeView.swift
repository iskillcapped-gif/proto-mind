import SwiftUI

struct ConversationWelcomeView: View {
    @ObservedObject var model: AppModel

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
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 160), spacing: 12)], alignment: .leading, spacing: 12) {
                card(L10n.text("Вернуться к работе"), detail: L10n.text("Найти и продолжить прежний диалог"), icon: "clock.arrow.circlepath") {
                    model.openConversationHistory()
                }
                card(L10n.text("Обсудить идею"), detail: L10n.text("Разложить мысли по полочкам"), icon: "lightbulb") {
                    let prompt = L10n.text("Помоги мне разобраться с идеей: ")
                    model.setComposer(model.composer.isEmpty ? prompt : model.composer + "\n" + prompt)
                }
                card(L10n.text("Открыть проект"), detail: L10n.text("Выбрать папку для работы"), icon: "folder") { model.chooseWorkspace() }
                card(L10n.text("Вспомнить важное"), detail: L10n.text("Открыть сохранённую память"), icon: "brain") {
                    Task {
                        if model.selected?.workspacePath != nil { await model.openProjectMemory() }
                        else { await model.showLibrary(.memory) }
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
                Text(title).font(.system(size: 13, weight: .medium))
                Text(detail).font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(2)
            }.frame(maxWidth: .infinity, minHeight: 99, alignment: .topLeading).padding(16)
                .background(NativeTheme.composer, in: RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(NativeTheme.hairline))
        }.buttonStyle(.nativeHover).disabled(model.busy)
    }
}
