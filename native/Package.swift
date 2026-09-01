// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "ProtoMindNative",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "ProtoMindNative", targets: ["ProtoMindNative"]),
               .executable(name: "ProtoMindPDF", targets: ["ProtoMindPDF"])],
    targets: [
        .executableTarget(name: "ProtoMindNative", path: "Sources"),
        .executableTarget(name: "ProtoMindPDF", path: "PDFHelper"),
    ],
    swiftLanguageModes: [.v5]
)
