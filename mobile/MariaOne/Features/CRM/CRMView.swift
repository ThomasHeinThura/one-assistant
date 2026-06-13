import SwiftUI

@MainActor
final class CRMModel: ObservableObject {
    @Published var opps: [Opportunity] = []
    @Published var filter = "all"
    func load() async { opps = (try? await APIClient.shared.opportunities(filter: filter)) ?? [] }
}

struct CRMView: View {
    @StateObject private var model = CRMModel()
    private let filters = ["all", "open", "risk", "won", "lost"]

    var body: some View {
        NavigationStack {
            VStack {
                Picker("Filter", selection: $model.filter) {
                    ForEach(filters, id: \.self) { Text($0.capitalized) }
                }
                .pickerStyle(.segmented).padding(.horizontal)
                .onChange(of: model.filter) { Task { await model.load() } }

                List(model.opps) { opp in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(opp.title).font(.headline)
                        HStack {
                            Text("$\(Int(opp.pipeline_value_usd)) · \(opp.stage)")
                                .font(.caption).foregroundStyle(.secondary)
                            Spacer()
                            healthBadge(opp.health)
                        }
                    }
                }
            }
            .navigationTitle("CRM")
            .task { await model.load() }
            .refreshable { await model.load() }
        }
    }

    private func healthBadge(_ h: String) -> some View {
        let color: Color = h == "at_risk" ? .red : h == "watch" ? .orange : .green
        return Label(h.replacingOccurrences(of: "_", with: "-"), systemImage: "circle.fill")
            .font(.caption2).foregroundStyle(color)
    }
}
