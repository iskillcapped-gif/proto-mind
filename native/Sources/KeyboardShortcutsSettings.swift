import SwiftUI

/// Settings → Keys: the keyboard shortcuts of PM in one place, grouped by where they act.
struct KeyboardShortcutsSettings: View {
    private struct Shortcut {
        let title: String
        var detail: String? = nil
        let keys: [String]
    }

    private struct ShortcutGroup {
        let title: String
        let shortcuts: [Shortcut]
        var footer: String? = nil
    }

    private var groups: [ShortcutGroup] {
        [
            ShortcutGroup(title: L10n.pick("Чат", "Chat"), shortcuts: [
                Shortcut(title: L10n.pick("Новый чат", "New chat"), keys: ["⌘N"]),
                Shortcut(title: L10n.pick("Отправить сообщение", "Send message"), keys: ["Return"]),
                Shortcut(title: L10n.pick("Новая строка в сообщении", "New line in a message"), keys: ["⇧Return"]),
                Shortcut(title: L10n.pick("Остановить ответ", "Stop the reply"),
                         detail: L10n.pick("В парящем режиме Esc в поле сообщения сворачивает окно в ядро.",
                                           "In floating mode, Esc in the message field folds the window into the core."),
                         keys: ["Esc"]),
            ]),
            ShortcutGroup(title: L10n.pick("Поиск", "Find"), shortcuts: [
                Shortcut(title: L10n.pick("Найти в открытом чате", "Find in the open chat"), keys: ["⌘F"]),
                Shortcut(title: L10n.pick("Совпадение раньше", "Earlier match"), keys: ["⌘G", "Return", "↑"]),
                Shortcut(title: L10n.pick("Совпадение позже", "Later match"), keys: ["⇧⌘G", "⇧Return", "↓"]),
                Shortcut(title: L10n.pick("Поиск диалогов в боковой панели", "Search conversations in the sidebar"), keys: ["⇧⌘F"]),
            ], footer: L10n.pick("Return, ⇧Return и стрелки работают в поле поиска, Esc закрывает его. Первым показывается самое новое совпадение.",
                                 "Return, ⇧Return and the arrows work in the find field, and Esc closes it. The newest match comes first.")),
            ShortcutGroup(title: L10n.pick("Окна и панели", "Windows and panels"), shortcuts: [
                Shortcut(title: L10n.pick("Парящий режим", "Floating mode"), keys: ["⌥⌘J"]),
                Shortcut(title: L10n.pick("Развернуть или свернуть окно 1 · 2", "Expand or shrink window 1 · 2"), keys: ["⌘1", "⌘2"]),
                Shortcut(title: L10n.pick("Показать или скрыть окно 1 · 2", "Show or hide window 1 · 2"), keys: ["⌥⌘1", "⌥⌘2"]),
                Shortcut(title: L10n.pick("Новая страница в панели", "New page in the panel"), keys: ["⌥⌘T"]),
                Shortcut(title: L10n.pick("Файлы проекта", "Project files"), keys: ["⇧⌘O"]),
                Shortcut(title: L10n.pick("Инспектор ответа", "Response inspector"), keys: ["⌥⌘I"]),
                Shortcut(title: L10n.pick("Каталог команд", "Command catalog"), keys: ["⌘K"]),
            ]),
            ShortcutGroup(title: L10n.pick("Настройки и просмотр", "Settings and viewing"), shortcuts: [
                Shortcut(title: L10n.pick("Настройки", "Settings"), keys: ["⌘,"]),
                Shortcut(title: L10n.pick("Назад к списку подключений", "Back to all connections"), keys: ["⌘["]),
                Shortcut(title: L10n.pick("Закрыть страницу поверх чата", "Close the page over the chat"), keys: ["Esc"]),
                Shortcut(title: L10n.pick("Масштаб картинки", "Zoom a picture"),
                         detail: L10n.pick("Увеличить, уменьшить и вписать; ⌘ с колесом мыши — вокруг указателя.",
                                           "Zoom in, out and fit; ⌘ with the scroll wheel zooms around the pointer."),
                         keys: ["⌘+", "⌘−", "⌘0"]),
            ]),
        ]
    }

    var body: some View {
        ForEach(groups, id: \.title) { group in
            Section {
                ForEach(group.shortcuts, id: \.title) { shortcut in
                    SettingsRow(title: shortcut.title, detail: shortcut.detail) { KeyCaps(keys: shortcut.keys) }
                }
            } header: { Text(group.title) } footer: {
                if let footer = group.footer { SettingsFooter(footer) }
            }
        }
    }
}

/// Keys drawn as small key caps, like the menus show them.
struct KeyCaps: View {
    let keys: [String]

    var body: some View {
        HStack(spacing: 4) {
            ForEach(keys, id: \.self) { key in
                Text(key).font(.system(size: 12, weight: .medium)).monospacedDigit()
                    .padding(.horizontal, 7).padding(.vertical, 2.5)
                    .background(Color.primary.opacity(0.06), in: RoundedRectangle(cornerRadius: 5))
                    .overlay(RoundedRectangle(cornerRadius: 5).stroke(Color.primary.opacity(0.13)))
            }
        }.fixedSize().accessibilityElement(children: .combine)
    }
}
