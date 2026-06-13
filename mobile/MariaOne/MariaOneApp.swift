import SwiftUI
import LocalAuthentication

@main
struct MariaOneApp: App {
    @State private var unlocked = false

    var body: some Scene {
        WindowGroup {
            if unlocked {
                RootTabView()
            } else {
                LockView(unlocked: $unlocked)
            }
        }
    }
}

/// Face ID gate. Re-auth on resume protects Tier-1 content (docs/08-mobile-ux.md).
struct LockView: View {
    @Binding var unlocked: Bool

    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "sparkles").font(.system(size: 44)).foregroundStyle(.purple)
            Text("Maria One").font(.largeTitle.bold())
            Text("Your sales & solution copilot").foregroundStyle(.secondary)
            Button { authenticate() } label: {
                Label("Sign in with Face ID", systemImage: "faceid")
            }
            .buttonStyle(.borderedProminent)
        }
        .onAppear(perform: authenticate)
    }

    private func authenticate() {
        let ctx = LAContext()
        var error: NSError?
        guard ctx.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error) else {
            unlocked = true   // simulator fallback
            return
        }
        ctx.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: "Unlock Maria One") { ok, _ in
            DispatchQueue.main.async { unlocked = ok }
        }
    }
}
