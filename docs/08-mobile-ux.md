# 08 — Mobile UX & Gestures

**Project:** Maria One

Quality-of-life gestures and mobile behaviours. Some are demonstrated in the HTML mockup; most are
**implemented in the final native iOS (Swift / SwiftUI) app**, where the platform gestures are
first-class. Each item is tagged accordingly.

Tags: 🟢 in HTML mockup · 📱 final app only

## Sheets & modals

- 🟢 **Swipe-down to dismiss.** Drag the grab handle (the pill at the top of a sheet) downward past a
  threshold to close it — no need to tap outside. Implemented for the editor sheet and the Maria
  chat sheet in the mockup.
- 📱 **Drag anywhere on the sheet header** (not just the handle), with rubber-band resistance.
- 📱 **Velocity-based dismiss.** A quick flick down closes even before the distance threshold.
- 📱 **Interactive scrim.** The background dims progressively as you drag the sheet down.
- 📱 **Detents.** Sheets support medium/large heights (`.presentationDetents([.medium, .large])`);
  drag up to expand, down to collapse then dismiss.
- 📱 **Keyboard-aware.** The sheet lifts above the keyboard; the grab handle stays reachable.
- 📱 **Haptic on dismiss/commit.** Light haptic when a sheet snaps closed or an action is confirmed.

## Navigation gestures

- 📱 **Edge-swipe back.** Swipe from the left edge to pop the current detail screen (native
  `NavigationStack` interactive pop).
- 📱 **Swipe between tabs.** Horizontal swipe across the content area moves between Today / VisitPlan
  / CRM / Tickets.
- 📱 **Pull-to-refresh.** Pull down at the top of any list to refresh + trigger a RAG re-index check.
- 📱 **Tap status bar to scroll to top.** Native iOS behaviour on long lists.

## Lists & cards

- 📱 **Swipe actions on rows.** Swipe a to-do, deal, or ticket for quick actions (Done, Assign,
  Snooze, Delegate to Maria) without opening it.
- 📱 **Long-press context menu.** Press-and-hold a card for a preview + quick actions.
- 📱 **Drag to reorder** to-dos and pipeline stages.
- 📱 **Section index / sticky headers** on long client lists.

## Input & capture

- 📱 **Voice capture** for visit notes (feeds the MoM) — the later audio-MoM feature.
- 📱 **Share-sheet ingest** — send content into Maria One from other apps.
- 📱 **Quick actions (long-press app icon)** — New ticket, Plan visit, Ask Maria.
- 📱 **Live Activities / Dynamic Island** — show an in-progress visit or a running Maria sub-agent.

## Feedback & polish

- 🟢 **Live status banners + coordination toasts** (shown in the mockup).
- 📱 **Haptics** — selection ticks on segmented controls, success/error notifications on submit.
- 📱 **Skeleton loaders** while lists/RAG answers load.
- 📱 **Optimistic UI** — actions apply instantly, then reconcile when the verifier confirms (see
  [07-datastore.md](07-datastore.md)); a subtle "syncing" dot until `verified`.
- 📱 **Dark mode** — full support following system appearance.
- 📱 **Dynamic Type & accessibility** — scalable fonts, VoiceOver labels, reduced-motion fallbacks.
- 📱 **Offline + reconnect** — queued changes show a pending state and flush on reconnect.

## Auth

- 🟢 **Face ID sign-in** (mocked in the HTML).
- 📱 **Real Face ID / Touch ID** via `LocalAuthentication`, with passcode fallback and re-auth on
  resume for confidential (Tier-1) data.

## Why most of this is "final app only"

The HTML mockup is for validating layout, flow, and look. True gesture physics (interactive pop,
detents, velocity dismiss, swipe actions, haptics) come from UIKit/SwiftUI and can't be faithfully
reproduced in a single static HTML file — so they're specified here as build requirements rather
than forced into the prototype.
