# YUMIQA iOS 版プロジェクト

Android APK (`MainActivity.java`) と同じ仕様の iOS (`WKWebView` / SwiftUI) アプリプロジェクトです。

## 主な機能
- `WKWebView` による YUMIQA アプリ表示（動画・写真のカメラ撮影・フォトライブラリ選択対応）
- `UserDefaults` + `iOSAuth` ブリッジによる自動ログイン・ワンタップログイン維持
- Streamlit Cloud 下部バッジの非表示化

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
