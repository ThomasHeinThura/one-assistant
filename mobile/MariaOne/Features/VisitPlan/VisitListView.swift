import SwiftUI
import CoreLocation

@MainActor
final class VisitModel: ObservableObject {
    @Published var visits: [Visit] = []
    @Published var loaded = false
    func load() async {
        visits = (try? await APIClient.shared.visits()) ?? []
        loaded = true
    }
}

struct VisitListView: View {
    @Binding var subtitle: String
    @StateObject private var model = VisitModel()

    var body: some View {
        NavigationStack {
            ScreenScroll {
                Eyebrow(text: "Today's visits")

                if model.loaded && model.visits.isEmpty {
                    StatusBlock(icon: "mappin.slash", title: "No visits planned",
                                message: "Plan a client visit to start the MoM → dispatch workflow.")
                }

                ForEach(model.visits) { visit in
                    NavigationLink(value: visit) { visitCard(visit) }.buttonStyle(.plain)
                }

                Eyebrow(text: "Per-visit SOP")
                MariaCard {
                    Text("Check-in (GPS) → agenda → notes → AI MoM → status update → dispatch (CRM · Plane · Notion).")
                        .font(.system(size: 13)).foregroundStyle(Color(hex: 0x34465f))
                }
            }
            .navigationBarHidden(true)
            .navigationDestination(for: Visit.self) { VisitDetailView(visit: $0) }
            .task { await model.load(); subtitle = "\(model.visits.count) visits · each has MoM + workflow" }
            .refreshable { await model.load() }
        }
    }

    private func visitCard(_ visit: Visit) -> some View {
        MariaCard {
            HStack(spacing: 12) {
                Text(initials(visit.title)).font(.system(size: 15, weight: .bold))
                    .foregroundStyle(Color.navy700)
                    .frame(width: 40, height: 40).background(Color.navy50, in: RoundedRectangle(cornerRadius: 12))
                VStack(alignment: .leading, spacing: 2) {
                    Text(visit.title).font(.system(size: 15, weight: .semibold)).foregroundStyle(Color.ink)
                    Text(visit.status.replacingOccurrences(of: "_", with: " ").capitalized)
                        .font(.system(size: 12.5)).foregroundStyle(Color.muted)
                }
                Spacer(minLength: 6)
                tierBadge(SensitivityTier(rawValue: visit.sensitivity_tier) ?? .internalUse)
            }
            if visit.status == "in_progress" || visit.status == "scheduled" {
                SuggestionCard(text: "Workflow: Visit → MoM → link to pipeline → raise RFI → follow-up ticket.",
                               action: "Run ›")
            }
        }
    }

    private func initials(_ s: String) -> String {
        let parts = s.split(separator: " ").prefix(2)
        return parts.map { String($0.prefix(1)) }.joined().uppercased()
    }

    private func tierBadge(_ tier: SensitivityTier) -> some View {
        let style: ChipStyle = tier == .confidential ? .risk : tier == .internalUse ? .warn : .ok
        return Chip(text: tier.label, style: style)
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
