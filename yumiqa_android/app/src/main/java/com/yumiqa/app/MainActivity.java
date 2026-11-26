package com.yumiqa.app;

import android.annotation.SuppressLint;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import androidx.activity.OnBackPressedCallback;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AppCompatActivity;

public class MainActivity extends AppCompatActivity {

    private static final String APP_URL = "https://aikyudo-6d3n8m5yhzqubjdnr4bbax.streamlit.app/";
    private static final String PREF_NAME = "yumiqa_auth_pref";
    private static final String KEY_AUTH_TOKEN = "auth_token";

    private WebView webView;
    private View splashView;
    private ValueCallback<Uri[]> fileUploadCallback;

    public class WebAppInterface {
        @JavascriptInterface
        public void saveAuth(String token) {
            if (token != null && !token.trim().isEmpty()) {
                getSharedPreferences(PREF_NAME, MODE_PRIVATE)
                        .edit()
                        .putString(KEY_AUTH_TOKEN, token.trim())
                        .apply();
                CookieManager.getInstance().flush();
            }
        }

        @JavascriptInterface
        public void clearAuth() {
            getSharedPreferences(PREF_NAME, MODE_PRIVATE)
                    .edit()
                    .remove(KEY_AUTH_TOKEN)
                    .apply();
            CookieManager.getInstance().flush();
        }
    }

    private void checkAndSaveAuthFromUrl(String url) {
        if (url != null && url.contains("auth=")) {
            try {
                Uri uri = Uri.parse(url);
                String token = uri.getQueryParameter("auth");
                if (token != null && !token.trim().isEmpty()) {
                    getSharedPreferences(PREF_NAME, MODE_PRIVATE)
                            .edit()
                            .putString(KEY_AUTH_TOKEN, token.trim())
                            .apply();
                    CookieManager.getInstance().flush();
                }
            } catch (Exception ignored) {}
        }
    }

    private final ActivityResultLauncher<Intent> fileChooserLauncher = registerForActivityResult(
            new ActivityResultContracts.StartActivityForResult(),
            result -> {
                if (fileUploadCallback == null) return;
                Uri[] results = null;
                if (result.getResultCode() == RESULT_OK && result.getData() != null) {
                    Intent data = result.getData();
                    if (data.getClipData() != null) {
                        int count = data.getClipData().getItemCount();
                        results = new Uri[count];
                        for (int i = 0; i < count; i++) {
                            results[i] = data.getClipData().getItemAt(i).getUri();
                        }
                    } else if (data.getData() != null) {
                        results = new Uri[]{data.getData()};
                    }
                }
                fileUploadCallback.onReceiveValue(results);
                fileUploadCallback = null;
            }
    );

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // ハードウェアアクセラレーションをウィンドウレベルで強制有効化（ストリーミング描画を高速・超スムーズに）
        getWindow().setFlags(
                WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED,
                WindowManager.LayoutParams.FLAG_HARDWARE_ACCELERATED
        );

        androidx.core.view.WindowCompat.setDecorFitsSystemWindows(getWindow(), false);
        setContentView(R.layout.activity_main);

        View rootContainer = findViewById(R.id.rootContainer);
        if (rootContainer != null) {
            androidx.core.view.ViewCompat.setOnApplyWindowInsetsListener(rootContainer, (v, windowInsets) -> {
                androidx.core.graphics.Insets insets = windowInsets.getInsets(
                        androidx.core.view.WindowInsetsCompat.Type.systemBars() |
                        androidx.core.view.WindowInsetsCompat.Type.displayCutout() |
                        androidx.core.view.WindowInsetsCompat.Type.ime()
                );
                v.setPadding(insets.left, insets.top, insets.right, insets.bottom);
                return windowInsets;
            });
        }

        webView = findViewById(R.id.webView);
        splashView = findViewById(R.id.splashView);

        // GPU ハードウェアアクセラレーションを明示
        webView.setLayerType(View.LAYER_TYPE_HARDWARE, null);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setTextZoom(100);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);

        // 高速描画・ストリーミング滑らか化（オフスクリーン事前ラスタライズ）
        settings.setOffscreenPreRaster(true);
        webView.setOverScrollMode(View.OVER_SCROLL_IF_CONTENT_SCROLLS);

        // 永続ログインブリッジの登録
        webView.addJavascriptInterface(new WebAppInterface(), "AndroidAuth");

        // Cookie & 認証情報の高速同期
        CookieManager cookieManager = CookieManager.getInstance();
        cookieManager.setAcceptCookie(true);
        cookieManager.setAcceptThirdPartyCookies(webView, true);

        // 戻るボタンのハンドリング
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                if (webView.canGoBack()) {
                    webView.goBack();
                } else {
                    setEnabled(false);
                    getOnBackPressedDispatcher().onBackPressed();
                }
            }
        });

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String url = request.getUrl().toString();
                checkAndSaveAuthFromUrl(url);
                if (url.startsWith("http://") || url.startsWith("https://")) {
                    return false;
                }
                try {
                    Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
                    startActivity(intent);
                    return true;
                } catch (Exception e) {
                    return false;
                }
            }

            @Override
            public void doUpdateVisitedHistory(WebView view, String url, boolean isReload) {
                super.doUpdateVisitedHistory(view, url, isReload);
                checkAndSaveAuthFromUrl(url);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                checkAndSaveAuthFromUrl(url);
                if (splashView != null && splashView.getVisibility() == View.VISIBLE) {
                    splashView.animate()
                            .alpha(0f)
                            .setDuration(400)
                            .withEndAction(() -> splashView.setVisibility(View.GONE));
                }
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView webView, ValueCallback<Uri[]> filePathCallback, FileChooserParams fileChooserParams) {
                if (fileUploadCallback != null) {
                    fileUploadCallback.onReceiveValue(null);
                }
                fileUploadCallback = filePathCallback;

                Intent intent = fileChooserParams.createIntent();
                try {
                    fileChooserLauncher.launch(intent);
                } catch (Exception e) {
                    fileUploadCallback = null;
                    return false;
                }
                return true;
            }
        });

        if (savedInstanceState == null) {
            SharedPreferences prefs = getSharedPreferences(PREF_NAME, MODE_PRIVATE);
            String savedToken = prefs.getString(KEY_AUTH_TOKEN, null);
            Uri initialUri = Uri.parse(APP_URL);
            if (savedToken != null && !savedToken.trim().isEmpty()) {
                initialUri = initialUri.buildUpon()
                        .appendQueryParameter("auth", savedToken.trim())
                        .build();
            }
            webView.loadUrl(initialUri.toString());
        } else {
            webView.restoreState(savedInstanceState);
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        CookieManager.getInstance().flush();
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        if (webView != null) {
            webView.saveState(outState);
        }
    }
}
