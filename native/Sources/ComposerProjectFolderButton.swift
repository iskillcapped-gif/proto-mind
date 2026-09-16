import Foundation
import SwiftUI

struct ComposerProjectFolderButton: View {
    let workspacePath: String?
    let choose: () -> Void

    var body: some View {
        Button(action: choose) {
            HStack(spacing: 7) {
                Image(systemName: "folder")
                Text(L10n.text("Папка проекта")).fixedSize()
                if let workspacePath {
                    Text(URL(fileURLWithPath: workspacePath).lastPathComponent)
                        .foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle)
                }
                Image(systemName: "chevron.down").font(.system(size: 9, weight: .medium))
                    .foregroundStyle(.secondary)
            }.font(.system(size: 12, weight: .medium))
                .padding(.horizontal, 11).padding(.vertical, 8)
                .background(Color.primary.opacity(0.045), in: RoundedRectangle(cornerRadius: 9))
                .overlay(RoundedRectangle(cornerRadius: 9).stroke(NativeTheme.hairline))
                .contentShape(RoundedRectangle(cornerRadius: 9))
        }.buttonStyle(.nativeHover)
            .help(workspacePath ?? L10n.text("Выбрать папку проекта"))
            .accessibilityLabel(L10n.text("Папка проекта"))
            .accessibilityValue(workspacePath ?? L10n.text("Выбрать папку проекта"))
    }
}
