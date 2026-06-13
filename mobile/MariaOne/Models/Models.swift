import Foundation

/// Sensitivity tier decided ON-DEVICE before anything leaves the phone.
enum SensitivityTier: Int, Codable, CaseIterable {
    case confidential = 1   // 🔴 banking/client data — on-device only, never cloud
    case internalUse  = 2   // 🟡 cloud allowed with no-logging enforced
    case publicTest   = 3   // 🟢 any free model

    var label: String {
        switch self {
        case .confidential: return "Confidential"
        case .internalUse:  return "Internal"
        case .publicTest:   return "Public"
        }
    }
}

struct Client: Codable, Identifiable { let id: UUID; let name: String; let account_type: String? }

struct Visit: Codable, Identifiable {
    let id: UUID
    let title: String
    let client_id: UUID
    var status: String
    var sensitivity_tier: Int
}

struct Opportunity: Codable, Identifiable {
    let id: UUID
    let title: String
    let stage: String
    let pipeline_value_usd: Double
    let health: String   // healthy | watch | at_risk
}

struct Ticket: Codable, Identifiable {
    let id: UUID
    let title: String
    let type: String
    var status: String
    let priority: String
    let plane_issue_id: String?
    let sync_source: String   // local | plane (Plane is authoritative for status)
}

struct ActionItem: Codable, Hashable {
    var description: String
    var owner_id: UUID?
    var due_date: String?
}

/// Structured Minutes of Meeting — drafted on-device for Tier 1.
struct MoM: Codable {
    var attendees: [String]
    var discussion: String
    var decisions: [String]
    var next_visit_date: String?
    var drafted_by: String       // on_device | cloud
    var action_items: [ActionItem]
}

struct TodayBrief: Codable {
    struct Glance: Codable {
        let visits_today: Int
        let tickets_to_action: Int
        let healthy_deals: Int
        let at_risk_deals: Int
    }
    let glance: Glance
    let todos: [Todo]
}

struct Todo: Codable, Identifiable {
    let id: UUID
    let title: String
    var status: String
    let source: String   // user | ai
}

struct DispatchTarget: Codable, Identifiable {
    var id: String { destination }
    let destination: String   // crm | plane | notion
    let status: String        // pending | done | failed
    let external_id: String?
}
