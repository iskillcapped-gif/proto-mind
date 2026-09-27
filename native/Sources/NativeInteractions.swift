import SwiftUI

struct NativeHoverState: Equatable {
    let fill: Double
    let border: Double

    init(enabled: Bool, hovered: Bool, pressed: Bool) {
        fill = !enabled ? 0 : pressed ? 0.15 : hovered ? 0.08 : 0
        border = !enabled ? 0 : pressed ? 0.22 : hovered ? 0.13 : 0
    }
}

enum NativeInteractionPerformance {
    // Animated hover transitions can queue faster than SwiftUI can retire them while
    // controls move beneath a stationary pointer during transcript scrolling.
    static let hoverAnimationEnabled = false
}

private struct NativeHoverFeedback: ViewModifier {
    @Environment(\.isEnabled) private var enabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var hovered = false
    var pressed = false
    var cornerRadius: CGFloat = 8

    func body(content: Content) -> some View {
        let state = NativeHoverState(enabled: enabled, hovered: hovered, pressed: pressed)
        let animation: Animation? = NativeInteractionPerformance.hoverAnimationEnabled && !reduceMotion
            ? .easeOut(duration: 0.12) : nil
        content
            .contentShape(RoundedRectangle(cornerRadius: cornerRadius))
            .overlay {
                RoundedRectangle(cornerRadius: cornerRadius)
                    .fill(Color.primary.opacity(state.fill))
                    .overlay { RoundedRectangle(cornerRadius: cornerRadius).strokeBorder(Color.primary.opacity(state.border), lineWidth: 1) }
                    .allowsHitTesting(false).accessibilityHidden(true)
            }
            .onHover { next in
                if hovered != next { hovered = next }
            }
            .animation(animation, value: state)
    }
}

struct NativeHoverButtonStyle: ButtonStyle {
    var minSize: CGFloat = 28
    var cornerRadius: CGFloat = 8

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .frame(minWidth: minSize, minHeight: minSize)
            .modifier(NativeHoverFeedback(pressed: configuration.isPressed, cornerRadius: cornerRadius))
    }
}

extension ButtonStyle where Self == NativeHoverButtonStyle {
    static var nativeHover: NativeHoverButtonStyle { NativeHoverButtonStyle() }
    /// The same feedback for small controls, such as the buttons around the desktop cube.
    static func nativeHover(minSize: CGFloat, cornerRadius: CGFloat = 6) -> NativeHoverButtonStyle {
        NativeHoverButtonStyle(minSize: minSize, cornerRadius: cornerRadius)
    }
}

extension View {
    func nativeHoverSurface() -> some View { modifier(NativeHoverFeedback()) }
}

/// Inline disclosure text, such as a work status or a tool-group summary: only the words are
/// clickable, and hovering gently brightens the letters themselves, with no row highlight.
struct NativeTextButtonStyle: ButtonStyle {
    var color: Color = .secondary
    var hover: Color = .primary.opacity(0.85)

    func makeBody(configuration: Configuration) -> some View {
        NativeTextButtonLabel(label: configuration.label, color: color, hover: hover, pressed: configuration.isPressed)
    }
}

private struct NativeTextButtonLabel<Label: View>: View {
    let label: Label
    let color: Color
    let hover: Color
    let pressed: Bool
    @Environment(\.isEnabled) private var enabled
    @State private var hovered = false

    var body: some View {
        label
            .foregroundStyle(enabled && hovered ? hover : color)
            .opacity(pressed ? 0.75 : 1)
            .contentShape(Rectangle())
            .onHover { next in if hovered != next { hovered = next } }
    }
}

extension ButtonStyle where Self == NativeTextButtonStyle {
    static var nativeText: NativeTextButtonStyle { NativeTextButtonStyle() }
    static func nativeText(_ color: Color, hover: Color) -> NativeTextButtonStyle { NativeTextButtonStyle(color: color, hover: hover) }
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
                .accessibilityValue(configuration.isExpanded ? L10n.text("Развёрнуто") : L10n.text("Свёрнуто"))
            if configuration.isExpanded { configuration.content.padding(.leading, 16) }
        }
    }
}
