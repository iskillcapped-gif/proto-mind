import Foundation
import PDFKit
import Darwin
import ImageIO
import UniformTypeIdentifiers

// Fixed stdin-to-text/page worker. The GUI never parses the original PDF.
let maximumBytes = 8 * 1024 * 1024
let maximumPages = 300
let maximumSelected = 8
let pageCharacters = 3000

func fail(_ message: String) -> Never {
    let data = (try? JSONSerialization.data(withJSONObject: ["error": message])) ?? Data()
    FileHandle.standardOutput.write(data)
    exit(1)
}

var cpu = rlimit(rlim_cur: 8, rlim_max: 8)
guard setrlimit(RLIMIT_CPU, &cpu) == 0 else { fail("PDF reader resource limit is unavailable.") }
guard CommandLine.arguments.count == 3, ["--pages", "--render-page"].contains(CommandLine.arguments[1]) else {
    fail("PDF reader accepts only explicit page numbers and stdin bytes.")
}
let parts = CommandLine.arguments[2].split(separator: ",", omittingEmptySubsequences: false)
let render = CommandLine.arguments[1] == "--render-page"
let numbers = parts.compactMap { part -> Int? in
    guard !part.isEmpty, part.allSatisfy({ $0.isASCII && $0.isNumber }) else { return nil }
    return Int(part)
}
guard (1...maximumSelected).contains(numbers.count), numbers.count == parts.count,
      Set(numbers).count == numbers.count, numbers == numbers.sorted(),
      numbers.allSatisfy({ (1...maximumPages).contains($0) }) else { fail("Select 1 to 8 distinct PDF pages.") }
guard !render || numbers.count == 1 else { fail("Render one PDF page at a time.") }

var bytes = Data()
do {
    while let block = try FileHandle.standardInput.read(upToCount: min(65536, maximumBytes + 1 - bytes.count)), !block.isEmpty {
        bytes.append(block)
        if bytes.count > maximumBytes { fail("PDF exceeds 8 MiB.") }
    }
} catch { fail("PDF input could not be read.") }
guard bytes.starts(with: Data("%PDF-".utf8)), let document = PDFDocument(data: bytes) else {
    fail("Invalid or unreadable PDF document.")
}
guard !document.isEncrypted, !document.isLocked, document.allowsCopying else {
    fail("Encrypted or copy-restricted PDFs are not supported. No password or bypass was attempted.")
}
guard (1...maximumPages).contains(document.pageCount), numbers.allSatisfy({ $0 <= document.pageCount }) else {
    fail("PDF page range is invalid or the document exceeds 300 pages.")
}
var pages: [[String: Any]] = []
for number in numbers {
    guard let page = document.page(at: number - 1) else { fail("A selected PDF page is unreadable.") }
    let original = (page.string ?? "").replacingOccurrences(of: "\r\n", with: "\n").replacingOccurrences(of: "\r", with: "\n")
    let scalars = original.unicodeScalars.filter { $0.value >= 32 && $0.value != 127 || $0 == "\n" || $0 == "\t" }
    let clean = String(String.UnicodeScalarView(scalars)).trimmingCharacters(in: .whitespacesAndNewlines)
    let text = String(String.UnicodeScalarView(clean.unicodeScalars.prefix(pageCharacters)))
    pages.append(["number": number, "text": text, "characters": clean.unicodeScalars.count,
                  "included_chars": text.unicodeScalars.count, "truncated": clean.unicodeScalars.count > pageCharacters])
}
var result: [String: Any] = ["schema": "proto_mind.native_pdf_text.v1",
    "engine": "apple_pdfkit_text_v1", "page_count": document.pageCount, "pages": pages]
if render {
    guard let page = document.page(at: numbers[0] - 1)?.pageRef else { fail("PDF page could not be rendered.") }
    let bounds = page.getBoxRect(.cropBox)
    guard (0.1...1_000_000).contains(bounds.width), (0.1...1_000_000).contains(bounds.height) else { fail("Invalid PDF page dimensions.") }
    let rotated = abs(page.rotationAngle % 180) == 90
    let size = rotated ? CGSize(width: bounds.height, height: bounds.width) : bounds.size
    let scale = 1600 / max(size.width, size.height)
    let width = max(1, Int((size.width * scale).rounded()))
    let height = max(1, Int((size.height * scale).rounded()))
    guard let context = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8,
                                  bytesPerRow: width * 4, space: CGColorSpaceCreateDeviceRGB(),
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { fail("PDF page raster allocation failed.") }
    let target = CGRect(x: 0, y: 0, width: width, height: height)
    context.setFillColor(CGColor(gray: 1, alpha: 1)); context.fill(target)
    // getDrawingTransform centers but does not upscale smaller PDF pages on
    // macOS. Apply raster scaling explicitly; let Core Graphics handle crop/rotation.
    context.scaleBy(x: CGFloat(width) / size.width, y: CGFloat(height) / size.height)
    context.concatenate(page.getDrawingTransform(.cropBox, rect: CGRect(origin: .zero, size: size), rotate: 0, preserveAspectRatio: true))
    context.drawPDFPage(page)
    let png = NSMutableData()
    guard let image = context.makeImage(),
          let destination = CGImageDestinationCreateWithData(png, UTType.png.identifier as CFString, 1, nil) else { fail("PDF image could not be encoded.") }
    CGImageDestinationAddImage(destination, image, nil)
    guard CGImageDestinationFinalize(destination), png.length <= 5 * 1024 * 1024 else { fail("Rendered PDF page exceeded its image limit.") }
    result = ["schema": "proto_mind.native_pdf_render.v1", "text_preview": result,
              "page": numbers[0], "width": width, "height": height, "png_base64": (png as Data).base64EncodedString()]
}
do {
    let output = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
    guard output.count <= (render ? 7 * 1024 * 1024 : 512 * 1024) else { fail("PDF preview exceeded its output limit.") }
    FileHandle.standardOutput.write(output)
} catch { fail("Extracted PDF text could not be encoded.") }
