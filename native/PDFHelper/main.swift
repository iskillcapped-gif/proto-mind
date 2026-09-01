import Foundation
import PDFKit
import Darwin

// A fixed stdin-to-text worker, never a viewer, writer or general command runner.
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
guard CommandLine.arguments.count == 3, CommandLine.arguments[1] == "--pages" else {
    fail("PDF reader accepts only explicit page numbers and stdin bytes.")
}
let parts = CommandLine.arguments[2].split(separator: ",", omittingEmptySubsequences: false)
let numbers = parts.compactMap { part -> Int? in
    guard !part.isEmpty, part.allSatisfy({ $0.isASCII && $0.isNumber }) else { return nil }
    return Int(part)
}
guard (1...maximumSelected).contains(numbers.count), numbers.count == parts.count,
      Set(numbers).count == numbers.count, numbers == numbers.sorted(),
      numbers.allSatisfy({ (1...maximumPages).contains($0) }) else { fail("Select 1 to 8 distinct PDF pages.") }

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
do {
    let output = try JSONSerialization.data(withJSONObject: ["schema": "proto_mind.native_pdf_text.v1",
        "engine": "apple_pdfkit_text_v1", "page_count": document.pageCount, "pages": pages], options: [.sortedKeys])
    guard output.count <= 512 * 1024 else { fail("Extracted PDF text exceeded its output limit.") }
    FileHandle.standardOutput.write(output)
} catch { fail("Extracted PDF text could not be encoded.") }
