import Foundation

extension NativeChecks {
    @MainActor
    static func multipleCodexAccounts(fixture: URL, service: URL, python: URL, root: URL) async throws {
        let project = root.appendingPathComponent("accounts-project")
        let state = root.appendingPathComponent("accounts-state")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try FileManager.default.copyItem(at: fixture, to: project)
        let subscription = project.appendingPathComponent("proto_mind/steering_fixture.py")
        let fixtureCode = try String(contentsOf: service, encoding: .utf8) + """

class AccountFixtureSubscription(FixtureSubscription):
    def account(self):
        main = self.home.parent.name == 'accounts-state'
        return {'connected': not (self.home.parent / 'signed-out').exists(), 'auth_type': 'chatgpt',
                'plan': 'plus' if main else 'pro', 'email': 'work@example.invalid' if main else 'personal@example.invalid'}
    def models(self):
        values = super().models()
        if self.home.parent.name != 'accounts-state':
            for value in values: value['id'] = value['model'] = 'personal-model'
        return values
    def logout(self):
        self.home.parent.mkdir(parents=True, exist_ok=True)
        (self.home.parent / 'signed-out').write_text('signed out')
        return self.account()
    def reset_thread(self, conversation):
        result = super().reset_thread(conversation)
        self.home.parent.mkdir(parents=True, exist_ok=True)
        with (self.home.parent / 'session-resets').open('a') as log: log.write(str(conversation) + '\\n')
        return result

"""
        try fixtureCode.write(to: subscription, atomically: true, encoding: .utf8)
        let bridge = project.appendingPathComponent("proto_mind/native_bridge.py")
        let code = try String(contentsOf: bridge, encoding: .utf8)
            .replacingOccurrences(of: "class NativeBackend:", with: "from proto_mind.steering_fixture import AccountFixtureSubscription\n\nclass NativeBackend:")
            .replacingOccurrences(of: "subscription_factory=CodexSubscription", with: "subscription_factory=AccountFixtureSubscription")
        try code.write(to: bridge, atomically: true, encoding: .utf8)
        let defaults = UserDefaults(suiteName: "pm-accounts-tests-" + UUID().uuidString)!
        let configuration = LaunchConfiguration(projectRoot: project, python: python, stateDirectory: state)
        let app = AppModel(configuration: configuration, uiDefaults: defaults)
        defer { app.shutdown() }
        await app.start()
        app.setProvider("codex"); app.cloudConsent = true; app.setAutoSkillsEnabled(false)
        let a = app.selectedID!
        let main = app.selectedCodexAccount
        await app.refreshAccount(main)
        let personal = try app.codexAccounts.create(name: "Личный")
        let personalID = personal.accountID!
        let personalState = state.appendingPathComponent("codex-accounts/" + personalID.uuidString.lowercased())
        app.newPanelConversation(in: app.workspacePanels.upper)
        guard case .conversation(let b) = app.workspacePanels.upper.selected?.content else { throw NativeError.message("Missing panel draft") }
        app.selectCodexAccount(personalID, conversationID: b)
        if let index = app.conversations.firstIndex(where: { $0.id == b }) { app.conversations[index].autoSkillsEnabled = false }
        await app.refreshAccount(personal)
        try await accountBoundary { !personal.connecting }
        try check(app.selectedID == a && app.account["email"].text == "work@example.invalid"
                  && personal.account["email"].text == "personal@example.invalid",
                  "Connecting a side chat leaves the main chat on its original ChatGPT account")
        try check(app.codexModels(for: a).first?.id == "gpt-6-astra" && app.codexModels(for: b).first?.id == "personal-model",
                  "Every model menu uses the catalog belonging to its own conversation")
        app.configureConversation(b, model: "gpt-6-astra")
        try check(app.conversations.first(where: { $0.id == b })?.model == "", "Another account's model cannot be selected in the side chat")
        app.configureConversation(b, model: "personal-model")
        try check(app.conversations.first(where: { $0.id == b })?.model == "personal-model", "A side chat accepts its own account's model")
        try FileManager.default.createDirectory(at: personalState, withIntermediateDirectories: true)
        try Data(#"{"primary":12,"weekly":21,"limits_delay":0.15}"#.utf8).write(to: personalState.appendingPathComponent("steering-control.json"))
        await main.usage.refreshLimits(app: app, minimumInterval: 0)
        let read = Task { await personal.usage.refresh(app: app) }
        app.select(b)
        app.select(a)
        await read.value
        try check(main.usage.displaySnapshot?.email == "work@example.invalid"
                  && personal.usage.displaySnapshot?.email == "personal@example.invalid"
                  && main.usage.displaySnapshot?.buckets.first?.windows.first?.usedPercent == 27
                  && personal.usage.displaySnapshot?.buckets.first?.windows.first?.usedPercent == 12,
                  "Late quota results and usage details stay in the original account's cache across navigation")
        app.setComposer("Рабочая задача")
        let first = Task { await app.submit(conversationID: a) }
        try await accountBoundary { app.executions[a]?.updateTarget != nil }
        app.setConversationDraft("Личная задача", id: b)
        let second = Task { await app.submit(conversationID: b) }
        try await accountBoundary { app.executions[b]?.updateTarget != nil }
        let firstExecution = app.executions[a]!, secondExecution = app.executions[b]!
        try check(app.isRunning(a) && app.isRunning(b) && firstExecution.client.codexAccountID == nil
                  && secondExecution.client.codexAccountID == personalID && firstExecution.client !== secondExecution.client,
                  "Two real bridge processes execute simultaneously with separate launch-time account IDs")
        app.selectCodexAccount(nil, conversationID: b)
        await app.logout(personal)
        try check(app.conversations.first(where: { $0.id == b })?.codexAccountID == personalID
                  && !FileManager.default.fileExists(atPath: personalState.appendingPathComponent("signed-out").path),
                  "An active account cannot be replaced or logged out beneath its running turn")
        app.setComposer("Рабочий черновик")
        app.setConversationDraft("Личный черновик", id: b)
        _ = try await app.sendExternalTaskMessage("Уточнение для личной задачи", id: b)
        try await accountBoundary { app.conversations.first(where: { $0.id == b })?.messages.first?.taskUpdates?.first?.state == .accepted }
        try check(!FileManager.default.fileExists(atPath: state.appendingPathComponent("steering-received.jsonl").path)
                  && FileManager.default.fileExists(atPath: personalState.appendingPathComponent("steering-received.jsonl").path),
                  "Steering reaches only the selected task's account transport")
        await app.stop(conversationID: a)
        await first.value
        try check(app.isRunning(b) && secondExecution.client.turnOutstanding, "Stopping the work account's task leaves the personal account running")
        await app.logout(main)
        try check(main.account["connected"] == .bool(false) && personal.account["connected"] == .bool(true)
                  && app.isRunning(b) && app.cloudConsent,
                  "Signing out of one idle account does not stop another account or revoke global cloud consent")
        try Data().write(to: personalState.appendingPathComponent("finish-steering"))
        await second.value
        let finished = app.conversations.first { $0.id == b }!
        try check(finished.messages.last?.role == "assistant" && finished.messages.last?.isError == false
                  && finished.messages.last?.text.contains("Уточнение для личной задачи") == true
                  && app.selectedID == a && app.composer == "Рабочий черновик" && finished.draft == "Личный черновик",
                  "A background reply from another account preserves both editor drafts and main navigation")
        let reopened = AppModel(configuration: configuration, uiDefaults: defaults)
        defer { reopened.shutdown() }
        try check(reopened.conversations.first(where: { $0.id == b })?.codexAccountID == personalID
                  && reopened.codexAccount(for: b).name == "Личный" && reopened.execution(for: b).client.codexAccountID == personalID,
                  "Account choices, names and exact execution namespaces survive history reload")
        let blank = UserDefaults(suiteName: "pm-missing-account-" + UUID().uuidString)!
        let recovered = AppModel(configuration: configuration, uiDefaults: blank)
        defer { recovered.shutdown() }
        try check(recovered.codexAccount(for: b).accountID == personalID
                  && recovered.execution(for: b).client.codexAccountID == personalID,
                  "A restored chat with missing account labels never falls back to the main login")
        secondExecution.sendingUpdate = true
        app.selectCodexAccount(nil, conversationID: b)
        try check(app.execution(for: b) === secondExecution && app.conversations.first(where: { $0.id == b })?.codexAccountID == personalID,
                  "A completed chat still owns its account while a steering receipt is outstanding")
        secondExecution.sendingUpdate = false
        app.selectCodexAccount(nil, conversationID: b)
        try check(app.execution(for: b) !== secondExecution && app.execution(for: b).client.codexAccountID == nil
                  && app.conversations.first(where: { $0.id == b })?.model == ""
                  && app.conversations.first(where: { $0.id == b })?.codexSessionResetPending == true
                  && app.conversations.first(where: { $0.id == b })?.messages == finished.messages,
                  "An explicit idle account change replaces the bridge and model while retaining the chat history")
        let switched = AppModel(configuration: configuration, uiDefaults: defaults)
        defer { switched.shutdown() }
        try check(switched.conversations.first(where: { $0.id == b })?.codexSessionResetPending == true,
                  "A required provider-session reset survives restart before the next message")
        await Task.yield()
        try await accountBoundary { !main.connecting }
        let rpcLog = state.appendingPathComponent("steering-rpc.jsonl")
        let before = try Data(contentsOf: rpcLog)
        try await app.prepareConversationAccount(app.execution(for: b))
        let resetLog = state.appendingPathComponent("session-resets")
        let resets = try String(contentsOf: resetLog, encoding: .utf8)
        let after = try Data(contentsOf: rpcLog)
        try check(app.conversations.first(where: { $0.id == b })?.codexSessionResetPending == nil
                  && resets.split(separator: "\n").last.map(String.init) == b.uuidString.lowercased()
                  && after == before,
                  "Returning to an account clears only its local stale binding before a provider call")
        try await app.prepareConversationAccount(app.execution(for: b))
        try check(try String(contentsOf: resetLog, encoding: .utf8) == resets,
                  "A prepared account session is not reset again on the following message")
    }

    @MainActor private static func accountBoundary(_ condition: () -> Bool) async throws {
        let deadline = Date().addingTimeInterval(20)
        while !condition(), Date() < deadline { try await Task.sleep(for: .milliseconds(20)) }
        guard condition() else { throw NativeError.message("Account fixture did not reach its boundary") }
    }
}
