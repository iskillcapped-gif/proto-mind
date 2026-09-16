import SwiftUI

struct ConversationPaneView: View {
    @ObservedObject var app: AppModel
    let conversationID: UUID
    @ObservedObject var panel: WorkspacePanelModel

    var body: some View {
        ChatView(model: app, conversationID: conversationID, panel: panel)
    }
}
