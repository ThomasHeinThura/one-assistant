import SwiftUI

struct ChatAnswer: Decodable { let answer: String; let model: String?; let grounded: Bool? }

struct ChatMessage: Identifiable { let id = UUID(); let text: String; let mine: Bool }

@MainActor
final class ChatModel: ObservableObject {
    @Published var messages: [ChatMessage] = [
        .init(text: "Hi — I'm Maria. Ask me about any client, deal, ticket, or what needs attention today.", mine: false)
    ]
    @Published var input = ""
    @Published var thinking = false

    func send() async {
        let q = input.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty, !thinking else { return }
        messages.append(.init(text: q, mine: true)); input = ""
        thinking = true
        defer { thinking = false }
        do {
            let r = try await APIClient.shared.ask(q)
            messages.append(.init(text: r.answer, mine: false))
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
            HStack { Image(systemName: "sparkles").foregroundStyle(.purple); Text("Maria").bold() }
                .padding(.top, 12)
            ScrollView {
                ForEach(model.messages) { m in
                    HStack {
                        if m.mine { Spacer() }
                        Text(m.text)
                            .padding(10)
                            .background(m.mine ? Color.blue.opacity(0.15) : Color.gray.opacity(0.12),
                                        in: RoundedRectangle(cornerRadius: 12))
                        if !m.mine { Spacer() }
                    }.padding(.horizontal)
                }
                if model.thinking {
                    HStack {
                        ProgressView().scaleEffect(0.8)
                        Text("Maria is thinking…").font(.caption).foregroundStyle(.secondary)
                        Spacer()
                    }.padding(.horizontal)
                }
            }
            HStack {
                TextField("Ask about any client, deal, or ticket…", text: $model.input)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { Task { await model.send() } }
                Button("Send") { Task { await model.send() } }
                    .disabled(model.thinking)
            }.padding()
        }
    }
}
