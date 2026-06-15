import Foundation

#if canImport(LLM)
import LLM
#endif

/// On-device LLM via **llama.cpp** (vendored LLM.swift + prebuilt xcframework).
/// This is the primary private/offline engine: it runs a small GGUF model fully on
/// the phone — nothing leaves the device. The model is downloaded once on first use
/// into the app's Documents directory, then loaded locally for every later call.
///
/// Unlike Apple FoundationModels, this works on any iOS 16+ device and the
/// simulator (subject to the one-time model download), so it's the dependable
/// on-device path for confidential (Tier-1) drafting and private chat.
actor LocalLlamaEngine {
    static let shared = LocalLlamaEngine()

    /// Gemma 2B Instruct, 4-bit (≈1.5 GB GGUF). Downloaded once, then cached.
    /// For a much faster first-run download, swap to a 0.5B model, e.g.
    ///   repo = "bartowski/Qwen2.5-0.5B-Instruct-GGUF", template = .chatML()
    private let repo = "bartowski/gemma-2-2b-it-GGUF"

    enum EngineError: LocalizedError {
        case notCompiledIn, loadFailed(String), emptyResponse
        var errorDescription: String? {
            switch self {
            case .notCompiledIn: "On-device llama engine isn't bundled in this build."
            case .loadFailed(let s): "On-device model couldn't load: \(s)"
            case .emptyResponse: "On-device model returned nothing."
            }
        }
    }

    /// True when the llama.cpp module is linked into this build (regardless of
    /// whether the model weights have been downloaded yet).
    nonisolated static var isCompiledIn: Bool {
        #if canImport(LLM)
        true
        #else
        false
        #endif
    }

    private(set) var downloadProgress: Double = 0
    private(set) var modelReady = false

    #if canImport(LLM)
    private var bot: LLM?

    /// Lazily download (first run) + load the model. Actor isolation serialises
    /// concurrent callers so the heavy load happens exactly once.
    private func ensureBot() async throws -> LLM {
        if let bot { return bot }
        let model = HuggingFaceModel(repo, .Q4_K_M, template: .gemma)
        let loaded = try await LLM(from: model) { progress in
            Task { await LocalLlamaEngine.shared.setProgress(progress) }
        }
        guard let loaded else { throw EngineError.loadFailed("init returned nil") }
        bot = loaded
        modelReady = true
        return loaded
    }

    private func setProgress(_ p: Double) { downloadProgress = p }
    #endif

    /// Generate a reply fully on-device. Throws if the engine isn't available or
    /// the model can't be loaded, so callers can fall back to the cloud path.
    func generate(prompt: String, instructions: String) async throws -> String {
        #if canImport(LLM)
        let bot = try await ensureBot()
        // Gemma's chat template has no system role, so fold instructions into the turn.
        let full = instructions.isEmpty ? prompt : "\(instructions)\n\n\(prompt)"
        var captured = ""
        await bot.respond(to: full) { stream in
            var s = ""
            for await chunk in stream { s += chunk }
            captured = s
            return s
        }
        let out = captured.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !out.isEmpty else { throw EngineError.emptyResponse }
        return out
        #else
        throw EngineError.notCompiledIn
        #endif
    }
}
