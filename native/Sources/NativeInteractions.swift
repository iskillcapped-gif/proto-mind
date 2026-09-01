import SwiftUI

struct NativeHoverState: Equatable {
    let fill: Double
    let border: Double

    init(enabled: Bool, hovered: Bool, pressed: Bool) {
        fill = !enabled ? 0 : pressed ? 0.15 : hovered ? 0.08 : 0
        border = !enabled ? 0 : pressed ? 0.22 : hovered ? 0.13 : 0
    }
}

private struct NativeHoverFeedback: ViewModifier {
    @Environment(\.isEnabled) private var enabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var hovered = false
    var pressed = false

    func body(content: Content) -> some View {
        let state = NativeHoverState(enabled: enabled, hovered: hovered, pressed: pressed)
        content
            .contentShape(RoundedRectangle(cornerRadius: 8))
            .overlay {
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color.primary.opacity(state.fill))
                    .overlay { RoundedRectangle(cornerRadius: 8).strokeBorder(Color.primary.opacity(state.border), lineWidth: 1) }
                    .allowsHitTesting(false).accessibilityHidden(true)
            }
            .onHover { hovered = $0 }
            .animation(reduceMotion ? nil : .easeOut(duration: 0.12), value: state)
    }
}

struct NativeHoverButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .frame(minWidth: 28, minHeight: 28)
            .modifier(NativeHoverFeedback(pressed: configuration.isPressed))
    }
}

extension ButtonStyle where Self == NativeHoverButtonStyle {
    static var nativeHover: NativeHoverButtonStyle { NativeHoverButtonStyle() }
}

extension View {
    func nativeHoverSurface() -> some View { modifier(NativeHoverFeedback()) }
}

struct NativeDisclosureStyle: DisclosureGroupStyle {
    func makeBody(configuration: Configuration) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Button { configuration.isExpanded.toggle() } label: {
                HStack(spacing: 8) {
                    Image(systemName: configuration.isExpanded ? "chevron.down" : "chevron.right")
                        .font(.system(size: 10, weight: .semibold)).foregroundStyle(.secondary)
                    configuration.label
                    Spacer(minLength: 0)
                }
            }.buttonStyle(.nativeHover)
                .accessibilityValue(configuration.isExpanded ? "Развёрнуто" : "Свёрнуто")
            if configuration.isExpanded { configuration.content.padding(.leading, 16) }
        }
    }
}
