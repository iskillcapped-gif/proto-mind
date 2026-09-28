import SwiftUI
import AVFoundation

struct RemoteQRScanner: UIViewControllerRepresentable {
    let received: (String) -> Void
    func makeUIViewController(context: Context) -> ScannerController { ScannerController(received: received) }
    func updateUIViewController(_ uiViewController: ScannerController, context: Context) { }
    static func dismantleUIViewController(_ uiViewController: ScannerController, coordinator: ()) { uiViewController.stop() }
}

final class ScannerController: UIViewController, AVCaptureMetadataOutputObjectsDelegate {
    private let session = AVCaptureSession()
    private let queue = DispatchQueue(label: "com.virencore.qr-scanner")
    private var preview: AVCaptureVideoPreviewLayer?
    private let received: (String) -> Void
    private var completed = false
    private var stopped = false
    init(received: @escaping (String) -> Void) { self.received = received; super.init(nibName: nil, bundle: nil) }
    required init?(coder: NSCoder) { fatalError("init(coder:) is not supported") }
    override func viewDidLoad() {
        super.viewDidLoad(); view.backgroundColor = .black
        Task {
            let granted = await AVCaptureDevice.requestAccess(for: .video)
            guard granted, !completed else { explain(); return }
            guard let device = AVCaptureDevice.default(for: .video), let input = try? AVCaptureDeviceInput(device: device), session.canAddInput(input) else { explain(); return }
            let output = AVCaptureMetadataOutput()
            guard session.canAddOutput(output) else { explain(); return }
            session.addInput(input); session.addOutput(output); output.setMetadataObjectsDelegate(self, queue: .main); output.metadataObjectTypes = [.qr]
            let layer = AVCaptureVideoPreviewLayer(session: session); layer.videoGravity = .resizeAspectFill
            view.layer.addSublayer(layer); preview = layer; layer.frame = view.bounds
            queue.async { if !self.stopped { self.session.startRunning() } }
        }
    }
    override func viewDidLayoutSubviews() { super.viewDidLayoutSubviews(); preview?.frame = view.bounds }
    func stop() { completed = true; queue.async { self.stopped = true; self.session.stopRunning() } }
    func metadataOutput(_ output: AVCaptureMetadataOutput, didOutput metadataObjects: [AVMetadataObject], from connection: AVCaptureConnection) {
        guard !completed, let code = metadataObjects.compactMap({ ($0 as? AVMetadataMachineReadableCodeObject)?.stringValue }).first,
              (try? MobilePairing.parse(code)) != nil else { return }
        stop(); received(code)
    }
    private func explain() {
        let label = UILabel(); label.text = R("Камера недоступна. Закройте сканер и вставьте ссылку подключения.", "Camera unavailable. Close the scanner and paste a pairing link.")
        label.textColor = .white; label.numberOfLines = 0; label.textAlignment = .center
        label.translatesAutoresizingMaskIntoConstraints = false; view.addSubview(label)
        NSLayoutConstraint.activate([label.centerYAnchor.constraint(equalTo: view.centerYAnchor), label.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 32), label.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -32)])
    }
}
