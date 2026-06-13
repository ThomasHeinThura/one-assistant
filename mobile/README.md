# Maria One — iOS app (Swift / SwiftUI)

Native iPhone client. Four tabs (Today · VisitPlan · CRM · Tickets) + the Maria
quick-chat. The **on-device Gemma 2B (Apple MLX)** drafts the MoM and assigns the
sensitivity tier *before anything leaves the phone*; the app then talks to the
backend CRM API over HTTPS.

> This is a **structural scaffold**. It is not built here (needs macOS + Xcode 15+).
> Open in Xcode as a new iOS App target and drop these files under the app group,
> or use the included `Package.swift` for the model/networking layer.

## Build

1. Xcode → New → App (SwiftUI, iOS 17+), product name `MariaOne`.
2. Add the files under `MariaOne/` to the target.
3. Add **MLX Swift** (`github.com/ml-explore/mlx-swift`) + an MLX Gemma 2B
   package for on-device drafting (`OnDevice/`), and grant Location permission
   (`NSLocationWhenInUseUsageDescription`) for GPS check-in.
4. Set `Config.apiBaseURL` and store the API bearer token in the **Keychain**
   (never in `Info.plist` or source).

## Layout

```
MariaOne/
├── MariaOneApp.swift            # @main, auth gate (Face ID)
├── Config.swift                 # base URL, Keychain token accessor
├── Networking/APIClient.swift   # URLSession async client -> backend
├── Models/Models.swift          # Codable mirrors of the API
├── OnDevice/
│   ├── SensitivityClassifier.swift  # Gemma/MLX -> Tier 1/2/3 (on-device)
│   └── MoMDrafter.swift             # on-device MoM draft (Tier 1 never leaves)
└── Features/
    ├── RootTabView.swift        # 4 tabs + chat FAB
    ├── Today/TodayView.swift
    ├── VisitPlan/VisitListView.swift
    ├── VisitPlan/MoMReviewView.swift    # the hero screen the mockup lacked
    ├── CRM/CRMView.swift
    ├── Tickets/TicketsView.swift        # list + DETAIL (the "check ticket" gap)
    └── Chat/MariaChatView.swift
```

## Privacy / tier rules enforced in the app

- The classifier tags each visit **on-device**. **Tier 1 → MoM drafted locally,
  no network LLM call ever.** The app sends `drafted_by: on_device` and the
  backend re-checks (`assert_cloud_allowed`) as defense in depth.
- Re-auth (Face ID) on resume before showing Tier-1 content.
