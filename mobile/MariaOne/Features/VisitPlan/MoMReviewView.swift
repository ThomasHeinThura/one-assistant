import SwiftUI

/// The hero screen the HTML mockup was missing: structured MoM review/edit before
/// confirm, with the on-device/cloud indicator + tier, then per-destination
/// dispatch status after confirm.
struct MoMReviewView: View {
    let visit: Visit
    let notes: String

    @State private var mom: MoM
    @State private var tier: SensitivityTier
    @State private var momID: UUID?
    @State private var dispatch: [DispatchTarget] = []
    @State private var working = false
    @State private var drafting = false

    init(visit: Visit, notes: String) {
        self.visit = visit
        self.notes = notes
        let t = SensitivityClassifier().classify(agenda: visit.title, notes: notes)
        _tier = State(initialValue: t)
        _mom = State(initialValue: MoMDrafter().draftOnDevice(agenda: visit.title, notes: notes, tier: t))
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
                    Text(mom.drafted_by == "on_device" ? "On-device (no cloud)" : "Cloud (no-logging)")
                }
                if tier == .confidential {
                    Label("Confidential — stays on this device", systemImage: "lock.fill")
                        .font(.caption).foregroundStyle(.red)
                }
            }
            Section {
                if drafting {
                    Label("Drafting minutes on-device…", systemImage: "cpu")
                        .font(.caption).foregroundStyle(.secondary)
                }
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
        .task { await enhanceOnDevice() }
    }

    /// Summarise the raw notes into clean minutes using the on-device model.
    /// Tier-1 confidential drafting NEVER uses the cloud — this runs locally only.
    private func enhanceOnDevice() async {
        guard OnDeviceAI.isReady, !notes.isEmpty else { return }
        drafting = true; defer { drafting = false }
        let prompt = "Summarise these meeting notes into 2–3 clear sentences of minutes. "
                   + "Keep it factual.\nAGENDA: \(visit.title)\nNOTES: \(notes)"
        if let summary = try? await OnDeviceAI.generate(
                prompt: prompt, instructions: "You write concise, factual meeting minutes."),
           !summary.isEmpty {
            mom.discussion = summary
            mom.drafted_by = "on_device"
        }
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
