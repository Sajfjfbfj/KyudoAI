import SwiftUI

@main
struct YUMIQAApp: App {
    @State private var isLoading = true

    var body: some Scene {
        WindowGroup {
            ZStack {
                WebViewContainer(isLoading: $isLoading)
                    .ignoresSafeArea(.container, edges: [.bottom])

                if isLoading {
                    ZStack {
                        Color(red: 0.08, green: 0.13, blue: 0.22)
                            .ignoresSafeArea()
                        VStack(spacing: 16) {
                            Text("YUMIQA")
                                .font(.system(size: 30, weight: .bold, design: .serif))
                                .foregroundColor(.white)
                            ProgressView()
                                .progressViewStyle(CircularProgressViewStyle(tint: .white))
                        }
                    }
                    .transition(.opacity)
                }
            }
        }
    }
}
