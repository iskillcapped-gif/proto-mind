import AppKit
import SwiftUI

enum NativeTheme {
    private static func color(_ light: CGFloat, _ dark: CGFloat) -> Color {
        Color(nsColor: NSColor(name: nil) { appearance in
            let isDark = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            return NSColor(white: isDark ? dark : light, alpha: 1)
        })
    }
    static let canvas = color(0.99, 0.095)
    static let sidebar = color(0.95, 0.16)
    static let composer = color(0.95, 0.15)
    static let bubble = color(0.94, 0.18)
    static let selection = color(0.89, 0.23)
    static let hairline = Color.primary.opacity(0.07)
    static let columnWidth: CGFloat = 830
    static let interfaceSize: CGFloat = 14
    static let codeSize: CGFloat = 12
    static let interfaceFont = Font.system(size: interfaceSize)
    static let codeFont = Font.system(size: codeSize, design: .monospaced)
}

struct SidebarMaterial: View {
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    var body: some View {
        Group {
            if reduceTransparency { NativeTheme.sidebar }
            else { SidebarVisualEffect() }
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
