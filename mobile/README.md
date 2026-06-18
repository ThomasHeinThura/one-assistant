# Maria One — iOS app (Swift / SwiftUI)

Native iPhone client. Four tabs (Today · VisitPlan · CRM · Tickets) + the Maria
quick-chat. The app is a **thin cloud client**: all AI (chat, MoM drafting) runs
server-side in the backend, which calls **Ollama Cloud** (`gemma4:31b`). There is
no on-device model — the app just talks to the backend CRM API over HTTPS.

> This is a **structural scaffold**. It is not built here (needs macOS + Xcode 15+).
> Open in Xcode as a new iOS App target and drop these files under the app group.

## Build

1. Xcode → New → App (SwiftUI, iOS 17+), product name `MariaOne`.
2. Add the files under `MariaOne/` to the target.
3. Grant Location permission (`NSLocationWhenInUseUsageDescription`) for GPS check-in.
4. Set `Config.apiBaseURL` and store the API bearer token in the **Keychain**
   (never in `Info.plist` or source).

No Swift packages or on-device model dependencies are required — the app is pure
SwiftUI + URLSession.

## Layout

```
MariaOne/
├── MariaOneApp.swift            # @main, auth gate (Face ID)
├── Config.swift                 # base URL, Keychain token accessor
├── Networking/APIClient.swift   # URLSession async client -> backend
├── Models/Models.swift          # Codable mirrors of the API
└── Features/
    ├── RootTabView.swift        # 4 tabs + chat FAB
    ├── Today/TodayView.swift
    ├── VisitPlan/VisitListView.swift
    ├── VisitPlan/MoMReviewView.swift    # review/edit the MoM, then confirm + dispatch
    ├── CRM/CRMView.swift
    ├── Tickets/TicketsView.swift        # list + detail
    └── Chat/MariaChatView.swift         # cloud chat (POST /chat)
```

## Privacy / data handling

- All AI inference happens in the cloud (backend → Ollama Cloud, which does not log
  or train on prompts). The on-device path was removed, so meeting notes and chat
  leave the phone to the backend over HTTPS.
- The **sensitivity tier** (1/2/3) is an advisory label carried on the visit/MoM for
  classification and audit — it no longer keeps data on-device.
- Re-auth (Face ID) on resume still protects access to the app and its data.
