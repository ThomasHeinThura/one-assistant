import SwiftUI
import CoreLocation

@MainActor
final class VisitModel: ObservableObject {
    @Published var visits: [Visit] = []
    func load() async { visits = (try? await APIClient.shared.visits()) ?? [] }
}

struct VisitListView: View {
    @StateObject private var model = VisitModel()

    var body: some View {
        NavigationStack {
            List(model.visits) { visit in
                NavigationLink(value: visit) {
                    VStack(alignment: .leading) {
                        HStack {
                            Text(visit.title).font(.headline)
                            Spacer()
                            tierBadge(SensitivityTier(rawValue: visit.sensitivity_tier) ?? .internalUse)
                        }
                        Text(visit.status.capitalized).font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("VisitPlan")
            .navigationDestination(for: Visit.self) { VisitDetailView(visit: $0) }
            .task { await model.load() }
            .refreshable { await model.load() }
        }
    }

    private func tierBadge(_ tier: SensitivityTier) -> some View {
        let color: Color = tier == .confidential ? .red : tier == .internalUse ? .orange : .green
        return Text(tier.label).font(.caption2.bold()).padding(.horizontal, 7).padding(.vertical, 2)
            .background(color.opacity(0.15), in: Capsule()).foregroundStyle(color)
    }
}

extension Visit: Hashable {
    static func == (l: Visit, r: Visit) -> Bool { l.id == r.id }
    func hash(into h: inout Hasher) { h.combine(id) }
}

/// Per-visit SOP: check-in (GPS) → agenda → notes → MoM → confirm → dispatch.
struct VisitDetailView: View {
    let visit: Visit
    @State private var notes = ""
    @State private var goReview = false
    private let locationManager = CLLocationManager()

    var body: some View {
        Form {
            Section("Check-in") {
                Button {
                    locationManager.requestWhenInUseAuthorization()
                    let c = locationManager.location?.coordinate
                    Task { try? await APIClient.shared.checkIn(
                        visit: visit.id, lat: c?.latitude ?? 0, lng: c?.longitude ?? 0) }
                } label: { Label("Check in (GPS)", systemImage: "location.fill") }
            }
            Section("Notes") {
                TextEditor(text: $notes).frame(minHeight: 120)
            }
            Section {
                Button("Draft MoM →") { goReview = true }.disabled(notes.isEmpty)
            }
        }
        .navigationTitle(visit.title)
        .navigationDestination(isPresented: $goReview) {
            MoMReviewView(visit: visit, notes: notes)
        }
    }
}
