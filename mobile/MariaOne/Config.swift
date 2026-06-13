import Foundation
import Security

/// App configuration. The API base URL is environment-specific; the bearer token
/// lives in the Keychain, never in source or Info.plist.
enum Config {
    /// Point at the Azure ingress in release; localhost for the simulator.
    static let apiBaseURL = URL(string: ProcessInfo.processInfo.environment["MARIA_API_URL"]
        ?? "https://api.maria-one.example.com")!
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
}
