import SwiftUI
import WebKit

struct WebViewContainer: UIViewRepresentable {
    @Binding var isLoading: Bool

    static let appURL = "https://aikyudo-6d3n8m5yhzqubjdnr4bbax.streamlit.app/"
    private static let authTokenKey = "yumiqa_auth_token"
    private static let lastAuthTokenKey = "yumiqa_last_auth_token"

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    func makeUIView(context: Context) -> WKWebView {
        let contentController = WKUserContentController()
        contentController.add(context.coordinator, name: "iOSAuth")

        // app.py 側の window.AndroidAuth 呼び出しをそのまま iOS 側で受け取る互換ブリッジ
        let bridgeJS = """
        window.AndroidAuth = {
            saveAuth: function(token) {
                try {
                    window.webkit.messageHandlers.iOSAuth.postMessage({ action: 'save', token: String(token || '') });
                } catch(e) {}
            },
            clearAuth: function() {
                try {
                    window.webkit.messageHandlers.iOSAuth.postMessage({ action: 'clear' });
                } catch(e) {}
            }
        };
        """
        let bridgeScript = WKUserScript(source: bridgeJS, injectionTime: .atDocumentStart, forMainFrameOnly: false)
        contentController.addUserScript(bridgeScript)

        let config = WKWebViewConfiguration()
        config.userContentController = contentController
        config.allowsInlineMediaPlayback = true
        config.mediaTypesRequiringUserActionForPlayback = []
        config.websiteDataStore = .default()

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.scrollView.bounces = false
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        webView.allowsBackForwardNavigationGestures = true
        webView.isOpaque = false
        webView.backgroundColor = UIColor(red: 0.98, green: 0.97, blue: 0.95, alpha: 1.0)

        let savedToken = UserDefaults.standard.string(forKey: Self.authTokenKey) ?? ""
        let initialString: String
        if !savedToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
           let encoded = savedToken.trimmingCharacters(in: .whitespacesAndNewlines).addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) {
            initialString = "\(Self.appURL)?auth=\(encoded)"
        } else {
            initialString = Self.appURL
        }

        if let url = URL(string: initialString) {
            webView.load(URLRequest(url: url))
        }
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler {
        private let parent: WebViewContainer

        init(_ parent: WebViewContainer) {
            self.parent = parent
        }

        func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
            guard message.name == "iOSAuth",
                  let body = message.body as? [String: Any],
                  let action = body["action"] as? String else { return }

            if action == "save", let token = body["token"] as? String {
                let clean = token.trimmingCharacters(in: .whitespacesAndNewlines)
                if !clean.isEmpty {
                    UserDefaults.standard.set(clean, forKey: WebViewContainer.authTokenKey)
                    UserDefaults.standard.set(clean, forKey: WebViewContainer.lastAuthTokenKey)
                }
            } else if action == "clear" {
                UserDefaults.standard.removeObject(forKey: WebViewContainer.authTokenKey)
            }
        }

        private func saveAuthFromURL(_ url: URL?) {
            guard let url = url,
                  let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
                  let token = components.queryItems?.first(where: { $0.name == "auth" })?.value else { return }
            let clean = token.trimmingCharacters(in: .whitespacesAndNewlines)
            if !clean.isEmpty {
                UserDefaults.standard.set(clean, forKey: WebViewContainer.authTokenKey)
                UserDefaults.standard.set(clean, forKey: WebViewContainer.lastAuthTokenKey)
            }
        }

        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            if let url = navigationAction.request.url {
                saveAuthFromURL(url)
                let scheme = url.scheme?.lowercased() ?? ""
                if scheme != "http" && scheme != "https" && scheme != "about" {
                    UIApplication.shared.open(url)
                    decisionHandler(.cancel)
                    return
                }
            }
            decisionHandler(.allow)
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            saveAuthFromURL(webView.url)

            // ネイティブ保存済みの最終トークンを localStorage へ同期（ワンタップ復帰維持）
            if let lastTok = UserDefaults.standard.string(forKey: WebViewContainer.lastAuthTokenKey),
               !lastTok.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                let safeTok = lastTok.trimmingCharacters(in: .whitespacesAndNewlines).replacingOccurrences(of: "'", with: "\\'")
                let syncJS = "try{if(!localStorage.getItem('yumiqa_last_tok')){localStorage.setItem('yumiqa_last_tok','\(safeTok)');}}catch(e){}"
                webView.evaluateJavaScript(syncJS, completionHandler: nil)
            }

            // Streamlit Cloud 下部バッジ非表示
            let hideBadgeJS = """
            (function(){
                if(document.getElementById('yumiqa-hide-st-badge')) return;
                var s=document.createElement('style'); s.id='yumiqa-hide-st-badge';
                s.textContent='[class*="viewerBadge"],[class*="profileContainer"],[class*="terminalButton"],[data-testid="manage-app-button"],[data-testid="stStatusWidget"],[data-testid="stToolbarActions"],footer,a[href*="streamlit.io"]{display:none!important;visibility:hidden!important;pointer-events:none!important;opacity:0!important;}';
                (document.head||document.documentElement).appendChild(s);
            })();
            """
            webView.evaluateJavaScript(hideBadgeJS, completionHandler: nil)

            DispatchQueue.main.async {
                withAnimation(.easeOut(duration: 0.35)) {
                    self.parent.isLoading = false
                }
            }
        }
    }
}
