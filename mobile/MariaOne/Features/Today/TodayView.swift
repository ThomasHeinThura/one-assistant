import SwiftUI

@MainActor
final class TodayModel: ObservableObject {
    @Published var brief: TodayBrief?
    @Published var error: String?

    func load() async {
        do { brief = try await APIClient.shared.today() }
        catch { self.error = "\(error)" }
    }
}

struct TodayView: View {
    @StateObject private var model = TodayModel()

    var body: some View {
        NavigationStack {
            List {
                if let g = model.brief?.glance {
                    Section {
                        HStack {
                            stat("\(g.visits_today)", "Visits")
                            stat("\(g.tickets_to_action)", "To action")
                            stat("\(g.healthy_deals)", "Healthy")
                        }
                    } header: { Text("Maria’s daily brief") }
                }
                Section("My to-do · AI-prioritised") {
                    ForEach(model.brief?.todos ?? []) { todo in
                        HStack {
                            Image(systemName: todo.status == "done" ? "checkmark.square.fill" : "square")
                            Text(todo.title)
                            Spacer()
                            if todo.source == "ai" {
                                Text("Maria").font(.caption2).padding(.horizontal, 6)
                                    .background(.purple.opacity(0.15), in: Capsule())
                            }
                        }
                    }
                }
            }
            .navigationTitle("Today")
            .refreshable { await model.load() }   // pull-to-refresh triggers reindex check
            .task { await model.load() }
            .overlay { if let e = model.error { Text(e).foregroundStyle(.red).font(.footnote) } }
        }
    }

    private func stat(_ n: String, _ l: String) -> some View {
        VStack { Text(n).font(.title2.bold()); Text(l).font(.caption).foregroundStyle(.secondary) }
            .frame(maxWidth: .infinity)
    }
}
