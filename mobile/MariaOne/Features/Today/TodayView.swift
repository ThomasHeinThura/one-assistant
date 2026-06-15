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
    @Binding var subtitle: String
    var openChat: () -> Void
    @StateObject private var model = TodayModel()

    var body: some View {
        ScreenScroll {
            switch model.state {
            case .loading:
                ProgressView("Loading…").frame(maxWidth: .infinity).padding(.top, 60)
            case .needsToken:
                StatusBlock(icon: "key.fill", title: "Connect to your backend",
                            message: "Add your API token in Settings to load Maria's brief.")
            case .error(let msg):
                StatusBlock(icon: "wifi.exclamationmark", title: "Couldn't load", message: msg,
                            actionTitle: "Retry") { Task { await model.load() } }
            case .empty:
                StatusBlock(icon: "checkmark.circle", title: "All clear",
                            message: "No to-dos or visits for today.")
            case .loaded:
                loaded
            }
        }
        .task {
            await model.load()
            subtitle = subtitleText
        }
        .refreshable { await model.load(); subtitle = subtitleText }
    }

    private var subtitleText: String {
        guard let g = model.brief?.glance else { return "Your sales & solution copilot" }
        let n = (model.brief?.todos.count ?? 0)
        return "\(g.visits_today) visits · Maria has \(n) things for you"
    }

    @ViewBuilder private var loaded: some View {
        let g = model.brief?.glance
        LiveBanner(text: "Maria is following up on \(model.brief?.todos.count ?? 0) items across your CRM, visits and tickets.")

        AIBrief(tag: "Daily brief", orchestrating: true) {
            Text(briefText).font(.system(size: 13.5)).foregroundStyle(Color(hex: 0x2c3a52))
        }

        if let g {
            HStack(spacing: 10) {
                StatCard(value: "\(g.visits_today)", label: "Visits today")
                StatCard(value: "\(g.tickets_to_action)", label: "Tickets to action", tint: .risk)
                StatCard(value: "\(g.healthy_deals)", label: "Healthy deals", tint: .ok)
            }
        }

        Eyebrow(text: "My to-do · AI-prioritised")
        MariaCard {
            let todos = model.brief?.todos ?? []
            if todos.isEmpty {
                Text("Nothing queued.").font(.system(size: 14)).foregroundStyle(Color.muted)
            } else {
                ForEach(Array(todos.enumerated()), id: \.element.id) { idx, todo in
                    TodoRow(todo: todo)
                    if idx < todos.count - 1 { Divider().background(Color.line) }
                }
            }
        }

        SuggestionCard(text: "A deal has had no touch in 21 days. Log a check-in or I can draft a nudge email.",
                       action: "Act ›", onTap: openChat)
    }

    private var briefText: String {
        guard let g = model.brief?.glance else { return "Loading your day…" }
        var s = "\(g.visits_today) visit(s) today. "
        if g.at_risk_deals > 0 { s += "\(g.at_risk_deals) deal(s) look at-risk. " }
        if g.tickets_to_action > 0 { s += "\(g.tickets_to_action) ticket(s) need triage. " }
        s += "I drafted your follow-ups and a sub-agent is preparing quotations."
        return s
    }
}

// MARK: - Todo row

struct TodoRow: View {
    let todo: Todo
    @State private var done: Bool = false

    var body: some View {
        HStack(spacing: 12) {
            Button { done.toggle() } label: {
                RoundedRectangle(cornerRadius: 6)
                    .fill(done ? Color.navy500 : Color.clear)
                    .frame(width: 20, height: 20)
                    .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(done ? Color.navy500 : Color.navy300, lineWidth: 2))
                    .overlay(done ? Image(systemName: "checkmark").font(.system(size: 11, weight: .bold)).foregroundStyle(.white) : nil)
            }.buttonStyle(.plain)
            Text(todo.title).font(.system(size: 14))
                .strikethrough(done, color: .muted)
                .foregroundStyle(done ? Color.muted : Color.ink)
            Spacer(minLength: 6)
            if todo.source == "ai" {
                Chip(text: "Maria drafted", style: .ai)
            }
        }
        .padding(.vertical, 2)
        .onAppear { done = todo.status == "done" }
    }
}

// MARK: - Shared scroll container + status block

struct ScreenScroll<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) { content }
                .padding(.horizontal, 16).padding(.top, 16).padding(.bottom, 120)
        }
        .background(Color.appBG)
    }
}

struct StatusBlock: View {
    let icon: String, title: String, message: String
    var actionTitle: String? = nil
    var action: (() -> Void)? = nil
    var body: some View {
        VStack(spacing: 14) {
            Image(systemName: icon).font(.system(size: 40)).foregroundStyle(Color.muted)
            Text(title).font(.headline)
            Text(message).font(.subheadline).foregroundStyle(Color.muted)
                .multilineTextAlignment(.center)
            if let actionTitle, let action {
                Button(actionTitle, action: action).buttonStyle(.borderedProminent).tint(.navy700)
            }
        }
        .frame(maxWidth: .infinity).padding(.top, 60).padding(.horizontal, 24)
    }
}
