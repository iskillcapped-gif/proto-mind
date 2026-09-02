import AppKit
import Foundation

extension NativeChecks {
    static func appIcon(source: URL) throws {
        let data = try Data(contentsOf: source)
        guard let bitmap = NSBitmapImageRep(data: data) else {
            throw NativeError.message("Native app icon is not a readable bitmap")
        }
        try check(bitmap.pixelsWide == 1024 && bitmap.pixelsHigh == 1024,
                  "Native app icon has a square 1024-pixel master")
        try check(bitmap.hasAlpha, "Native app icon has a real alpha channel")
        let corners = [(0, 0), (1023, 0), (0, 1023), (1023, 1023)]
        try check(corners.allSatisfy { bitmap.colorAt(x: $0.0, y: $0.1)?.alphaComponent == 0 },
                  "Native icon corners are transparent, not a baked checkerboard")
        try check((bitmap.colorAt(x: 512, y: 512)?.alphaComponent ?? 0) > 0.99,
                  "Native icon keeps its central cube opaque")
        var visible = 0
        var samples = 0
        for y in stride(from: 0, to: 1024, by: 16) {
            for x in stride(from: 0, to: 1024, by: 16) {
                if (bitmap.colorAt(x: x, y: y)?.alphaComponent ?? 0) > 0.5 { visible += 1 }
                samples += 1
            }
        }
        let coverage = Double(visible) / Double(samples)
        try check(coverage > 0.55 && coverage < 0.9,
                  "Native icon has readable artwork and an outer transparent safety margin")
    }
}
