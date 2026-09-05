import SwiftUI

/// Small local animations: only their drawing updates, not the surrounding transcript.
struct WorkingIndicator: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30, paused: reduceMotion || scenePhase != .active)) { tick in
            ZStack {
                Circle().stroke(Color.primary.opacity(0.16), lineWidth: 1.7)
                Circle().trim(from: 0, to: 0.76)
                    .stroke(AngularGradient(colors: [.primary.opacity(0.08), .primary.opacity(0.8)],
                                            center: .center, startAngle: .degrees(0), endAngle: .degrees(274)),
                            style: StrokeStyle(lineWidth: 1.7, lineCap: .round))
                    .rotationEffect(.degrees(reduceMotion ? -90 : tick.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 1.15) / 1.15 * 360))
            }.padding(1)
        }.frame(width: 15, height: 15).accessibilityHidden(true)
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
                    GeometryReader { geometry in
                        TimelineView(.animation(minimumInterval: 1.0 / 30, paused: scenePhase != .active)) { tick in
                            let beam = min(110, max(40, geometry.size.width * 0.45))
                            let cycle = tick.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 2.6)
                            let progress = min(1, cycle / 2)
                            LinearGradient(colors: [.clear, .primary.opacity(0.12), .primary.opacity(0.9), .primary.opacity(0.12), .clear],
                                           startPoint: .leading, endPoint: .trailing)
                                .frame(width: beam, height: geometry.size.height)
                                .offset(x: -beam + (geometry.size.width + beam) * progress)
                        }
                    }.mask(alignment: .leading) { Text(text) }
                        .allowsHitTesting(false).accessibilityHidden(true)
                }
            }
    }
}
