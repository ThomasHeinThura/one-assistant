import Foundation

#if canImport(FoundationModels)
import FoundationModels
#endif

/// On-device LLM facade. Two engines, tried in order:
///   1. **llama.cpp** (LocalLlamaEngine) — the dependable, fully-offline path that
///      works on any iOS 16+ device + simulator once its GGUF model is downloaded.
///   2. **Apple FoundationModels** (Apple Intelligence) — used when available on
///      iOS 26 hardware; zero download, but only on eligible devices.
/// Inference runs entirely on the phone — nothing leaves the device, so this is the
/// engine for confidential (Tier-1) drafting and for private chat. Both engines can
/// be absent (e.g. older simulator) — callers then fall back to the cloud.
enum OnDeviceAI {
    enum Status: Equatable {
        case ready
        case unavailable(String)
    }

    /// "Ready" means at least one on-device engine is available to attempt. For
    /// llama.cpp that's "compiled in" — the model downloads on first generate().
    static var status: Status {
        if LocalLlamaEngine.isCompiledIn { return .ready }
        #if canImport(FoundationModels)
        if #available(iOS 26.0, *) {
            switch SystemLanguageModel.default.availability {
            case .available: return .ready
            case .unavailable(let reason): return .unavailable(Self.reasonText(reason))
            @unknown default: return .unavailable("unavailable")
            }
        }
        #endif
        return .unavailable("no on-device engine on this device")
    }

    static var isReady: Bool { status == .ready }

    static var statusLabel: String {
        switch status {
        case .ready: return "On-device model ready"
        case .unavailable(let why): return "On-device model: \(why)"
        }
    }

    /// Generate a reply fully on-device. Tries llama.cpp first, then Apple's model.
    /// Throws `OnDeviceError.unavailable` if neither engine can produce a reply, so
    /// callers can fall back to the cloud path.
    static func generate(prompt: String, instructions: String) async throws -> String {
        // 1) llama.cpp — primary, offline, works everywhere once the model is local.
        if LocalLlamaEngine.isCompiledIn {
            do {
                return try await LocalLlamaEngine.shared.generate(prompt: prompt, instructions: instructions)
            } catch {
                // Fall through to Apple's model (download may have failed / no network).
            }
        }

        // 2) Apple FoundationModels — only on eligible iOS 26 hardware.
        #if canImport(FoundationModels)
        if #available(iOS 26.0, *) {
            switch SystemLanguageModel.default.availability {
            case .available:
                let session = LanguageModelSession(instructions: instructions)
                let response = try await session.respond(to: prompt)
                return response.content.trimmingCharacters(in: .whitespacesAndNewlines)
            default:
                break
            }
        }
        #endif

        throw OnDeviceError.unavailable
    }

    #if canImport(FoundationModels)
    @available(iOS 26.0, *)
    private static func reasonText(_ reason: SystemLanguageModel.Availability.UnavailableReason) -> String {
        switch reason {
        case .deviceNotEligible:            return "device not eligible"
        case .appleIntelligenceNotEnabled:  return "enable Apple Intelligence in Settings"
        case .modelNotReady:                return "model downloading — try again shortly"
        @unknown default:                   return "unavailable"
        }
    }
    #endif
}

enum OnDeviceError: LocalizedError {
    case unavailable
    var errorDescription: String? { "The on-device model isn't available on this device." }
}
