import SwiftUI

struct ConversationWelcomeView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            Image(systemName: "cube.transparent.fill")
                .font(.system(size: 32, weight: .light)).foregroundStyle(NativeTheme.accent)
                .frame(width: 62, height: 62).background(NativeTheme.accent.opacity(0.09), in: RoundedRectangle(cornerRadius: 18))
            VStack(alignment: .leading, spacing: 11) {
                Text("Чем займёмся?").font(.system(size: 34, weight: .semibold))
                Text("Разберём идею, поработаем над проектом\nили вспомним важное.")
                    .font(.system(size: 16)).foregroundStyle(.secondary).lineSpacing(5)
            }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 160), spacing: 12)], alignment: .leading, spacing: 12) {
                card("Вернуться к работе", detail: "Найти и продолжить прежний диалог", icon: "clock.arrow.circlepath") {
                    model.openConversationHistory()
                }
                card("Обсудить идею", detail: "Разложить мысли по полочкам", icon: "lightbulb") {
                    let prompt = "Помоги мне разобраться с идеей: "
                    model.setComposer(model.composer.isEmpty ? prompt : model.composer + "\n" + prompt)
                }
                card("Открыть проект", detail: "Выбрать папку для работы", icon: "folder") { model.chooseWorkspace() }
                card("Вспомнить важное", detail: "Открыть сохранённую память", icon: "brain") {
                    Task {
                        if model.selected?.workspacePath != nil { await model.openProjectMemory() }
                        else { await model.showLibrary(.memory) }
                    }
                }
            }.padding(.top, 6)
            Text("Или просто напишите сообщение ниже.").font(.system(size: 12)).foregroundStyle(.secondary)
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
