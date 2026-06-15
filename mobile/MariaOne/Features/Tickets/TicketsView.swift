import SwiftUI

@MainActor
final class TicketsModel: ObservableObject {
    @Published var tickets: [Ticket] = []
    @Published var loaded = false
    func load() async {
        tickets = (try? await APIClient.shared.tickets()) ?? []
        loaded = true
    }

    var open: [Ticket] { tickets.filter { $0.status != "done" } }
    func countType(_ t: String) -> Int { tickets.filter { $0.type == t && $0.status != "done" }.count }
    func countStatus(_ s: String) -> Int { tickets.filter { $0.status == s }.count }
    var attention: [Ticket] {
        tickets.filter { $0.status == "new" || $0.status == "triaged"
            || $0.priority == "high" || $0.priority == "urgent" }
    }
}

struct TicketsView: View {
    @Binding var subtitle: String
    var openChat: () -> Void
    @StateObject private var model = TicketsModel()

    var body: some View {
        NavigationStack {
            ScreenScroll {
                LiveBanner(text: "Maria triages incoming tickets and balances the team workload.")

                AIBrief(tag: "Management summary") {
                    Text(summary).font(.system(size: 13.5)).foregroundStyle(Color(hex: 0x2c3a52))
                }

                HStack(spacing: 10) {
                    StatCard(value: "\(model.open.count)", label: "Open")
                    StatCard(value: "\(model.countType("managed_service"))", label: "Managed Svc")
                    StatCard(value: "\(model.countType("project"))", label: "Projects")
                }

                Eyebrow(text: "By status")
                statusFunnel

                Eyebrow(text: "Needs your attention")
                if model.loaded && model.attention.isEmpty {
                    MariaCard {
                        Text("Nothing needs triage right now. 🎉").font(.system(size: 14)).foregroundStyle(Color.muted)
                    }
                }
                ForEach(model.attention) { t in
                    NavigationLink(value: t) { attentionCard(t) }.buttonStyle(.plain)
                }

                Eyebrow(text: "Ask Maria")
                SuggestionCard(text: "\"Who has the most open tickets?\" · \"Open MS tickets\" · \"Create a ticket\"",
                               action: "Chat ›", onTap: openChat)
            }
            .navigationBarHidden(true)
            .navigationDestination(for: Ticket.self) { TicketDetailView(ticket: $0) }
            .task { await model.load(); subtitle = "\(model.open.count) open · Projects & Managed Service" }
            .refreshable { await model.load() }
        }
    }

    private var summary: String {
        let unassigned = model.countStatus("new")
        return "\(model.open.count) open ticket(s). \(unassigned) awaiting triage. "
            + "\(model.countType("managed_service")) Managed-Service, \(model.countType("project")) Project, \(model.countType("cr")) Change-Request."
    }

    private var statusFunnel: some View {
        let rows: [(String, String, Color)] = [
            ("New", "new", .warn), ("Assigned", "assigned", .navy500),
            ("In progress", "in_progress", .navy500), ("Review", "review", .navy300),
            ("Done", "done", .ok),
        ]
        let maxC = max(1, rows.map { model.countStatus($0.1) }.max() ?? 1)
        return MariaCard {
            ForEach(rows, id: \.1) { name, key, color in
                HStack(spacing: 10) {
                    Text(name).font(.system(size: 13.5, weight: .semibold)).frame(width: 90, alignment: .leading)
                    MiniBar(fraction: Double(model.countStatus(key)) / Double(maxC), tint: color, height: 18)
                    Text("\(model.countStatus(key))").font(.system(size: 12.5, weight: .bold))
                        .frame(width: 24, alignment: .trailing)
                }
            }
        }
    }

    private func attentionCard(_ t: Ticket) -> some View {
        let urgent = t.priority == "high" || t.priority == "urgent"
        return MariaCard {
            HStack(spacing: 12) {
                Text(urgent ? "⏱" : "!").font(.system(size: 15, weight: .bold))
                    .frame(width: 40, height: 40)
                    .foregroundStyle(urgent ? Color.warn : Color.risk)
                    .background(urgent ? Color.warnBG : Color.riskBG, in: RoundedRectangle(cornerRadius: 12))
                VStack(alignment: .leading, spacing: 2) {
                    Text(t.title).font(.system(size: 15, weight: .semibold)).foregroundStyle(Color.ink)
                    Text(t.type.replacingOccurrences(of: "_", with: " ").capitalized + " · " + t.priority.capitalized)
                        .font(.system(size: 12.5)).foregroundStyle(Color.muted)
                }
                Spacer(minLength: 6)
                Chip(text: t.status == "new" ? "Unassigned" : t.status.capitalized,
                     style: t.status == "new" ? .risk : .warn)
            }
        }
    }
}

extension Ticket: Hashable {
    static func == (l: Ticket, r: Ticket) -> Bool { l.id == r.id }
    func hash(into h: inout Hasher) { h.combine(id) }
}

/// "Check the ticket" detail view — the read surface the HTML mockup lacked
/// (every tap there opened the *create* form instead).
struct TicketDetailView: View {
    let ticket: Ticket

    var body: some View {
        Form {
            Section("Status") {
                LabeledContent("Status", value: ticket.status)
                LabeledContent("Priority", value: ticket.priority)
                LabeledContent("Type", value: ticket.type)
            }
            Section("Sync") {
                LabeledContent("Source of truth",
                               value: ticket.sync_source == "plane" ? "Plane (authoritative)" : "Local")
                if let pid = ticket.plane_issue_id {
                    LabeledContent("Plane issue", value: pid)
                }
            }
        }
        .navigationTitle(ticket.title)
    }
}
