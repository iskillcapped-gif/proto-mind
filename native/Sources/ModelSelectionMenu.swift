import SwiftUI

struct ModelSelectionMenu: View {
    @ObservedObject var model: AppModel
    let openSettings: () -> Void

    private var isCodex: Bool { model.selected?.provider == "codex" }

    var body: some View {
        Menu {
            if isCodex {
                Menu {
                    CodexModelPicker(model: model)
                } label: {
                    Text("Модель: \(model.codexModelLabel)")
                }
                Menu {
                    CodexEffortPicker(model: model)
                } label: {
                    Text("Глубина: \(model.reasoningEffortLabel)")
                }.disabled(model.availableReasoningEfforts.isEmpty && (model.selected?.reasoningEffort.isEmpty ?? true))
                Divider()
                Button("Сбросить выбор", systemImage: "arrow.counterclockwise") { model.resetCodexSelection() }
                    .disabled((model.selected?.model.isEmpty ?? true) && (model.selected?.reasoningEffort.isEmpty ?? true))
                Button("Обновить список моделей", systemImage: "arrow.clockwise") { Task { await model.refreshAccount() } }
                    .disabled(model.connecting)
                Divider()
            }
            Menu("Источник модели") {
                Picker("Провайдер", selection: Binding(get: { model.selected?.provider ?? "ollama" }, set: model.setProvider)) {
                    Text("Ollama · на этом Mac").tag("ollama")
                    Text("Codex · подписка ChatGPT").tag("codex")
                    Text("Mock · локальная диагностика").tag("mock")
                }.pickerStyle(.inline)
            }
            Button("Настройки модели…", systemImage: "slider.horizontal.3") { model.settingsSection = .models; openSettings() }
        } label: {
            // AppKit's Menu bridge keeps only the first Text in a composite label.
            Text(isCodex ? "\(model.codexModelLabel) · \(model.reasoningEffortLabel)" : localModelLabel)
                .font(.system(size: 12, weight: .medium)).lineLimit(1).truncationMode(.middle)
        }
        .menuStyle(.borderlessButton)
        // Long catalog names must leave room for the send and access controls.
        .frame(maxWidth: 200, alignment: .leading).fixedSize(horizontal: false, vertical: true)
        .padding(.horizontal, 5).frame(minHeight: 32)
        .nativeHoverSurface()
        .help(isCodex ? "\(model.codexModelLabel) · \(model.reasoningEffortLabel)" : localModelLabel)
        .disabled(model.busy)
        .accessibilityLabel(isCodex ? "Модель \(model.codexModelLabel), усилие \(model.reasoningEffortLabel)" : "Модель \(localModelLabel)")
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
