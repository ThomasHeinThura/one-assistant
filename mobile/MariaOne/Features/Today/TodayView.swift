import SwiftUI

@MainActor
final class TodayModel: ObservableObject {
    enum State { case loading, loaded, empty, error(String), needsToken }
    @Published var brief: TodayBrief?
    @Published var state: State = .loading

    func load() async {
        if !Config.hasToken { state = .needsToken; return }
        state = .loading
        do {
            let b = try await APIClient.shared.today()
            brief = b
            state = (b.todos.isEmpty && b.glance.visits_today == 0 && b.glance.tickets_to_action == 0) ? .empty : .loaded
        } catch APIClient.APIError.unauthorized {
            state = .needsToken
        } catch {
            state = .error((error as? LocalizedError)?.errorDescription ?? "\(error)")
        }
    }
}

struct TodayView: View {
    @StateObject private var model = TodayModel()
    @State private var showSettings = false

    var body: some View {
        NavigationStack {
            Group {
                switch model.state {
                case .loading:
                    ProgressView("Loading…").frame(maxWidth: .infinity, maxHeight: .infinity)
                case .needsToken:
                    StatusView(icon: "key.fill", title: "Connect to your backend",
                               message: "Add your API token to load Maria's brief.",
                               actionTitle: "Open Settings") { showSettings = true }
                case .error(let msg):
                    StatusView(icon: "wifi.exclamationmark", title: "Couldn't load",
                               message: msg, actionTitle: "Retry") { Task { await model.load() } }
                case .empty:
                    StatusView(icon: "checkmark.circle", title: "All clear",
                               message: "No to-dos or visits for today.", actionTitle: nil, action: {})
                case .loaded:
                    briefList
                }
            }
            .navigationTitle("Today")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { showSettings = true } label: { Image(systemName: "gearshape") }
                }
            }
            .refreshable { await model.load() }
            .task { await model.load() }
            .sheet(isPresented: $showSettings) {
                SettingsView { Task { await model.load() } }
            }
        }
    }

    private var briefList: some View {
        List {
            if let g = model.brief?.glance {
                Section("Maria's daily brief") {
                    HStack {
                        stat("\(g.visits_today)", "Visits")
                        stat("\(g.tickets_to_action)", "To action")
                        stat("\(g.healthy_deals)", "Healthy")
                        stat("\(g.at_risk_deals)", "At-risk")
                    }
                }
            }
            Section("My to-do · AI-prioritised") {
                if (model.brief?.todos ?? []).isEmpty {
                    Text("Nothing queued.").foregroundStyle(.secondary)
                }
                ForEach(model.brief?.todos ?? []) { todo in
                    HStack {
                        Image(systemName: todo.status == "done" ? "checkmark.square.fill" : "square")
                            .foregroundStyle(todo.status == "done" ? .green : .secondary)
                        Text(todo.title)
                        Spacer()
                        if todo.source == "ai" {
                            Text("Maria").font(.caption2).padding(.horizontal, 6).padding(.vertical, 2)
                                .background(.purple.opacity(0.15), in: Capsule())
                        }
                    }
                }
            }
        }
    }

    private func stat(_ n: String, _ l: String) -> some View {
        VStack(spacing: 2) { Text(n).font(.title3.bold()); Text(l).font(.caption2).foregroundStyle(.secondary) }
            .frame(maxWidth: .infinity)
    }
}

/// Reusable empty/error/needs-token state.
struct StatusView: View {
    let icon: String, title: String, message: String
    let actionTitle: String?
    let action: () -> Void

    var body: some View {
        VStack(spacing: 14) {
            Image(systemName: icon).font(.system(size: 40)).foregroundStyle(.secondary)
            Text(title).font(.headline)
            Text(message).font(.subheadline).foregroundStyle(.secondary)
                .multilineTextAlignment(.center).padding(.horizontal, 32)
            if let actionTitle {
                Button(actionTitle, action: action).buttonStyle(.borderedProminent)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
