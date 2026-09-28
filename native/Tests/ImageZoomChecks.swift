import AppKit
import CryptoKit
import ImageIO
import SwiftUI
import UniformTypeIdentifiers

extension NativeChecks {
    /// A checked preview of a PNG the way the bridge returns it; `dpi` 144 is a Retina screenshot.
    static func zoomPreview(width: Int, height: Int, dpi: Double) throws -> NativeImagePreview {
        let context = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                                bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
        context.setFillColor(CGColor(red: 0.13, green: 0.14, blue: 0.17, alpha: 1)); context.fill(CGRect(x: 0, y: 0, width: width, height: height))
        // A blue header near the top and rows of small "text", so orientation and sharpness show.
        context.setFillColor(CGColor(red: 0.2, green: 0.45, blue: 0.9, alpha: 1))
        context.fill(CGRect(x: width / 18, y: height * 3 / 4, width: width / 3, height: height / 12))
        context.setFillColor(CGColor(gray: 0.85, alpha: 1))
        for row in 0..<12 {
            for word in 0..<9 {
                context.fill(CGRect(x: width / 18 + word * width / 11, y: height / 10 + row * height / 22, width: width / 14, height: max(2, height / 90)))
            }
        }
        let data = NSMutableData()
        let destination = CGImageDestinationCreateWithData(data, UTType.png.identifier as CFString, 1, nil)!
        CGImageDestinationAddImage(destination, context.makeImage()!, [kCGImagePropertyDPIWidth: dpi, kCGImagePropertyDPIHeight: dpi] as CFDictionary)
        guard CGImageDestinationFinalize(destination) else { throw NativeError.message("Zoom fixture unavailable") }
        let bytes = data as Data
        let image: JSONValue = .object([
            "schema": .string("proto_mind.native_image.v1"), "path": .string("/tmp/Снимок экрана.png"), "name": .string("Снимок экрана.png"),
            "sha256": .string(SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()), "mime_type": .string("image/png"),
            "size_bytes": .number(Double(bytes.count)), "width": .number(Double(width)), "height": .number(Double(height))])
        return try NativeImagePreview(.object(["schema": .string("proto_mind.native_image_preview.v1"), "read_only": .bool(true),
                                               "no_execution": .bool(true), "image": image, "data_base64": .string(bytes.base64EncodedString())]),
                                      conversationID: UUID(), canAttach: false)
    }

    /// A picture opened from a message fits its view, magnifies to 800% and back, keeps the
    /// operator's zoom while the view resizes, moves with a drag, and shows the verified original
    /// once it is magnified past the thumbnail's resolution.
    @MainActor static func imageZoom() async throws {
        let screenshot = try zoomPreview(width: 2872, height: 1712, dpi: 144), photo = try zoomPreview(width: 300, height: 200, dpi: 72)
        try check(screenshot.pointSize == CGSize(width: 1436, height: 856) && photo.pointSize == CGSize(width: 300, height: 200),
                  "A picture's 100% size follows its DPI: a Retina screenshot shows its pixels at their original size")

        let zoom = ImageZoomModel()
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 600, height: 500), styleMask: [.borderless], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        defer { window.contentView = nil; window.close() }
        window.contentView = NSHostingView(rootView: ZoomableImage(preview: screenshot, zoom: zoom, inset: 16, label: "Снимок").frame(width: 600, height: 500))
        window.contentView?.layoutSubtreeIfNeeded()
        guard let view = zoom.view else { throw NativeError.message("The zoomable picture was not created") }
        let fit = min(1, 568 / 1436.0, 468 / 856.0)
        func at(_ value: CGFloat) -> Bool { abs(view.magnification - value) < 0.002 }
        func centred() -> Bool {
            let visible = view.documentVisibleRect, frame = view.documentView?.frame ?? .zero
            return abs(visible.midX - frame.midX) < 1 && abs(visible.midY - frame.midY) < 1
        }
        try check(at(fit) && zoom.percent == 40 && zoom.fitted && !view.canPan && centred(),
                  "A picture opens whole, centred and fitted to its view (\(zoom.percent)%)")

        view.step(larger: true)
        try check(at(fit * 1.5) && zoom.percent == 59 && !zoom.fitted, "Zoom in magnifies by half again")
        try check(view.zoomKey("-") && at(fit) && zoom.fitted, "⌘− zooms out, never below the fitted picture")

        let corner = NSPoint(x: 1436 * 0.2, y: 856 * 0.3)
        view.toggle(at: corner)
        try check(at(1) && zoom.percent == 100 && view.canPan && view.documentVisibleRect.contains(corner),
                  "A double click shows the picture at 100% around the clicked point")
        for _ in 0..<40 where !view.showsOriginal { try await Task.sleep(for: .milliseconds(50)) }
        let shown = (view.documentView as? NSImageView)?.image?.representations.first?.pixelsWide
        try check(view.showsOriginal && shown == 2872, "Past the thumbnail's resolution the verified original replaces it (\(shown ?? 0) px)")

        view.contentView.scroll(to: NSPoint(x: 300, y: 150)); view.reflectScrolledClipView(view.contentView)
        let origin = view.contentView.bounds.origin
        view.pan(from: origin, by: NSPoint(x: 100, y: 40))
        let moved = view.contentView.bounds.origin
        try check(abs(moved.x - (origin.x - 100)) < 0.5 && abs(moved.y - (origin.y - 40)) < 0.5,
                  "Dragging a magnified picture moves it with the pointer")

        view.setFrameSize(NSSize(width: 800, height: 600))
        try check(at(1) && !zoom.fitted, "Resizing keeps the operator's zoom")
        try check(view.zoomKey("0") && zoom.fitted && centred(), "⌘0 fits the picture again")
        view.setFrameSize(NSSize(width: 900, height: 700))
        try check(at(min(1, 868 / 1436.0, 668 / 856.0)) && zoom.fitted && centred(), "A fitted picture follows its view as it resizes")

        for _ in 0..<12 { _ = view.zoomKey("=") }
        try check(at(ImageZoomScrollView.largest) && !zoom.canZoomIn, "Zooming in stops at 800%")
        for _ in 0..<12 { view.step(larger: false) }
        try check(at(view.fitMagnification) && zoom.fitted, "Zooming out stops at the fitted picture")

        // A small picture is never enlarged to fill the view; a double click still magnifies it.
        let small = ImageZoomModel()
        window.contentView = NSHostingView(rootView: ZoomableImage(preview: photo, zoom: small, label: "Маленькая")
                                            .frame(width: 600, height: 500).disabled(true))
        window.contentView?.layoutSubtreeIfNeeded()
        guard let little = small.view else { throw NativeError.message("The small picture was not created") }
        try check(small.percent == 100 && small.fitted && !little.active, "A small picture opens at 100%, and a hidden tab's picture ignores ⌘ + − 0")
        little.toggle(at: NSPoint(x: 150, y: 100))
        try check(small.percent == 200, "A double click magnifies a picture that already fits at 100%")
    }
}
