import AppKit
import QuartzCore
import SwiftUI

// No continuous animation lives inside a conversation transcript. A SwiftUI TimelineView
// or symbol effect re-rendered the whole transcript on every frame (15-25% of the main
// thread in a long chat), and an AppKit view inside the scrolling content made AppKit
// hit-test the whole transcript for the cursor on every scrolled frame. The transcript
// shows a static mark; the moving spinner stays outside scrolling content (the composer's
// send button and the sidebar), where Core Animation turns it without main-thread work.

/// Static "in progress" mark for rows inside a transcript.
struct WorkingMark: View {
    var body: some View {
        Image(systemName: "circle.dotted").font(.system(size: 13)).frame(width: 15, height: 15).accessibilityHidden(true)
    }
}

/// The moving spinner, for places outside scrolling transcripts.
struct WorkingIndicator: View {
    var size: CGFloat = 15
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        SpinnerRepresentable(animates: !reduceMotion && scenePhase == .active)
            .frame(width: size, height: size).allowsHitTesting(false).accessibilityHidden(true)
    }
}

private struct SpinnerRepresentable: NSViewRepresentable {
    let animates: Bool
    func makeNSView(context: Context) -> WorkingSpinnerView { WorkingSpinnerView() }
    func updateNSView(_ view: WorkingSpinnerView, context: Context) { view.animates = animates }
}

/// Label color at a fraction of its own opacity, like SwiftUI's `.primary.opacity(_:)`.
private func labelTone(_ opacity: CGFloat, in appearance: NSAppearance) -> CGColor {
    var color = CGColor.clear
    appearance.performAsCurrentDrawingAppearance {
        let label = NSColor.labelColor.usingColorSpace(.sRGB) ?? .labelColor
        color = label.withAlphaComponent(label.alphaComponent * opacity).cgColor
    }
    return color
}

/// A faint ring with a gradient arc that turns clockwise once every 1.15 s.
final class WorkingSpinnerView: NSView {
    private let track = CAShapeLayer(), arc = CAShapeLayer(), gradient = CAGradientLayer(), rotor = CALayer()
    private var drawnSize = CGSize.zero
    var animates = true { didSet { if animates != oldValue { restart() } } }

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        layer?.addSublayer(track)
        gradient.type = .conic
        gradient.mask = arc
        rotor.addSublayer(gradient)
        layer?.addSublayer(rotor)
    }

    required init?(coder: NSCoder) { nil }
    override var isFlipped: Bool { true }
    override func hitTest(_ point: NSPoint) -> NSView? { nil }  // Clicks reach the enclosing control.

    override func layout() {
        super.layout()
        guard bounds.size != drawnSize else { return }
        drawnSize = bounds.size
        CATransaction.begin(); CATransaction.setDisableActions(true)
        let lineWidth: CGFloat = 1.7
        let center = CGPoint(x: bounds.midX, y: bounds.midY), radius = max(1, min(bounds.width, bounds.height) / 2 - 1)
        for item in [track, rotor, gradient, arc] as [CALayer] { item.frame = bounds }
        track.path = CGPath(ellipseIn: CGRect(x: center.x - radius, y: center.y - radius, width: radius * 2, height: radius * 2), transform: nil)
        track.lineWidth = lineWidth
        track.fillColor = nil
        let path = CGMutablePath()
        path.addArc(center: center, radius: radius, startAngle: 0, endAngle: .pi * 2 * 0.76, clockwise: false)
        arc.path = path
        arc.lineWidth = lineWidth
        arc.lineCap = .round
        arc.fillColor = nil
        arc.strokeColor = .black
        // Faint at the tail, strongest at the head; fading again past it keeps the tail's cap faint.
        gradient.startPoint = CGPoint(x: 0.5, y: 0.5)
        gradient.endPoint = CGPoint(x: 1, y: 0.5)
        gradient.locations = [0, NSNumber(value: 274.0 / 360), 1]
        CATransaction.commit()
        updateColors()
        restart()
    }

    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        updateColors()
    }

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        restart()
    }

    private func updateColors() {
        CATransaction.begin(); CATransaction.setDisableActions(true)
        track.strokeColor = labelTone(0.16, in: effectiveAppearance)
        gradient.colors = [labelTone(0.08, in: effectiveAppearance), labelTone(0.8, in: effectiveAppearance), labelTone(0.08, in: effectiveAppearance)]
        CATransaction.commit()
    }

    private func restart() {
        rotor.removeAnimation(forKey: "spin")
        CATransaction.begin(); CATransaction.setDisableActions(true)
        rotor.transform = animates ? CATransform3DIdentity : CATransform3DMakeRotation(-.pi / 2, 0, 0, 1)
        CATransaction.commit()
        guard animates, window != nil else { return }
        let spin = CABasicAnimation(keyPath: "transform.rotation.z")
        spin.fromValue = 0
        spin.toValue = CGFloat.pi * 2
        spin.duration = 1.15
        spin.repeatCount = .infinity
        rotor.add(spin, forKey: "spin")
    }
}
