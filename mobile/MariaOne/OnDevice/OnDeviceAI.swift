import Foundation

#if canImport(FoundationModels)
import FoundationModels
#endif

/// On-device LLM via Apple's **FoundationModels** (Apple Intelligence foundation
/// model). Inference runs entirely on the phone — nothing leaves the device, so
/// this is the engine for confidential (Tier-1) drafting and for private chat.
/// Falls back gracefully when the OS/device can't provide the model.
enum OnDeviceAI {
    enum Status: Equatable {
        case ready
        case unavailable(String)
    }

    static var status: Status {
        #if canImport(FoundationModels)
        if #available(iOS 26.0, *) {
            switch SystemLanguageModel.default.availability {
            case .available:
                return .ready
            case .unavailable(let reason):
                return .unavailable(Self.reasonText(reason))
            @unknown default:
                return .unavailable("unavailable")
            }
        }
        #endif
        return .unavailable("Requires iOS 26 (Apple Intelligence)")
    }

    static var isReady: Bool { status == .ready }

    static var statusLabel: String {
        switch status {
        case .ready: return "On-device model ready"
        case .unavailable(let why): return "On-device model: \(why)"
        }
    }

    /// Generate a reply fully on-device. Throws `OnDeviceError.unavailable` if the
    /// model isn't usable, so callers can fall back to the cloud path.
    static func generate(prompt: String, instructions: String) async throws -> String {
        #if canImport(FoundationModels)
        if #available(iOS 26.0, *) {
            guard isReady else { throw OnDeviceError.unavailable }
            let session = LanguageModelSession(instructions: instructions)
            let response = try await session.respond(to: prompt)
            return response.content.trimmingCharacters(in: .whitespacesAndNewlines)
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
