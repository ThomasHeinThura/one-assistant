import SwiftUI

struct ChatAnswer: Decodable { let answer: String; let model: String?; let grounded: Bool? }

struct ChatMessage: Identifiable {
    let id = UUID(); let text: String; let mine: Bool; var engine: String? = nil
}

@MainActor
final class ChatModel: ObservableObject {
    @Published var messages: [ChatMessage] = [
        .init(text: "Hi — I'm Maria. Ask me about your day, a client, or a deal.", mine: false)
    ]
    @Published var input = ""
    @Published var thinking = false

    func send() async {
        let q = input.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty, !thinking else { return }
        messages.append(.init(text: q, mine: true)); input = ""
        thinking = true
        defer { thinking = false }

        // All AI runs in the cloud (backend → Ollama Cloud). The app is a thin client.
        do {
            let r = try await APIClient.shared.ask(q)
            messages.append(.init(text: r.answer, mine: false, engine: "Maria · cloud"))
        } catch {
            let msg = (error as? APIClient.APIError)?.errorDescription ?? "Couldn't reach Maria. Try again."
            messages.append(.init(text: msg, mine: false))
        }
    }
}

struct MariaChatView: View {
    @StateObject private var model = ChatModel()

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 10) {
                        ForEach(model.messages) { m in bubble(m) }
                        if model.thinking {
                            HStack(spacing: 8) {
                                ProgressView().scaleEffect(0.7)
                                Text("Maria is thinking…")
                                    .font(.caption).foregroundStyle(.secondary)
                                Spacer()
                            }.padding(.horizontal)
                        }
                        Color.clear.frame(height: 1).id("bottom")
                    }.padding(.vertical, 12)
                }
                .onChange(of: model.messages.count) { _, _ in
                    withAnimation { proxy.scrollTo("bottom", anchor: .bottom) }
                }
            }
            inputBar
        }
    }

    private var header: some View {
        HStack(spacing: 7) {
            Image(systemName: "sparkles").foregroundStyle(.purple)
            Text("Maria").font(.headline)
            Spacer()
        }
        .padding(.horizontal).padding(.top, 14).padding(.bottom, 8)
    }

    private func bubble(_ m: ChatMessage) -> some View {
        HStack {
            if m.mine { Spacer(minLength: 40) }
            VStack(alignment: m.mine ? .trailing : .leading, spacing: 3) {
                Text(m.text)
                    .padding(10)
                    .background(m.mine ? Color.blue.opacity(0.15) : Color.gray.opacity(0.12),
                                in: RoundedRectangle(cornerRadius: 13))
                if let e = m.engine {
                    Text(e).font(.caption2).foregroundStyle(.secondary)
                }
            }
            if !m.mine { Spacer(minLength: 40) }
        }.padding(.horizontal)
    }

    private var inputBar: some View {
        HStack {
            TextField("Ask about your day, a client, or a deal…", text: $model.input)
                .textFieldStyle(.roundedBorder)
                .onSubmit { Task { await model.send() } }
            Button("Send") { Task { await model.send() } }
                .disabled(model.thinking || model.input.trimmingCharacters(in: .whitespaces).isEmpty)
        }.padding()
    }
}
