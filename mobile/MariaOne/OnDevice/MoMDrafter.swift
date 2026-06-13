import Foundation

/// Drafts the Minutes of Meeting. For Tier 1 the draft happens ENTIRELY on-device
/// (MLX Gemma) and `drafted_by` is "on_device" — no network LLM call is made.
/// For Tier 2/3 the caller may instead ask the backend (OpenRouter, no-logging).
struct MoMDrafter {

    /// On-device draft. Replace the body with an MLX Gemma 2B generate() call.
    func draftOnDevice(agenda: String, notes: String, tier: SensitivityTier) -> MoM {
        // Heuristic placeholder so the review screen has structured content to show.
        let decisions = notes
            .split(whereSeparator: \.isNewline)
            .filter { $0.lowercased().contains("agree") || $0.lowercased().contains("decide") }
            .map(String.init)

        return MoM(
            attendees: [],
            discussion: notes.isEmpty ? agenda : notes,
            decisions: decisions,
            next_visit_date: nil,
            drafted_by: "on_device",
            action_items: []
        )
    }

    /// Guard used by the UI: Tier 1 must never be eligible for a cloud draft.
    func cloudDraftAllowed(for tier: SensitivityTier) -> Bool { tier != .confidential }
}
