import AppKit
import Quartz
import SwiftUI

struct WorkspaceDocumentPreview {
    let conversationID: UUID
    let url: URL
    let sha256: String
}

struct WorkspaceDocumentView: NSViewRepresentable {
    let document: WorkspaceDocumentPreview
    func makeNSView(context: Context) -> QLPreviewView {
        let view = QLPreviewView(frame: .zero, style: .normal)!
        view.autostarts = true
        view.previewItem = document.url as NSURL
        return view
    }
    func updateNSView(_ view: QLPreviewView, context: Context) {
        if (view.previewItem?.previewItemURL ?? nil) != document.url { view.previewItem = document.url as NSURL }
    }
    static func dismantleNSView(_ view: QLPreviewView, coordinator: ()) { view.close() }
}

enum WorkspaceAgentImage {
    static func jpeg(_ image: NSImage) throws -> String {
        var rect = CGRect(origin: .zero, size: image.size)
        guard let source = image.cgImage(forProposedRect: &rect, context: nil, hints: nil) else { throw NativeError.message("Image unavailable.") }
        for edge in [1200, 900, 640] {
            let scale = min(1, Double(edge) / Double(max(source.width, source.height)))
            let width = max(1, Int(Double(source.width) * scale)), height = max(1, Int(Double(source.height) * scale))
            guard let context = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0,
                                          space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { continue }
            context.setFillColor(NSColor.white.cgColor); context.fill(CGRect(x: 0, y: 0, width: width, height: height))
            context.draw(source, in: CGRect(x: 0, y: 0, width: width, height: height))
            if let image = context.makeImage(), let data = NSBitmapImageRep(cgImage: image).representation(using: .jpeg, properties: [.compressionFactor: 0.72]), data.count <= 290_000 {
                return "data:image/jpeg;base64," + data.base64EncodedString()
            }
        }
        throw NativeError.message("Image exceeds the tool preview limit.")
    }
}
