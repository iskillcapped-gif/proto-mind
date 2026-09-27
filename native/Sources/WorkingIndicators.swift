import AppKit
import QuartzCore
import SwiftUI

// Working indicators are moved by Core Animation. A SwiftUI TimelineView re-rendered the
// whole hosting view on every frame; in a long transcript that took 15-25% of the main
// thread while a task ran and made scrolling stutter.

struct WorkingIndicator: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        SpinnerRepresentable(animates: !reduceMotion && scenePhase == .active)
            .frame(width: 15, height: 15).accessibilityHidden(true)
    }
}

struct WorkingStatusText: View {
    let text: String
    var active = true
    var color: Color = .secondary
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        Text(text).foregroundStyle(color)
            .overlay {
                if active && !reduceMotion && !text.isEmpty {
                    ShimmerRepresentable(animates: scenePhase == .active)
                        .mask(alignment: .leading) { Text(text) }
                        .allowsHitTesting(false).accessibilityHidden(true)
                }
            }
    }
}

private struct SpinnerRepresentable: NSViewRepresentable {
    let animates: Bool
    func makeNSView(context: Context) -> WorkingSpinnerView { WorkingSpinnerView() }
    func updateNSView(_ view: WorkingSpinnerView, context: Context) { view.animates = animates }
}

private struct ShimmerRepresentable: NSViewRepresentable {
    let animates: Bool
    func makeNSView(context: Context) -> WorkingShimmerView { WorkingShimmerView() }
    func updateNSView(_ view: WorkingShimmerView, context: Context) { view.animates = animates }
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

/// A light beam that crosses the view in 2 s and rests 0.6 s; the caller masks it with the text.
final class WorkingShimmerView: NSView {
    private let beam = CAGradientLayer()
    private var drawnSize = CGSize.zero
    var animates = true { didSet { if animates != oldValue { restart() } } }

    override init(frame: NSRect) {
        super.init(frame: frame)
        wantsLayer = true
        layer?.masksToBounds = true
        beam.startPoint = CGPoint(x: 0, y: 0.5)
        beam.endPoint = CGPoint(x: 1, y: 0.5)
        beam.anchorPoint = .zero
        layer?.addSublayer(beam)
    }

    required init?(coder: NSCoder) { nil }
    override var isFlipped: Bool { true }
    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    override func layout() {
        super.layout()
        guard bounds.size != drawnSize else { return }
        drawnSize = bounds.size
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
        beam.colors = [CGColor.clear, labelTone(0.12, in: effectiveAppearance), labelTone(0.9, in: effectiveAppearance),
                       labelTone(0.12, in: effectiveAppearance), CGColor.clear]
        CATransaction.commit()
    }

    private func restart() {
        beam.removeAnimation(forKey: "sweep")
        let width = min(110, max(40, bounds.width * 0.45))
        CATransaction.begin(); CATransaction.setDisableActions(true)
        beam.bounds = CGRect(x: 0, y: 0, width: width, height: bounds.height)
        beam.position = CGPoint(x: -width, y: 0)
        CATransaction.commit()
        updateColors()
        guard animates, window != nil, bounds.width > 0 else { return }
        let sweep = CABasicAnimation(keyPath: "position.x")
        sweep.fromValue = -width
        sweep.toValue = bounds.width
        sweep.duration = 2
        let cycle = CAAnimationGroup()
        cycle.animations = [sweep]
        cycle.duration = 2.6
        cycle.repeatCount = .infinity
        beam.add(cycle, forKey: "sweep")
    }
}
