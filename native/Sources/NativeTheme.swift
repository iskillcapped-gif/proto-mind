import AppKit
import SwiftUI

enum NativeTheme {
    private static func color(_ light: (CGFloat, CGFloat, CGFloat), _ dark: (CGFloat, CGFloat, CGFloat)) -> Color {
        Color(nsColor: NSColor(name: nil) { appearance in
            let isDark = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            let rgb = isDark ? dark : light
            return NSColor(srgbRed: rgb.0, green: rgb.1, blue: rgb.2, alpha: 1)
        })
    }
    static let canvas = color((1, 1, 1), (0.094, 0.094, 0.094))
    static let sidebar = color((0.95, 0.95, 0.95), (0.215, 0.215, 0.215))
    static let composer = color((0.955, 0.955, 0.955), (0.16, 0.16, 0.16))
    static let bubble = color((0.94, 0.94, 0.94), (0.185, 0.185, 0.185))
    static let selection = color((0.88, 0.88, 0.88), (0.275, 0.275, 0.275))
    static let accent = color((0.16, 0.16, 0.16), (0.95, 0.95, 0.95))
    static let hairline = Color.primary.opacity(0.07)
    static let columnWidth: CGFloat = 752
    static let conversationInset: CGFloat = 50
    static let interfaceSize: CGFloat = 14
    static let codeSize: CGFloat = 12
    static let interfaceFont = Font.system(size: interfaceSize)
    static let messageSize: CGFloat = 15
    static let messageFont = Font.system(size: messageSize)
    static let codeFont = Font.system(size: codeSize, design: .monospaced)
}

struct SidebarMaterial: View {
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    var body: some View {
        Group {
            if reduceTransparency { NativeTheme.sidebar }
            else { SidebarVisualEffect().overlay(NativeTheme.sidebar.opacity(0.82)) }
        }.allowsHitTesting(false).accessibilityHidden(true)
    }
}

struct SidebarVisualEffect: NSViewRepresentable {
    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = .sidebar
        view.blendingMode = .behindWindow
        view.state = .followsWindowActiveState
        return view
    }

    func updateNSView(_ view: NSVisualEffectView, context: Context) {}
}
