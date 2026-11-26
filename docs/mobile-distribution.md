# YUMIQA モバイルアプリのビルドと配布

## Android

`.github/workflows/android_build.yml` はJava 17 / Gradle 8.9でAPKをビルドします。GitHub ActionsのArtifactsから `YUMIQA-Android-APKs` をダウンロードできます。Actionsを手動実行することもできます。

- 署名Secretsが未設定の場合は、実機テスト・サイドロード用の `debug` APKだけを生成します。
- Google Play配布や継続アップデート用には、GitHub Actions Secretsに次の4項目を設定してください。すべて設定された場合のみ署名済み `release` APKを生成します。
  - `ANDROID_KEYSTORE_BASE64`: リリース用keystoreのBase64
  - `ANDROID_KEYSTORE_PASSWORD`
  - `ANDROID_KEY_ALIAS`
  - `ANDROID_KEY_PASSWORD`
- 同じ署名鍵を安全にバックアップし、今後のアップデートにも使い続けてください。鍵を紛失すると、既存インストールに更新を配布できなくなります。
- `yumiqa_android/local.properties` と `yumiqa_android/yumiqa.keystore` はローカル専用で、Gitには登録しません。

Windows PowerShellでkeystoreをBase64化する場合:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\path\to\release.keystore"))
```

ローカルのdebug APKはJDK 17、Android SDK Platform 35、Gradle 8.9を用意し、`yumiqa_android`で次を実行すると生成できます。

```powershell
gradle --no-daemon :app:assembleDebug
```

成果物は `yumiqa_android/app/build/outputs/apk/debug/app-debug.apk` です。リリース署名は環境変数 `ANDROID_KEYSTORE_FILE`、`ANDROID_KEYSTORE_PASSWORD`、`ANDROID_KEY_ALIAS`、`ANDROID_KEY_PASSWORD` で設定します。

## iOS

`.github/workflows/ios_build.yml` は未署名IPAをビルドし、GitHub ActionsのArtifactsと `ios-latest` Releaseへ出力します。未署名IPAはSideloadly等で署名して個人端末にインストールする用途です。無料Apple IDで署名したアプリは通常7日ごとの再署名が必要です。

TestFlight / App Store向けの署名と提出は自動化していません。macOS上のXcodeとApple Developer Teamで署名し、App Store Connectへ提出してください。アプリは公開中のWeb版をWebViewで表示するため、ネットワーク接続が必要です。
