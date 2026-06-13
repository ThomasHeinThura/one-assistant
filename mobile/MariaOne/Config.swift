import Foundation
import Security

/// App configuration. The API base URL is environment-specific; the bearer token
/// lives in the Keychain, never in source or Info.plist.
enum Config {
    static let defaultBaseURL = "https://api.technexus.info"
    private static let baseURLKey = "maria.apiBaseURL"

    /// Resolved API base URL: Settings override → env (simulator) → default.
    static var apiBaseURL: URL {
        let s = UserDefaults.standard.string(forKey: baseURLKey)
            ?? ProcessInfo.processInfo.environment["MARIA_API_URL"]
            ?? defaultBaseURL
        return URL(string: s) ?? URL(string: defaultBaseURL)!
    }

    static func setBaseURL(_ s: String) {
        let trimmed = s.trimmingCharacters(in: .whitespacesAndNewlines)
        UserDefaults.standard.set(trimmed.isEmpty ? defaultBaseURL : trimmed, forKey: baseURLKey)
    }

    /// Bearer token: Keychain (entered in Settings) → env (simulator/debug only).
    static var apiToken: String? {
        if let t = TokenStore.load(), !t.isEmpty { return t }
        if let e = ProcessInfo.processInfo.environment["MARIA_API_TOKEN"], !e.isEmpty { return e }
        return nil
    }

    static var hasToken: Bool { apiToken != nil }
}

/// Minimal Keychain wrapper for the API bearer token.
enum TokenStore {
    private static let account = "maria.api.token"

    static func save(_ token: String) {
        let data = Data(token.utf8)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(query as CFDictionary)
        var add = query
        add[kSecValueData as String] = data
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        SecItemAdd(add as CFDictionary, nil)
    }

    static func load() -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
        ]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else { return nil }
        return String(decoding: data, as: UTF8.self)
    }

    static func clear() {
        SecItemDelete([
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: account,
        ] as CFDictionary)
    }
}
