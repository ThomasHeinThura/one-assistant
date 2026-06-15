import SwiftUI

// Design system ported from /ui/index.html — the agreed MVP look.
// Navy gradient header, lavender AI brief, soft cards, colour-coded chips.

extension Color {
    static let navy900 = Color(hex: 0x0f2747)
    static let navy700 = Color(hex: 0x1e3a5f)
    static let navy500 = Color(hex: 0x2f5d8f)
    static let navy300 = Color(hex: 0x6f93bd)
    static let navy50  = Color(hex: 0xeef3f9)
    static let navy100 = Color(hex: 0xdde7f3)

    static let appBG   = Color(hex: 0xf4f7fb)
    static let cardBG  = Color(hex: 0xffffff)
    static let ink     = Color(hex: 0x15233a)
    static let muted   = Color(hex: 0x6b7a90)
    static let line    = Color(hex: 0xe4ebf3)

    static let ok = Color(hex: 0x1f9d6b),  okBG = Color(hex: 0xe4f6ee)
    static let warn = Color(hex: 0xc9810a), warnBG = Color(hex: 0xfdf3e0)
    static let risk = Color(hex: 0xd24545), riskBG = Color(hex: 0xfceaea)
    static let ai = Color(hex: 0x6c4cd1),   aiBG = Color(hex: 0xefeafb)

    init(hex: UInt32) {
        self.init(.sRGB,
                  red: Double((hex >> 16) & 0xff) / 255,
                  green: Double((hex >> 8) & 0xff) / 255,
                  blue: Double(hex & 0xff) / 255,
                  opacity: 1)
    }
}

// Navy gradient used by the header + login mark.
let navyGradient = LinearGradient(
    colors: [.navy700, .navy900],
    startPoint: .topLeading, endPoint: .bottomTrailing)

let aiOrbGradient = RadialGradient(
    colors: [Color(hex: 0x9b7ff0), .ai],
    center: .init(x: 0.3, y: 0.3), startRadius: 1, endRadius: 30)

// MARK: - Card container

struct MariaCard<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        VStack(alignment: .leading, spacing: 10) { content }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.cardBG)
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(Color.line))
            .shadow(color: .navy900.opacity(0.06), radius: 10, x: 0, y: 6)
    }
}

// MARK: - Eyebrow section label

struct Eyebrow: View {
    let text: String
    var trailing: AnyView? = nil
    var body: some View {
        HStack {
            Text(text.uppercased())
                .font(.system(size: 12, weight: .semibold)).tracking(0.4)
                .foregroundStyle(Color.muted)
            Spacer()
            if let trailing { trailing }
        }
        .padding(.horizontal, 4).padding(.top, 6).padding(.bottom, 2)
    }
}

// MARK: - Chip

enum ChipStyle { case risk, warn, ok, ai, neutral
    var fg: Color { switch self { case .risk: .risk; case .warn: .warn; case .ok: .ok; case .ai: .ai; case .neutral: .muted } }
    var bg: Color { switch self { case .risk: .riskBG; case .warn: .warnBG; case .ok: .okBG; case .ai: .aiBG; case .neutral: .navy50 } }
}

struct Chip: View {
    let text: String
    var style: ChipStyle = .neutral
    var body: some View {
        Text(text)
            .font(.system(size: 10.5, weight: .semibold))
            .padding(.horizontal, 8).padding(.vertical, 2)
            .foregroundStyle(style.fg)
            .background(style.bg, in: Capsule())
    }
}

// MARK: - Stat card

struct StatCard: View {
    let value: String
    let label: String
    var tint: Color = .ink
    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(value).font(.system(size: 22, weight: .bold)).foregroundStyle(tint)
            Text(label).font(.system(size: 11.5)).foregroundStyle(Color.muted)
                .lineLimit(1).minimumScaleFactor(0.8)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.cardBG)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(Color.line))
        .shadow(color: .navy900.opacity(0.06), radius: 8, x: 0, y: 4)
    }
}

// MARK: - AI brief card (lavender)

struct AIBrief<Content: View>: View {
    var tag: String = "Daily brief"
    var orchestrating: Bool = false
    @ViewBuilder var content: Content
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Circle().fill(aiOrbGradient).frame(width: 26, height: 26)
                    .overlay(Circle().strokeBorder(Color.aiBG, lineWidth: 4))
                Text("Maria").font(.system(size: 14, weight: .bold))
                Text(tag).font(.system(size: 10.5, weight: .semibold))
                    .foregroundStyle(Color.ai)
                    .padding(.horizontal, 8).padding(.vertical, 2)
                    .background(Color.aiBG, in: Capsule())
                if orchestrating {
                    Spacer()
                    Text("orchestrating").font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(Color.ai)
                        .padding(.horizontal, 8).padding(.vertical, 2)
                        .background(Color.aiBG, in: Capsule())
                }
            }
            content
        }
        .padding(15)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(LinearGradient(colors: [Color(hex: 0xfaf8ff), Color(hex: 0xf1ecfb)],
                                   startPoint: .topLeading, endPoint: .bottomTrailing))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(Color.navy100))
        .shadow(color: .navy900.opacity(0.06), radius: 10, x: 0, y: 6)
    }
}

// MARK: - Live banner

struct LiveBanner: View {
    let text: String
    var body: some View {
        HStack(spacing: 8) {
            Circle().fill(Color.ai).frame(width: 8, height: 8)
            Text(text).font(.system(size: 12.5)).foregroundStyle(Color(hex: 0x3a2c63))
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .background(Color.aiBG)
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(Color(hex: 0xe0d6f7)))
    }
}

// MARK: - Suggestion (dashed) card

struct SuggestionCard: View {
    let text: String
    var action: String = "Act ›"
    var onTap: (() -> Void)? = nil
    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Text("✦").font(.system(size: 13))
                .frame(width: 24, height: 24)
                .foregroundStyle(Color.ai).background(Color.aiBG, in: RoundedRectangle(cornerRadius: 7))
            Text(text).font(.system(size: 13)).foregroundStyle(Color.ink)
            Spacer(minLength: 4)
            Text(action).font(.system(size: 12, weight: .semibold)).foregroundStyle(Color.navy500)
        }
        .padding(.horizontal, 12).padding(.vertical, 11)
        .background(Color(hex: 0xfbfcfe))
        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous)
            .strokeBorder(Color.navy100, style: StrokeStyle(lineWidth: 1, dash: [4, 3])))
        .contentShape(Rectangle())
        .onTapGesture { onTap?() }
    }
}

// MARK: - Horizontal progress bar

struct MiniBar: View {
    var fraction: Double
    var tint: Color
    var height: CGFloat = 7
    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(Color.navy50)
                Capsule().fill(tint).frame(width: max(4, geo.size.width * min(1, max(0, fraction))))
            }
        }
        .frame(height: height)
    }
}
