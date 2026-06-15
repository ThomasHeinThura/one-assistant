import SwiftUI

enum Tab: String, CaseIterable {
    case today, visit, crm, tickets
    var title: String {
        switch self { case .today: "Today"; case .visit: "VisitPlan"; case .crm: "CRM"; case .tickets: "Tickets" }
    }
    var icon: String {
        switch self {
        case .today: "circle.grid.cross"; case .visit: "mappin.and.ellipse"
        case .crm: "chart.line.uptrend.xyaxis"; case .tickets: "square.stack.3d.up"
        }
    }
    var tabLabel: String {
        switch self { case .today: "Today"; case .visit: "Visits"; case .crm: "CRM"; case .tickets: "Tickets" }
    }
}

struct RootTabView: View {
    @State private var tab: Tab = .today
    @State private var showChat = false
    @State private var showSettings = false
    @State private var subtitle = "Your sales & solution copilot"

    var body: some View {
        ZStack(alignment: .bottom) {
            Color.appBG.ignoresSafeArea()

            VStack(spacing: 0) {
                header
                content
            }

            // Purple chat FAB, sitting just above the tab bar.
            Button { showChat = true } label: {
                Text("✦").font(.system(size: 22)).foregroundStyle(.white)
                    .frame(width: 54, height: 54)
                    .background(aiOrbGradient, in: Circle())
                    .shadow(color: .ai.opacity(0.45), radius: 12, x: 0, y: 10)
            }
            .frame(maxWidth: .infinity, alignment: .trailing)
            .padding(.trailing, 16).padding(.bottom, 74)

            tabBar
        }
        .sheet(isPresented: $showChat) {
            MariaChatView().presentationDetents([.medium, .large])
        }
        .sheet(isPresented: $showSettings) {
            SettingsView { }
        }
        .onAppear {
            let env = ProcessInfo.processInfo.environment
            if env["MARIA_ONDEVICE_SELFTEST"] == "1" { showChat = true }
            // QA/screenshot helper: deep-link the initial tab (today|visit|crm|tickets).
            if let t = env["MARIA_START_TAB"], let start = Tab(rawValue: t) { tab = start }
        }
    }

    // MARK: header
    private var header: some View {
        VStack(spacing: 0) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("MARIA ONE").font(.system(size: 12, weight: .semibold)).tracking(2)
                        .foregroundStyle(Color.navy300)
                    Text(tab.title).font(.system(size: 23, weight: .bold)).foregroundStyle(.white)
                    Text(subtitle).font(.system(size: 13)).foregroundStyle(Color(hex: 0xc6d6ea))
                }
                Spacer()
                Button { showSettings = true } label: {
                    Text("HT").font(.system(size: 14, weight: .bold)).foregroundStyle(.white)
                        .frame(width: 38, height: 38).background(Color.navy500, in: Circle())
                }
            }
            .padding(.horizontal, 20).padding(.top, 8).padding(.bottom, 18)
        }
        .background(navyGradient.ignoresSafeArea(edges: .top))
    }

    // MARK: screen content
    @ViewBuilder private var content: some View {
        switch tab {
        case .today:   TodayView(subtitle: $subtitle, openChat: { showChat = true })
        case .visit:   VisitListView(subtitle: $subtitle)
        case .crm:     CRMView(subtitle: $subtitle, openChat: { showChat = true })
        case .tickets: TicketsView(subtitle: $subtitle, openChat: { showChat = true })
        }
    }

    // MARK: custom tab bar
    private var tabBar: some View {
        HStack {
            ForEach(Tab.allCases, id: \.self) { t in
                Button { tab = t } label: {
                    VStack(spacing: 3) {
                        Image(systemName: t.icon).font(.system(size: 17))
                        Text(t.tabLabel).font(.system(size: 10.5, weight: .semibold))
                    }
                    .frame(maxWidth: .infinity)
                    .foregroundStyle(tab == t ? Color.navy700 : Color.muted)
                }
            }
        }
        .padding(.top, 8).padding(.horizontal, 6)
        .background(.regularMaterial)
        .overlay(Divider(), alignment: .top)
    }
}
