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
                    Text("Усилие: \(model.reasoningEffortLabel)")
                }.disabled(model.availableReasoningEfforts.isEmpty && (model.selected?.reasoningEffort.isEmpty ?? true))
                Divider()
                Button("Сбросить модель и усилие", systemImage: "arrow.counterclockwise") { model.resetCodexSelection() }
                    .disabled((model.selected?.model.isEmpty ?? true) && (model.selected?.reasoningEffort.isEmpty ?? true))
                Button("Обновить список моделей", systemImage: "arrow.clockwise") { Task { await model.refreshAccount() } }
                    .disabled(model.connecting)
                Divider()
            }
            Menu("Провайдер") {
                Picker("Провайдер", selection: Binding(get: { model.selected?.provider ?? "ollama" }, set: model.setProvider)) {
                    Text("Ollama · на этом Mac").tag("ollama")
                    Text("Codex · подписка ChatGPT").tag("codex")
                    Text("Mock · локальная диагностика").tag("mock")
                }.pickerStyle(.inline)
            }
            Button("Модели и настройки…", systemImage: "slider.horizontal.3", action: openSettings)
        } label: {
            // AppKit's Menu bridge keeps only the first Text in a composite label.
            Text(isCodex ? "\(model.codexModelLabel) · \(model.reasoningEffortLabel)" : localModelLabel)
                .font(NativeTheme.interfaceFont).lineLimit(1)
        }
        .menuStyle(.borderlessButton)
        // Ask the menu for its intrinsic width before drawing hover feedback.
        .frame(maxWidth: 260, alignment: .trailing).fixedSize(horizontal: true, vertical: true)
        .padding(.horizontal, 8).frame(minHeight: 32)
        .nativeHoverSurface()
        .disabled(model.busy)
        .accessibilityLabel(isCodex ? "Модель \(model.codexModelLabel), усилие \(model.reasoningEffortLabel)" : "Модель \(localModelLabel)")
    }

    private var localModelLabel: String {
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
