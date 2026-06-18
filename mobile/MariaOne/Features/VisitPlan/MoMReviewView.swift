import SwiftUI

/// Structured MoM review/edit before confirm, then per-destination dispatch status
/// after confirm. Drafting happens in the cloud (backend → Ollama Cloud); the app is
/// a thin client. The sensitivity tier is metadata carried on the visit record.
struct MoMReviewView: View {
    let visit: Visit
    let notes: String

    @State private var mom: MoM
    @State private var tier: SensitivityTier
    @State private var momID: UUID?
    @State private var dispatch: [DispatchTarget] = []
    @State private var working = false

    init(visit: Visit, notes: String) {
        self.visit = visit
        self.notes = notes
        _tier = State(initialValue: SensitivityTier(rawValue: visit.sensitivity_tier) ?? .internalUse)
        // Seed the editable draft with the raw notes; the user refines before confirm.
        _mom = State(initialValue: MoM(
            attendees: [], discussion: notes, decisions: [],
            next_visit_date: nil, drafted_by: "cloud", action_items: []))
    }

    var body: some View {
        Form {
            Section {
                HStack {
                    Text("Sensitivity").foregroundStyle(.secondary)
                    Spacer()
                    Text(tier.label).bold()
                        .foregroundStyle(tier == .confidential ? .red : .primary)
                }
                HStack {
                    Text("Drafted").foregroundStyle(.secondary)
                    Spacer()
                    Text("Cloud (Ollama, no-logging)")
                }
            }
            Section {
                TextEditor(text: $mom.discussion).frame(minHeight: 100)
            } header: { Text("Discussion") }
            Section("Decisions") {
                ForEach(mom.decisions.indices, id: \.self) { i in
                    TextField("Decision", text: $mom.decisions[i])
                }
                Button("+ Add decision") { mom.decisions.append("") }
            }
            Section("Action items") {
                ForEach(mom.action_items.indices, id: \.self) { i in
                    TextField("Action", text: $mom.action_items[i].description)
                }
                Button("+ Add action") { mom.action_items.append(ActionItem(description: "")) }
            }
            Section {
                if momID == nil {
                    Button(working ? "Confirming…" : "Confirm & dispatch") { Task { await confirm() } }
                        .disabled(working)
                } else {
                    ForEach(dispatch) { t in
                        HStack {
                            Text(t.destination.uppercased())
                            Spacer()
                            statusBadge(t.status)
                        }
                    }
                }
            } footer: {
                Text("On confirm, one CRM outcome + Plane ticket(s) + Notion note — idempotent, retried.")
            }
        }
        .navigationTitle("Review MoM")
    }

    private func confirm() async {
        working = true; defer { working = false }
        do {
            let id = try await APIClient.shared.saveMoM(visit: visit.id, mom: mom)
            try await APIClient.shared.confirmMoM(id)
            momID = id
            dispatch = (try? await APIClient.shared.dispatchStatus(id)) ?? []
        } catch { /* surface to user in real app */ }
    }

    private func statusBadge(_ s: String) -> some View {
        let color: Color = s == "done" ? .green : s == "failed" ? .red : .orange
        return Text(s).font(.caption.bold()).foregroundStyle(color)
    }
}
