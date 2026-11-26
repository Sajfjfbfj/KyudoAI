# YUMIQA iOS 版プロジェクト

Android APK (`MainActivity.java`) と同じ仕様の iOS (`WKWebView` / SwiftUI) アプリプロジェクトです。

## 主な機能
- `WKWebView` による YUMIQA アプリ表示（動画・写真のカメラ撮影・フォトライブラリ選択対応）
- `UserDefaults` + `iOSAuth` ブリッジによる自動ログイン・ワンタップログイン維持
- Streamlit Cloud 下部バッジの非表示化

## Windows だけで iPhone に入れる方法（Mac 不要・無料 Apple ID 可）
1. GitHub の **Releases（`ios-latest`）** または **Actions → Build iOS App (Unsigned) → Artifacts** から `YUMIQA-unsigned.ipa` をダウンロードします。
2. Windows PC に以下をインストールします（Microsoft Store 版ではなく Apple 公式インストーラー版を使用）：
   - iTunes（Windows 用公式版）
   - iCloud（Windows 用公式版）
   - Sideloadly（`https://sideloadly.io/`）
3. iPhone の **設定 → プライバシーとセキュリティ → デベロッパモード** をオンにして再起動し、USB で Windows に接続します。
4. Sideloadly を開いて `YUMIQA-unsigned.ipa` をドラッグ＆ドロップし、Apple ID を入力して **Start** を押します。
5. 完了後、iPhone の **設定 → 一般 → VPNとデバイス管理** から自分の Apple ID を「信頼」すると起動できます（※ 無料 Apple ID は 7日ごとに Sideloadly で更新が必要です）。

## Mac でのビルド方法（TestFlight / App Store / 実機インストール）
1. Homebrew で XcodeGen をインストール（初回のみ）:
   ```bash
   brew install xcodegen
   ```
2. `ios/` ディレクトリで Xcode プロジェクトを生成して開く:
   ```bash
   cd ios
   xcodegen generate
   open YUMIQA.xcodeproj
   ```
3. Xcode の `Signing & Capabilities` でご自身の Apple Developer Team を選択し、実機ビルドまたは `Product -> Archive` から TestFlight（ベータ版配布）へアップロードしてください。
