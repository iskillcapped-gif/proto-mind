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
    static let canvas = color((0.985, 0.986, 0.993), (0.085, 0.093, 0.112))
    static let sidebar = color((0.947, 0.953, 0.974), (0.12, 0.133, 0.16))
    static let composer = color((1, 1, 1), (0.132, 0.145, 0.174))
    static let bubble = color((0.925, 0.939, 0.976), (0.17, 0.19, 0.244))
    static let selection = color((0.87, 0.901, 0.975), (0.21, 0.248, 0.345))
    static let accent = color((0.30, 0.39, 0.78), (0.59, 0.68, 0.98))
    static let hairline = Color.primary.opacity(0.07)
    static let columnWidth: CGFloat = 790
    static let interfaceSize: CGFloat = 14
    static let codeSize: CGFloat = 12
    static let interfaceFont = Font.system(size: interfaceSize)
    static let messageFont = Font.system(size: 15)
    static let codeFont = Font.system(size: codeSize, design: .monospaced)
}

struct SidebarMaterial: View {
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    var body: some View {
        Group {
            if reduceTransparency { NativeTheme.sidebar }
            else { SidebarVisualEffect().overlay(NativeTheme.sidebar.opacity(0.28)) }
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
