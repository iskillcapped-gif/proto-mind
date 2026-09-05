import AppKit
import SwiftUI

enum ModelSelectionPresentation {
    static func width(for label: String) -> CGFloat {
        min(220, ceil((label as NSString).size(withAttributes: [.font: NSFont.systemFont(ofSize: 12, weight: .medium)]).width) + 28)
    }
}

struct ModelSelectionMenu: View {
    @ObservedObject var model: AppModel
    let openSettings: () -> Void
    @State private var open = false
    @State private var section = "model"

    private var isCodex: Bool { model.selected?.provider == "codex" }
    private var title: String {
        isCodex ? "\(model.codexModelLabel) · \(model.reasoningEffortLabel)" : localModelLabel
    }

    var body: some View {
        Button { open.toggle() } label: {
            HStack(spacing: 5) {
                Text(title).lineLimit(1).truncationMode(.middle)
                Image(systemName: "chevron.up").font(.system(size: 9, weight: .semibold))
            }.font(.system(size: 12, weight: .medium))
                .padding(.horizontal, 5)
                .frame(minWidth: 70, idealWidth: ModelSelectionPresentation.width(for: title), maxWidth: ModelSelectionPresentation.width(for: title), minHeight: 32)
                .contentShape(Rectangle())
        }.buttonStyle(.nativeHover).fixedSize(horizontal: false, vertical: true).help(title).disabled(model.busy)
            .accessibilityLabel(isCodex ? "Модель \(model.codexModelLabel), усилие \(model.reasoningEffortLabel)" : "Модель \(localModelLabel)")
            .composerPopover(isPresented: $open, width: 310, trailing: true) {
                VStack(alignment: .leading, spacing: 4) {
                    Picker("Выбор модели", selection: $section) {
                        Text("Модель").tag("model")
                        if isCodex { Text("Глубина").tag("effort") }
                        Text("Источник").tag("provider")
                    }.pickerStyle(.segmented).padding(8)
                    if section == "provider" {
                        provider("Ollama · на этом Mac", id: "ollama")
                        provider("Codex · подписка ChatGPT", id: "codex")
                        provider("Mock · диагностика", id: "mock")
                    } else if isCodex && section == "effort" {
                        ComposerMenuRow(title: model.selectedCodexModel?.defaultEffort.map { "По умолчанию · \($0.title)" } ?? "По умолчанию",
                                        selected: (model.selected?.reasoningEffort ?? "").isEmpty) { model.setReasoningEffort(""); open = false }
                        ForEach(model.availableReasoningEfforts) { effort in
                            ComposerMenuRow(title: effort.title, selected: model.selected?.reasoningEffort == effort.rawValue) {
                                model.setReasoningEffort(effort.rawValue); open = false
                            }
                        }
                    } else if isCodex {
                        ComposerMenuRow(title: "По умолчанию для аккаунта", selected: (model.selected?.model ?? "").isEmpty) { model.setModel(""); open = false }
                        ForEach(model.codexModels) { item in
                            ComposerMenuRow(title: item.displayName, selected: model.selected?.model == item.id) { model.setModel(item.id); open = false }
                        }
                        if let selected = model.selected?.model, !selected.isEmpty, model.selectedCodexModel == nil {
                            Text("\(selected) · недоступна").font(.caption).foregroundStyle(.secondary).padding(10)
                        }
                        Divider().padding(.vertical, 4)
                        ComposerMenuRow(title: "Обновить список", icon: "arrow.clockwise") { Task { await model.refreshAccount() } }
                            .disabled(model.connecting)
                        ComposerMenuRow(title: "Сбросить выбор", icon: "arrow.counterclockwise") { model.resetCodexSelection(); open = false }
                    } else {
                        Text(localModelLabel).font(.system(size: 13)).padding(10)
                    }
                    Divider().padding(.vertical, 4)
                    ComposerMenuRow(title: "Настройки модели…", icon: "slider.horizontal.3") {
                        open = false
                        Task { @MainActor in await Task.yield(); model.settingsSection = .models; openSettings() }
                    }
                }.padding(6)
            }
    }

    private func provider(_ title: String, id: String) -> some View {
        ComposerMenuRow(title: title, selected: model.selected?.provider == id) {
            model.setProvider(id); section = "model"; open = false
        }
    }

    private var localModelLabel: String {
        if model.selected?.provider == "mock" { return "Тестовый режим" }
        let selected = model.selected?.model ?? ""
        return selected.isEmpty ? model.providerLabel : selected
    }
}

struct CodexModelPicker: View {
    @ObservedObject var model: AppModel

    var body: some View {
        Picker("Модель Codex", selection: Binding(get: { model.selected?.model ?? "" }, set: model.setModel)) {
            Text("По умолчанию для аккаунта").tag("")
            ForEach(model.codexModels) { item in Text(item.displayName).tag(item.id) }
            if let selected = model.selected?.model, !selected.isEmpty, model.selectedCodexModel == nil {
                Text("\(selected) · недоступна").tag(selected)
            }
        }.pickerStyle(.inline)
    }
}

struct CodexEffortPicker: View {
    @ObservedObject var model: AppModel

    var body: some View {
        Picker("Усилие рассуждения", selection: Binding(get: { model.selected?.reasoningEffort ?? "" }, set: model.setReasoningEffort)) {
            Text(model.selectedCodexModel?.defaultEffort.map { "По умолчанию · \($0.title)" } ?? "По умолчанию").tag("")
            ForEach(model.availableReasoningEfforts) { effort in Text(effort.title).tag(effort.rawValue) }
            if let selected = model.selected?.reasoningEffort, !selected.isEmpty,
               !model.availableReasoningEfforts.contains(where: { $0.rawValue == selected }) {
                Text("\(selected) · недоступно").tag(selected)
            }
        }.pickerStyle(.inline)
    }
}
