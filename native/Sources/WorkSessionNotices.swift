import SwiftUI

// A display preference for one observed revision, never a run/acceptance receipt.
struct NativeWorkSessionNotice: Codable, Equatable {
    let runID: UUID
    let fingerprint: String
    let state: String

    init(_ run: NativeWorkSession) throws {
        guard let id = UUID(uuidString: run.id), run.needsReview else {
            throw NativeError.message("Скрывать можно только уведомление о прошлом незавершённом запуске.")
        }
        runID = id; fingerprint = run.value["fingerprint"].text; state = run.state
        try Self.validate([self])
    }

    func matches(_ run: NativeWorkSession) -> Bool {
        runID == UUID(uuidString: run.id) && fingerprint == run.value["fingerprint"].text && state == run.state
    }

    static func validate(_ notices: [Self]) throws {
        guard notices.count <= 500, Set(notices.map(\.runID)).count == notices.count,
              notices.allSatisfy({ ["unknown", "not_started"].contains($0.state)
                  && $0.fingerprint.count == 64 && $0.fingerprint.allSatisfy({ "0123456789abcdef".contains($0) }) }) else {
            throw NativeError.message("Настройки уведомлений журнала не прошли проверку. История не изменена.")
        }
    }
}

struct WorkSessionNoticeControls: View {
    @ObservedObject var model: AppModel
    let run: NativeWorkSession
    @State private var error: String?

    var body: some View {
        if run.needsReview {
            VStack(alignment: .leading, spacing: 8) {
                let hidden = model.isWorkSessionWarningHidden(run)
                Text(hidden ? "Уведомление об этом запуске скрыто в чате." : "Этот запуск показывает уведомление в чате.")
                    .font(.callout).foregroundStyle(.secondary)
                Button(hidden ? "Показывать уведомление" : "Скрыть уведомление") {
                    do { try model.setWorkSessionWarningHidden(run, hidden: !hidden); error = nil }
                    catch { self.error = error.localizedDescription }
                }.disabled(model.busy || model.loadingWorkSessions || model.client.turnOutstanding)
                    .help("Только показ в чате. Не удаляет запуск, не принимает результат и ничего не повторяет.")
                Text("Сохранится после перезапуска. Запись и её статус останутся в журнале; новые или изменившиеся предупреждения появятся снова.")
                    .font(.caption).foregroundStyle(.secondary)
                if let error { Text(error).font(.callout).foregroundStyle(.orange).textSelection(.enabled) }
            }
        }
    }
}

struct WorkSessionNoticeBanner: View {
    @ObservedObject var model: AppModel

    var body: some View {
        if !model.busy, model.hasWorkSessionNotice {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 4) {
                    Label(model.workSessionsWarning == nil ? "Есть прошлый запрос без подтверждённого результата." : "Журнал работы требует проверки. Откройте диагностику перед новым запросом.", systemImage: "exclamationmark.circle")
                        .font(.callout).foregroundStyle(.orange)
                    if model.workSessionsWarning == nil, let run = model.workSessionNoticeToShow {
                        Text("\(run.title): \(run.value["input_preview"].text)").font(.caption).foregroundStyle(.secondary).lineLimit(2)
                    }
                }
                Spacer()
                Button("Открыть журнал") { model.openWorkSessions(model.workSessionNoticeToShow) }
                if model.workSessionsWarning == nil, let run = model.workSessionNoticeToShow {
                    Button {
                        do { try model.setWorkSessionWarningHidden(run, hidden: true) }
                        catch { model.error = error.localizedDescription }
                    } label: { Image(systemName: "xmark") }
                        .disabled(model.loadingWorkSessions || model.client.turnOutstanding)
                        .accessibilityLabel("Скрыть уведомление о прошлом запуске")
                        .help("Скрыть только это уведомление. Запуск остаётся в журнале и не считается принятым.")
                }
            }.padding(.horizontal, 28).padding(.vertical, 10).background(Color.orange.opacity(0.05))
        }
    }
}
