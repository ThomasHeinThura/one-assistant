import SwiftUI

struct ChatAnswer: Decodable { let answer: String; let model: String?; let grounded: Bool? }

struct ChatMessage: Identifiable {
    let id = UUID(); let text: String; let mine: Bool; var engine: String? = nil
}

@MainActor
final class ChatModel: ObservableObject {
    enum Engine: String, CaseIterable, Identifiable {
        case onDevice = "On-device"
        case cloud = "Cloud"
        var id: String { rawValue }
    }

    @Published var messages: [ChatMessage] = [
        .init(text: "Hi — I'm Maria. Ask me about your day, a client, or a deal. "
                  + "On-device mode keeps everything private on this phone.", mine: false)
    ]
    @Published var input = ""
    @Published var thinking = false
    @Published var engine: Engine
    @Published var deviceReady: Bool
    @Published var deviceNote: String

    private let instructions =
        "You are Maria, a concise, friendly sales & solution work assistant. "
      + "Answer in 1–3 short sentences. Be practical and suggest a useful next step when relevant."

    init() {
        let ready = OnDeviceAI.isReady
        deviceReady = ready
        engine = ready ? .onDevice : .cloud
        if case .unavailable(let why) = OnDeviceAI.status { deviceNote = why } else { deviceNote = "ready" }
    }

    /// Diagnostic: when launched with MARIA_ONDEVICE_SELFTEST=1, fire one prompt so
    /// on-device generation can be verified in a headless simulator. Off by default.
    func selfTestIfRequested() async {
        guard ProcessInfo.processInfo.environment["MARIA_ONDEVICE_SELFTEST"] == "1" else { return }
        input = "In one short sentence, what is a good first move with an at-risk deal?"
        await send()
    }

    func send() async {
        let q = input.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty, !thinking else { return }
        messages.append(.init(text: q, mine: true)); input = ""
        thinking = true
        defer { thinking = false }

        if engine == .onDevice, deviceReady {
            do {
                let reply = try await OnDeviceAI.generate(prompt: q, instructions: instructions)
                messages.append(.init(text: reply, mine: false, engine: "On-device · private"))
                return
            } catch {
                // On-device model present but weights not downloaded (e.g. Apple
                // Intelligence off, or running in a simulator) — say so, then use cloud.
                messages.append(.init(
                    text: "On-device model isn't downloaded here (enable Apple Intelligence, or run on a "
                        + "supported device). Answering via the cloud instead:",
                    mine: false, engine: "On-device · unavailable"))
            }
        }

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
                                Text(model.engine == .onDevice && model.deviceReady
                                     ? "Thinking on-device…" : "Maria is thinking…")
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
                .task { await model.selfTestIfRequested() }
            }
            inputBar
        }
    }

    private var header: some View {
        VStack(spacing: 8) {
            HStack(spacing: 7) {
                Image(systemName: "sparkles").foregroundStyle(.purple)
                Text("Maria").font(.headline)
                Spacer()
            }
            Picker("Engine", selection: $model.engine) {
                Label("On-device", systemImage: "lock.fill").tag(ChatModel.Engine.onDevice)
                Label("Cloud", systemImage: "cloud").tag(ChatModel.Engine.cloud)
            }
            .pickerStyle(.segmented)
            .disabled(!model.deviceReady && model.engine == .cloud)
            HStack(spacing: 5) {
                Circle().fill(model.deviceReady ? .green : .orange).frame(width: 7, height: 7)
                Text(model.deviceReady ? "On-device model ready · private"
                                       : "On-device unavailable (\(model.deviceNote)) — using cloud")
                    .font(.caption2).foregroundStyle(.secondary)
                Spacer()
            }
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
