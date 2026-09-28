import AppKit
import SwiftUI

/// What a picture's zoom controls show, and the actions they send to its view.
@MainActor
final class ImageZoomModel: ObservableObject {
    @Published private(set) var percent = 100
    @Published private(set) var fitted = true
    @Published private(set) var canZoomIn = true
    fileprivate(set) weak var view: ImageZoomScrollView?

    func zoomIn() { view?.step(larger: true) }
    func zoomOut() { view?.step(larger: false) }
    func fit() { view?.fit() }

    fileprivate func show(percent: Int, fitted: Bool, canZoomIn: Bool) {
        // Scrolling reports too; publish only real changes so the controls are not redrawn for it.
        if self.percent != percent { self.percent = percent }
        if self.fitted != fitted { self.fitted = fitted }
        if self.canZoomIn != canZoomIn { self.canZoomIn = canZoomIn }
    }
}

/// A checked local picture that magnifies the way Preview does: pinch, a two-finger double tap or a
/// double click, ⌘ with + − 0 or ⌘ with the scroll wheel; drag or scroll to look around. It opens
/// fitted to the view and follows resizing until the operator zooms in. Past the thumbnail's
/// resolution it shows the verified original, so small text stays sharp.
struct ZoomableImage: NSViewRepresentable {
    let preview: NativeImagePreview
    let zoom: ImageZoomModel
    var inset: CGFloat = 16
    let label: String

    func makeNSView(context: Context) -> ImageZoomScrollView {
        let view = ImageZoomScrollView(picture: preview.thumbnail, size: preview.pointSize, original: preview.bytes)
        view.onChange = { [weak zoom] in zoom?.show(percent: $0, fitted: $1, canZoomIn: $2) }
        return view
    }

    func updateNSView(_ view: ImageZoomScrollView, context: Context) {
        zoom.view = view
        view.inset = inset
        // Hidden panel tabs stay mounted but disabled; only the visible picture takes ⌘ + − 0.
        view.active = context.environment.isEnabled
        view.pictureLabel = label
    }

    static func dismantleNSView(_ view: ImageZoomScrollView, coordinator: ()) { view.close() }
}

/// Zoom out, the current scale (a click fits the picture again) and zoom in.
struct ImageZoomControls: View {
    @ObservedObject var zoom: ImageZoomModel

    var body: some View {
        HStack(spacing: 0) {
            Button { zoom.zoomOut() } label: { Image(systemName: "minus.magnifyingglass") }
                .disabled(zoom.fitted).help(L10n.text("Уменьшить изображение (⌘−)"))
                .accessibilityLabel(L10n.text("Уменьшить изображение"))
            Button { zoom.fit() } label: { Text(verbatim: "\(zoom.percent)%").monospacedDigit().frame(minWidth: 36) }
                .help(L10n.text("Вписать изображение в окно (⌘0)"))
                .accessibilityLabel(L10n.format("Масштаб изображения \(zoom.percent)%"))
            Button { zoom.zoomIn() } label: { Image(systemName: "plus.magnifyingglass") }
                .disabled(!zoom.canZoomIn).help(L10n.text("Увеличить изображение (⌘+)"))
                .accessibilityLabel(L10n.text("Увеличить изображение"))
        }.font(.system(size: 12)).buttonStyle(.nativeHover(minSize: 24))
    }
}

/// Magnification, centring and panning for `ZoomableImage`.
final class ImageZoomScrollView: NSScrollView {
    static let largest: CGFloat = 8
    static let step: CGFloat = 1.5
    var onChange: ((_ percent: Int, _ fitted: Bool, _ canZoomIn: Bool) -> Void)?
    var inset: CGFloat = 16 { didSet { if inset != oldValue { refit() } } }
    var active = true
    var pictureLabel = "" { didSet { picture.setAccessibilityLabel(pictureLabel) } }
    private(set) var fitted = true
    private(set) var fitMagnification: CGFloat = 1
    /// Whether the verified original has replaced the thumbnail.
    private(set) var showsOriginal = false
    private let picture: ImageZoomPictureView
    private let size: CGSize
    private let original: Data
    private let thumbnailPixels: CGFloat
    private var decoding: Task<Void, Never>?

    init(picture image: NSImage, size: CGSize, original: Data) {
        let size = CGSize(width: max(1, size.width), height: max(1, size.height))
        let picture = ImageZoomPictureView(frame: NSRect(origin: .zero, size: size))
        picture.image = image
        self.size = size
        self.picture = picture
        self.original = original
        thumbnailPixels = max(image.size.width, image.size.height)
        super.init(frame: .zero)
        contentView = ImageZoomClipView()
        contentView.drawsBackground = false
        contentView.postsBoundsChangedNotifications = true
        drawsBackground = false
        borderType = .noBorder
        hasHorizontalScroller = true
        hasVerticalScroller = true
        autohidesScrollers = true
        scrollerStyle = .overlay
        usesPredominantAxisScrolling = false
        allowsMagnification = true
        maxMagnification = Self.largest
        documentView = picture
        NotificationCenter.default.addObserver(self, selector: #selector(scrolled), name: NSView.boundsDidChangeNotification, object: contentView)
        NotificationCenter.default.addObserver(self, selector: #selector(magnified), name: NSScrollView.didEndLiveMagnifyNotification, object: self)
    }

    required init?(coder: NSCoder) { nil }

    func close() {
        decoding?.cancel()
        NotificationCenter.default.removeObserver(self)
    }

    override func setFrameSize(_ newSize: NSSize) {
        super.setFrameSize(newSize)
        refit()
    }

    /// The largest scale, at most 100%, at which the whole picture fits inside the inset.
    private func refit() {
        let area = contentSize
        guard area.width > inset * 2 + 1, area.height > inset * 2 + 1 else { return }
        fitMagnification = min(1, (area.width - inset * 2) / size.width, (area.height - inset * 2) / size.height)
        minMagnification = fitMagnification
        maxMagnification = max(Self.largest, fitMagnification)
        if fitted || magnification < fitMagnification {
            fitted = true
            magnification = fitMagnification
        }
        report()
    }

    func step(larger: Bool) {
        zoom(to: larger ? magnification * Self.step : magnification / Self.step, at: visibleCenter)
    }

    func fit() { zoom(to: fitMagnification, at: visibleCenter) }

    /// A double click or a two-finger double tap: from the fitted picture to its actual size (twice
    /// the size of a picture that already fits at 100%), and back.
    func toggle(at point: NSPoint) {
        if fitted { zoom(to: max(1, fitMagnification * 2), at: point) } else { fit() }
    }

    /// Zooms to a scale within the allowed range, keeping `point` (in picture coordinates) in view.
    func zoom(to value: CGFloat, at point: NSPoint) {
        let target = min(maxMagnification, max(fitMagnification, value))
        fitted = target <= fitMagnification * 1.001
        setMagnification(fitted ? fitMagnification : target, centeredAt: point)
        report()
        showOriginalIfNeeded()
    }

    var canPan: Bool {
        let visible = documentVisibleRect
        return picture.frame.width > visible.width + 0.5 || picture.frame.height > visible.height + 0.5
    }

    /// Moves the picture with a drag; `delta` is in window points from where the drag began.
    func pan(from origin: NSPoint, by delta: NSPoint) {
        var bounds = contentView.bounds
        bounds.origin = NSPoint(x: origin.x - delta.x / magnification, y: origin.y - delta.y / magnification)
        contentView.scroll(to: contentView.constrainBoundsRect(bounds).origin)
        reflectScrolledClipView(contentView)
    }

    override func smartMagnify(with event: NSEvent) {
        toggle(at: picture.convert(event.locationInWindow, from: nil))
    }

    override func scrollWheel(with event: NSEvent) {
        // ⌘ with the scroll wheel zooms around the pointer, as in Preview; plain scrolling moves.
        guard event.modifierFlags.contains(.command) else { return super.scrollWheel(with: event) }
        let delta = event.hasPreciseScrollingDeltas ? event.scrollingDeltaY / 100 : event.scrollingDeltaY / 10
        zoom(to: magnification * min(1.5, max(0.67, 1 + delta)), at: picture.convert(event.locationInWindow, from: nil))
    }

    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask).subtracting([.shift, .capsLock, .numericPad, .function])
        guard active, flags == .command, window?.isKeyWindow == true, !isHiddenOrHasHiddenAncestor,
              let characters = event.charactersIgnoringModifiers, zoomKey(characters) else { return super.performKeyEquivalent(with: event) }
        return true
    }

    /// ⌘+ (or ⌘=) zooms in, ⌘− out, ⌘0 fits the picture again.
    func zoomKey(_ characters: String) -> Bool {
        switch characters {
        case "=", "+": step(larger: true)
        case "-": step(larger: false)
        case "0": fit()
        default: return false
        }
        return true
    }

    @objc private func scrolled() { report() }

    @objc private func magnified() {
        fitted = magnification <= fitMagnification * 1.001
        report()
        showOriginalIfNeeded()
    }

    private var visibleCenter: NSPoint { NSPoint(x: documentVisibleRect.midX, y: documentVisibleRect.midY) }

    private func report() {
        onChange?(Int((magnification * 100).rounded()), fitted, magnification < maxMagnification * 0.999)
        window?.invalidateCursorRects(for: picture)
    }

    /// Past the thumbnail's resolution, decodes the verified original once and shows it instead.
    private func showOriginalIfNeeded() {
        guard !showsOriginal, decoding == nil,
              max(size.width, size.height) * magnification * (window?.backingScaleFactor ?? 2) > thumbnailPixels * 1.05 else { return }
        let bytes = original, size = size
        decoding = Task { [weak self] in
            let image = await Task.detached(priority: .userInitiated) { NativeImagePreview.fullResolution(bytes) }.value
            guard let self, !Task.isCancelled, let image else { return }
            showsOriginal = true
            picture.image = NSImage(cgImage: image, size: size)
        }
    }
}

/// Keeps a picture smaller than its view in the middle rather than in a corner.
private final class ImageZoomClipView: NSClipView {
    override func constrainBoundsRect(_ proposedBounds: NSRect) -> NSRect {
        var rect = super.constrainBoundsRect(proposedBounds)
        guard let document = documentView?.frame else { return rect }
        if rect.width > document.width { rect.origin.x = document.midX - rect.width / 2 }
        if rect.height > document.height { rect.origin.y = document.midY - rect.height / 2 }
        return rect
    }
}

/// The picture itself: a double click zooms, and a magnified picture moves with a drag.
private final class ImageZoomPictureView: NSImageView {
    private var grab: (point: NSPoint, origin: NSPoint)?
    private var holding = false

    override init(frame: NSRect) {
        super.init(frame: frame)
        imageScaling = .scaleAxesIndependently
        imageFrameStyle = .none
        isEditable = false
        allowsCutCopyPaste = false
        animates = false
    }

    required init?(coder: NSCoder) { nil }

    private var zoomView: ImageZoomScrollView? { enclosingScrollView as? ImageZoomScrollView }

    override func mouseDown(with event: NSEvent) {
        guard let zoomView else { return }
        if event.clickCount == 2 { zoomView.toggle(at: convert(event.locationInWindow, from: nil)); return }
        grab = (event.locationInWindow, zoomView.contentView.bounds.origin)
        if zoomView.canPan { NSCursor.closedHand.push(); holding = true }
    }

    override func mouseDragged(with event: NSEvent) {
        guard let grab, let zoomView else { return }
        zoomView.pan(from: grab.origin, by: NSPoint(x: event.locationInWindow.x - grab.point.x, y: event.locationInWindow.y - grab.point.y))
    }

    override func mouseUp(with event: NSEvent) {
        grab = nil
        if holding { NSCursor.pop(); holding = false }
    }

    override func resetCursorRects() {
        if zoomView?.canPan == true { addCursorRect(visibleRect, cursor: .openHand) }
    }
}
