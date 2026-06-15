import SwiftUI

@MainActor
final class CRMModel: ObservableObject {
    @Published var all: [Opportunity] = []
    @Published var filter = "all"
    @Published var loaded = false

    func load() async {
        all = (try? await APIClient.shared.opportunities(filter: "all")) ?? []
        loaded = true
    }

    var filtered: [Opportunity] {
        switch filter {
        case "open":  all.filter { $0.stage != "won" && $0.stage != "lost" }
        case "risk":  all.filter { $0.health == "at_risk" }
        case "won":   all.filter { $0.stage == "won" }
        case "lost":  all.filter { $0.stage == "lost" }
        default:      all
        }
    }

    var openPipeline: Double { all.filter { $0.stage != "won" && $0.stage != "lost" }.reduce(0) { $0 + $1.pipeline_value_usd } }
    var activeCount: Int { all.filter { $0.stage != "won" && $0.stage != "lost" }.count }
    var atRiskCount: Int { all.filter { $0.health == "at_risk" }.count }

    // Funnel buckets in lifecycle order, with count + summed value.
    struct Bucket: Identifiable { let id = UUID(); let name: String; let count: Int; let value: Double; let kind: String }
    var funnel: [Bucket] {
        let groups: [(String, [String], String)] = [
            ("Lead", ["lead"], "open"), ("Visit", ["visit"], "open"),
            ("Qualified", ["qualified"], "open"),
            ("Proposal", ["proposal_tech", "proposal_commercial"], "open"),
            ("Quote", ["quotation"], "open"), ("Contract", ["contract"], "open"),
            ("Won", ["won"], "won"), ("Lost", ["lost"], "lost"),
        ]
        return groups.map { name, stages, kind in
            let rows = all.filter { stages.contains($0.stage) }
            return Bucket(name: name, count: rows.count, value: rows.reduce(0) { $0 + $1.pipeline_value_usd }, kind: kind)
        }
    }
}

struct CRMView: View {
    @Binding var subtitle: String
    var openChat: () -> Void
    @StateObject private var model = CRMModel()
    private let chips: [(String, String)] = [("all", "All"), ("open", "Open"), ("risk", "At-risk"), ("won", "Won"), ("lost", "Lost")]

    var body: some View {
        ScreenScroll {
            LiveBanner(text: "Maria keeps your pipeline stages and deal health up to date.")

            HStack(spacing: 10) {
                StatCard(value: money(model.openPipeline), label: "Open pipeline")
                StatCard(value: "\(model.activeCount)", label: "Active deals")
                StatCard(value: "\(model.atRiskCount)", label: "At-risk", tint: .risk)
            }

            Eyebrow(text: "Pipeline funnel · count & value")
            funnelCard

            Eyebrow(text: "Opportunities · AI health")
            filterChips

            if model.loaded && model.filtered.isEmpty {
                StatusBlock(icon: "tray", title: "No deals here", message: "Nothing matches this filter yet.")
            }
            ForEach(model.filtered) { dealCard($0) }
        }
        .task { await model.load(); subtitle = "\(money(model.openPipeline)) pipeline · \(model.activeCount) active deals" }
        .refreshable { await model.load() }
    }

    private var funnelCard: some View {
        let maxCount = max(1, model.funnel.map(\.count).max() ?? 1)
        return MariaCard {
            ForEach(model.funnel) { b in
                HStack(spacing: 10) {
                    Text(b.name).font(.system(size: 13.5, weight: .semibold)).frame(width: 84, alignment: .leading)
                    MiniBar(fraction: Double(b.count) / Double(maxCount),
                            tint: b.kind == "won" ? .ok : b.kind == "lost" ? .risk : .navy500, height: 18)
                    Text("\(b.count)").font(.system(size: 12.5, weight: .bold)).frame(width: 24, alignment: .trailing)
                    Text(money(b.value)).font(.system(size: 11)).foregroundStyle(Color.muted)
                        .frame(width: 56, alignment: .trailing)
                }
            }
        }
    }

    private var filterChips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 7) {
                ForEach(chips, id: \.0) { key, label in
                    let on = model.filter == key
                    let count = countFor(key)
                    Button { model.filter = key } label: {
                        Text("\(label) · \(count)")
                            .font(.system(size: 12.5, weight: .semibold))
                            .padding(.horizontal, 13).padding(.vertical, 7)
                            .foregroundStyle(on ? .white : Color.navy700)
                            .background(on ? chipColor(key) : Color.cardBG, in: Capsule())
                            .overlay(Capsule().strokeBorder(on ? .clear : Color.line))
                    }.buttonStyle(.plain)
                }
            }.padding(.horizontal, 2)
        }
    }

    private func dealCard(_ opp: Opportunity) -> some View {
        MariaCard {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(opp.title).font(.system(size: 15, weight: .semibold)).foregroundStyle(Color.ink)
                    Text("\(money(opp.pipeline_value_usd)) · \(opp.stage.replacingOccurrences(of: "_", with: " ").capitalized)")
                        .font(.system(size: 12.5)).foregroundStyle(Color.muted)
                }
                Spacer(minLength: 6)
                healthLabel(opp.health)
            }
            MiniBar(fraction: stageFraction(opp.stage), tint: healthColor(opp.health))
            if opp.health == "at_risk" {
                SuggestionCard(text: "No recent activity. Maria suggests a check-in.", action: "Act ›", onTap: openChat)
            }
        }
    }

    // MARK: helpers
    private func countFor(_ key: String) -> Int {
        switch key {
        case "open": model.activeCount
        case "risk": model.atRiskCount
        case "won":  model.all.filter { $0.stage == "won" }.count
        case "lost": model.all.filter { $0.stage == "lost" }.count
        default:     model.all.count
        }
    }
    private func chipColor(_ key: String) -> Color { key == "won" ? .ok : key == "lost" ? .risk : .navy700 }
    private func healthColor(_ h: String) -> Color { h == "at_risk" ? .risk : h == "watch" ? .warn : .ok }
    private func healthLabel(_ h: String) -> some View {
        let txt = h == "at_risk" ? "At-risk" : h == "watch" ? "Watch" : "Healthy"
        return HStack(spacing: 5) {
            Circle().fill(healthColor(h)).frame(width: 7, height: 7)
            Text(txt).font(.system(size: 11.5, weight: .semibold)).foregroundStyle(healthColor(h))
        }
    }
    private func stageFraction(_ stage: String) -> Double {
        let order = ["lead", "visit", "qualified", "proposal_tech", "proposal_commercial", "quotation", "contract", "won"]
        if stage == "lost" { return 1.0 }
        guard let i = order.firstIndex(of: stage) else { return 0.2 }
        return Double(i + 1) / Double(order.count)
    }
    private func money(_ v: Double) -> String {
        if v >= 1_000_000 { return String(format: "$%.1fM", v / 1_000_000) }
        if v >= 1_000 { return String(format: "$%.0fk", v / 1_000) }
        return "$\(Int(v))"
    }
}
