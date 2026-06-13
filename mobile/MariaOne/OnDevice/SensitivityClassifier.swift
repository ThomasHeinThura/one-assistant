import Foundation

/// On-device sensitivity tagger. Runs Gemma 2B via Apple MLX so the decision is
/// made BEFORE any data leaves the phone. This stub uses a keyword heuristic;
/// swap `classify` for the MLX inference call when the model package is added.
struct SensitivityClassifier {

    /// Keywords that force Tier 1 (confidential) — banking/financial client data.
    private static let confidentialMarkers = [
        "bank", "account number", "balance", "ledger", "kyc", "swift", "iban",
        "card number", "pii", "salary", "credentials", "password",
    ]

    func classify(agenda: String, notes: String) -> SensitivityTier {
        let text = (agenda + " " + notes).lowercased()
        if Self.confidentialMarkers.contains(where: text.contains) {
            return .confidential
        }
        // Default to Internal (cloud allowed only with no-logging); never default
        // to Public for real client meetings.
        return .internalUse
    }
}
