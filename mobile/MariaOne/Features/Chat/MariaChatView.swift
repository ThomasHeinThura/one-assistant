import SwiftUI

struct ChatMessage: Identifiable { let id = UUID(); let text: String; let mine: Bool }

@MainActor
final class ChatModel: ObservableObject {
    @Published var messages: [ChatMessage] = [
        .init(text: "Morning. Thai Bank’s SLA deal is at-risk — 21 days quiet. Want a check-in draft?", mine: false)
    ]
    @Published var input = ""

    func send() async {
        let q = input.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty else { return }
        messages.append(.init(text: q, mine: true)); input = ""
        // Backend /chat is the RAG-grounded answer (AgentScope + Qdrant in M2).
        messages.append(.init(text: "On it — checking CRM, visits, and tickets…", mine: false))
    }
}

struct MariaChatView: View {
    @StateObject private var model = ChatModel()

    var body: some View {
        VStack {
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
            }
            HStack {
                TextField("Ask about any client, deal, or ticket…", text: $model.input)
                    .textFieldStyle(.roundedBorder)
                Button("Send") { Task { await model.send() } }
            }.padding()
        }
    }
}
