import SwiftUI

/// Backend URL + API token entry. The token is stored in the Keychain (never in
/// source — the repo is public). MVP has no login yet, so this is how you connect.
struct SettingsView: View {
    @Environment(\.dismiss) private var dismiss
    var onSave: () -> Void = {}

    @State private var baseURL = ""
    @State private var token = ""
    @State private var saved = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Backend") {
                    TextField("API base URL", text: $baseURL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                }
                Section {
                    SecureField("API bearer token", text: $token)
                } header: {
                    Text("Authentication")
                } footer: {
                    Text("Stored securely in the device Keychain. Get this from your backend `.env` (API_TOKEN).")
                }
                if Config.hasToken {
                    Section {
                        Button("Sign out (clear token)", role: .destructive) {
                            TokenStore.clear(); token = ""
                        }
                    }
                }
            }
            .navigationTitle("Settings")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Save") {
                        Config.setBaseURL(baseURL)
                        let t = token.trimmingCharacters(in: .whitespacesAndNewlines)
                        if !t.isEmpty { TokenStore.save(t) }
                        onSave()
                        dismiss()
                    }.fontWeight(.semibold)
                }
                ToolbarItem(placement: .topBarLeading) { Button("Cancel") { dismiss() } }
            }
            .onAppear {
                baseURL = Config.apiBaseURL.absoluteString
                token = TokenStore.load() ?? ""
            }
        }
    }
}
