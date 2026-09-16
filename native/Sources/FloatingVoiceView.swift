import AppKit
import SwiftUI

final class DesktopVoicePanel: NSPanel {
    var onClose: (() -> Void)?
    override var canBecomeMain: Bool { false }
    override func close() { orderOut(nil); onClose?() }
}

struct FloatingVoiceView: View {
    @ObservedObject var app: AppModel
    @ObservedObject var voice: LiveVoiceModel
    @ObservedObject var desktop: DesktopPresentation
    var body: some View {
        LiveVoiceView(app: app, voice: voice)
            .background {
                if desktop.enabled { DesktopGlassBackground(transparency: desktop.chatTransparency, tint: NativeTheme.canvas) }
                else { NativeTheme.composer }
            }
            .clipShape(RoundedRectangle(cornerRadius: 18))
            .overlay(RoundedRectangle(cornerRadius: 18).strokeBorder(.white.opacity(0.12)).allowsHitTesting(false))
            .ignoresSafeArea()
            .buttonStyle(.nativeHover).tint(NativeTheme.accent)
            .environment(\.locale, L10n.locale)
    }
}
