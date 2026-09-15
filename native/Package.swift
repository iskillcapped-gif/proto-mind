// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "ProtoMindNative",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "ProtoMindNative", targets: ["ProtoMindNative"]),
               .executable(name: "ProtoMindPDF", targets: ["ProtoMindPDF"])],
    dependencies: [
        .package(url: "https://github.com/migueldeicaza/SwiftTerm.git", exact: "1.20.0"),
    ],
    targets: [
        .executableTarget(name: "ProtoMindNative", dependencies: ["SwiftTerm"], path: "Sources"),
        .executableTarget(name: "ProtoMindPDF", path: "PDFHelper"),
    ],
    swiftLanguageModes: [.v5]
)
