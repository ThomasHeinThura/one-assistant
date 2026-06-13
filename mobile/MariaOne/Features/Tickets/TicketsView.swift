import SwiftUI

@MainActor
final class TicketsModel: ObservableObject {
    @Published var tickets: [Ticket] = []
    func load() async { tickets = (try? await APIClient.shared.tickets()) ?? [] }
}

struct TicketsView: View {
    @StateObject private var model = TicketsModel()

    var body: some View {
        NavigationStack {
            List(model.tickets) { ticket in
                NavigationLink(value: ticket) {
                    VStack(alignment: .leading) {
                        Text(ticket.title).font(.headline)
                        HStack {
                            Text(ticket.type.replacingOccurrences(of: "_", with: " "))
                            Text("·").foregroundStyle(.secondary)
                            Text(ticket.status)
                        }.font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("Tickets")
            .navigationDestination(for: Ticket.self) { TicketDetailView(ticket: $0) }
            .task { await model.load() }
            .refreshable { await model.load() }
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
