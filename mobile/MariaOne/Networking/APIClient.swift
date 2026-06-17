import Foundation

/// Thin async URLSession client to the backend CRM API.
/// The phone NEVER speaks MCP — Plane/Notion stay server-side (architecture §MCP).
actor APIClient {
    static let shared = APIClient()

    private let session = URLSession(configuration: .default)
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()

    enum APIError: LocalizedError {
        case unauthorized, http(Int), offline

        var errorDescription: String? {
            switch self {
            case .unauthorized: return "Not signed in — add your API token in Settings."
            case .offline:      return "Can't reach the server. Check your connection or the API URL."
            case .http(let c):  return "Server error (HTTP \(c))."
            }
        }
    }

    private func request(_ path: String, method: String = "GET", body: Encodable? = nil) async throws -> Data {
        var req = URLRequest(url: Config.apiBaseURL.appendingPathComponent(path))
        req.httpMethod = method
        req.timeoutInterval = 15
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token = Config.apiToken {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body { req.httpBody = try encoder.encode(AnyEncodable(body)) }

        let data: Data, resp: URLResponse
        do {
            (data, resp) = try await session.data(for: req)
        } catch {
            throw APIError.offline
        }
        let code = (resp as? HTTPURLResponse)?.statusCode ?? -1
        if code == 401 || code == 403 { throw APIError.unauthorized }
        guard (200..<300).contains(code) else { throw APIError.http(code) }
        return data
    }

    private func get<T: Decodable>(_ path: String) async throws -> T {
        try decoder.decode(T.self, from: try await request(path))
    }

    // MARK: Endpoints
    func today() async throws -> TodayBrief { try await get("today") }
    func visits() async throws -> [Visit] { try await get("visits") }
    func opportunities(filter: String = "all") async throws -> [Opportunity] {
        try await get("opportunities?filter=\(filter)")
    }
    func tickets() async throws -> [Ticket] { try await get("tickets") }
    func ticket(_ id: UUID) async throws -> Ticket { try await get("tickets/\(id)") }

    /// Ask Maria — RAG/CRM-grounded answer from the backend (cloud Tier 2/3).
    func ask(_ question: String) async throws -> ChatAnswer {
        struct Body: Encodable { let question: String }
        let data = try await request("chat", method: "POST", body: Body(question: question))
        return try decoder.decode(ChatAnswer.self, from: data)
    }

    func checkIn(visit: UUID, lat: Double, lng: Double) async throws {
        struct Body: Encodable { let lat: Double; let lng: Double }
        _ = try await request("visits/\(visit)/checkin", method: "POST", body: Body(lat: lat, lng: lng))
    }

    /// Save the cloud-drafted MoM, then confirm to trigger the 3-system fan-out.
    func saveMoM(visit: UUID, mom: MoM) async throws -> UUID {
        struct Created: Decodable { let id: UUID }
        let data = try await request("visits/\(visit)/mom", method: "POST", body: mom)
        return try decoder.decode(Created.self, from: data).id
    }
    func confirmMoM(_ momID: UUID) async throws {
        _ = try await request("visits/mom/\(momID)/confirm", method: "POST")
    }
    func dispatchStatus(_ momID: UUID) async throws -> [DispatchTarget] {
        try await get("visits/mom/\(momID)/dispatch")
    }
}

/// Type-erasing wrapper so `Encodable` values can be encoded generically.
private struct AnyEncodable: Encodable {
    private let encodeFunc: (Encoder) throws -> Void
    init(_ wrapped: Encodable) { encodeFunc = wrapped.encode }
    func encode(to encoder: Encoder) throws { try encodeFunc(encoder) }
}
