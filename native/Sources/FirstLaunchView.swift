import CryptoKit
import SwiftUI

/// Dismissing the walkthrough is UI state, never consent or an account credential.
enum FirstLaunch {
    static func key(for configuration: LaunchConfiguration) -> String {
        let digest = SHA256.hash(data: Data(configuration.stateDirectory.standardizedFileURL.path.utf8))
            .map { String(format: "%02x", $0) }.joined()
        return "firstLaunch.v1." + digest
    }

    static func shouldPresent(_ configuration: LaunchConfiguration, defaults: UserDefaults = .standard) -> Bool {
        configuration.isPortable && !defaults.bool(forKey: key(for: configuration))
    }

    static func dismiss(_ configuration: LaunchConfiguration, defaults: UserDefaults = .standard) {
        defaults.set(true, forKey: key(for: configuration))
    }
}

struct FirstLaunchView: View {
    @ObservedObject var model: AppModel
    private var ready: Bool { !model.bootstrap.isNull && model.account["connected"].flag && !model.models.isEmpty && model.cloudConsent }

    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Добро пожаловать в Proto-Mind").font(.title2.weight(.semibold))
                Text("Подключим вашу модель — и можно начинать.").foregroundStyle(.secondary)
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    VStack(alignment: .leading, spacing: 8) {
                        Label(model.bootstrap.isNull ? "Проверяем локальное ядро…" : "Локальное ядро готово",
                              systemImage: model.bootstrap.isNull ? "circle.dotted" : "checkmark.circle")
                            .font(.headline)
                        Text("Диалоги и память сохраняются на этом Mac. У каждого пользователя — свой профиль; замена приложения при обновлении его не удаляет.")
                            .foregroundStyle(.secondary)
                        if model.bootstrap.isNull {
                            Button("Повторить проверку") { Task { await model.refresh() } }.disabled(model.globalBusy)
                        }
                    }
                    Divider()
                    VStack(alignment: .leading, spacing: 10) {
                        Label("Ваш аккаунт ChatGPT", systemImage: model.account["connected"].flag ? "checkmark.circle" : "person.crop.circle")
                            .font(.headline)
                        Text("Для текстовых задач нужен аккаунт с доступом к Codex. Встроенный Codex использует вашу подписку; API-ключ для этого не нужен.")
                            .foregroundStyle(.secondary)
                        if model.account["connected"].flag {
                            Text(model.account["email"].text + " · " + model.account["plan"].text)
                                .textSelection(.enabled)
                            Text(model.models.isEmpty ? "Пока не удалось получить доступные модели. Проверьте вход ещё раз." : "Доступные модели получены.")
                                .font(.callout).foregroundStyle(.secondary)
                        }
                        HStack {
                            Button(model.account["connected"].flag ? "Другой аккаунт…" : "Войти через ChatGPT…") {
                                Task { await model.login() }
                            }
                            Button("Проверить вход") { Task { await model.refreshAccount() } }
                            if model.connecting { ProgressView().controlSize(.small) }
                        }.disabled(model.globalBusy || model.connecting)
                        if model.loginPending {
                            Text("Завершите вход в браузере и вернитесь сюда. Если окно не обновилось, нажмите «Проверить вход».")
                                .font(.callout).foregroundStyle(.secondary)
                        }
                    }
                    Divider()
                    VStack(alignment: .leading, spacing: 8) {
                        Toggle("Разрешить облачную обработку", isOn: $model.cloudConsent).disabled(model.globalBusy)
                        Text("При отправке задачи сообщения, выбранная память и вложения передаются OpenAI. Вход в аккаунт сам по себе этого разрешения не даёт.")
                            .font(.callout).foregroundStyle(.secondary)
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Остальное — когда понадобится").font(.headline)
                        Text("Голос подключается в настройках с вашим OpenAI API-ключом и отдельной оплатой API. Доступ к файлам и Mac включается в диалоге.")
                        if !model.computerUseAvailable {
                            Text("Для управления экраном дополнительно нужен подписанный сервис Computer Use из Codex Desktop. Без него доступны чат и работа с файлами и командами при разрешённом доступе к Mac.")
                        }
                        Text("Можно начать и с локальной моделью Ollama — выберите её в настройках после закрытия этого окна.")
                    }.font(.callout).foregroundStyle(.secondary)
                    if let error = model.error {
                        Label(error, systemImage: "exclamationmark.circle").foregroundStyle(.orange).textSelection(.enabled)
                    }
                }.frame(maxWidth: .infinity, alignment: .leading)
            }
            HStack {
                Button("Настрою позже") { model.showFirstLaunch = false }
                Spacer()
                Button("Начать работу") { model.showFirstLaunch = false }
                    .buttonStyle(.borderedProminent).disabled(!ready || model.connecting)
            }
        }.padding(28).workspacePageSize(width: 650, height: 730)
    }
}
