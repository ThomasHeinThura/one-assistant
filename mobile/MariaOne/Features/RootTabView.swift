import SwiftUI

struct RootTabView: View {
    @State private var showChat = false

    var body: some View {
        ZStack(alignment: .bottomTrailing) {
            TabView {
                TodayView().tabItem { Label("Today", systemImage: "circle.grid.cross") }
                VisitListView().tabItem { Label("Visits", systemImage: "mappin.and.ellipse") }
                CRMView().tabItem { Label("CRM", systemImage: "chart.line.uptrend.xyaxis") }
                TicketsView().tabItem { Label("Tickets", systemImage: "square.stack.3d.up") }
            }
            // Persistent Maria quick-chat FAB.
            Button { showChat = true } label: {
                Image(systemName: "sparkles").font(.title2).foregroundStyle(.white)
                    .frame(width: 54, height: 54).background(.purple, in: Circle())
            }
            .padding(.trailing, 18).padding(.bottom, 70)
            .sheet(isPresented: $showChat) {
                MariaChatView().presentationDetents([.medium, .large])
            }
        }
    }
}
