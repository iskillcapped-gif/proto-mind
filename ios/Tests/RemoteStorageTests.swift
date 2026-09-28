import XCTest
@testable import ProtoMindRemote

final class RemoteStorageTests: XCTestCase {
    func testDeviceKeychainRoundTripAndRemoval() throws {
        let service = "com.virencore.protomind.remote.tests." + UUID().uuidString
        let storage = RemoteStorage(service: service)
        defer { try? storage.save(connection: nil) }
        XCTAssertNil(try storage.connection())
        let token = try RemoteStorage.token()
        XCTAssertTrue(MobileWire.validSecret(token))
        let connection = RemoteConnection(endpoint: "https://fixture.invalid", deviceID: UUID(), token: token)
        try storage.save(connection: connection)
        XCTAssertEqual(try RemoteStorage(service: service).connection(), connection)
        let replacement = RemoteConnection(endpoint: connection.endpoint, deviceID: connection.deviceID, token: try RemoteStorage.token())
        try storage.save(connection: replacement)
        XCTAssertEqual(try storage.connection(), replacement)
        try storage.save(connection: nil)
        XCTAssertNil(try storage.connection())
    }

    func testDraftAndPendingCommandSurviveReload() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("pm-storage-test-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let storage = RemoteStorage(directory: directory)
        let chat = UUID()
        let command = MobileCommand(id: UUID(), conversationID: chat, kind: .send, text: "Keep this draft", expectedRunID: nil, createdAt: Date())
        let value = RemoteLocalState(drafts: [chat.uuidString: command.text], pending: command)
        try storage.save(state: value)
        let restored = try RemoteStorage(directory: directory).load()
        XCTAssertEqual(restored.drafts, value.drafts)
        XCTAssertEqual(restored.pending?.fingerprint, command.fingerprint)
        XCTAssertEqual(try directory.resourceValues(forKeys: [.isExcludedFromBackupKey]).isExcludedFromBackup, true)
        let file = directory.appendingPathComponent("drafts.json")
        try Data("broken".utf8).write(to: file)
        XCTAssertThrowsError(try storage.load())
    }

    func testDraftFileProtectionOnPhysicalDevice() throws {
        #if targetEnvironment(simulator)
        throw XCTSkip("File protection must be verified on a physical iPhone.")
        #else
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("pm-protection-test-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        try RemoteStorage(directory: directory).save(state: RemoteLocalState())
        let file = directory.appendingPathComponent("drafts.json")
        XCTAssertEqual(try FileManager.default.attributesOfItem(atPath: file.path)[.protectionKey] as? FileProtectionType, .complete)
        #endif
    }
}
