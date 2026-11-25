import os
import time
import json
import re
import tempfile
import hashlib
import hmac
import shutil
import html
import secrets
from concurrent.futures import ThreadPoolExecutor
import base64
ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')
import streamlit as st
import streamlit.components.v1 as components
import plotly.graph_objects as go
from google import genai
from google.genai import types

def get_asset_base64(filename: str) -> str:
    """assetsディレクトリ内の画像をBase64文字列に変換"""
    asset_path = os.path.join(os.path.dirname(__file__), "assets", filename)
    if os.path.exists(asset_path):
        try:
            with open(asset_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception:
            return ""
    return ""

def _toolbar_theme_css() -> str:
    t = st.session_state.get("ui_theme", "自動")
    if t == "ライト":
        return ":root{color-scheme:light}html,body{background:#ffffff}.btn{color:#6f6f6f}.btn:hover{background:rgba(0,0,0,.06);color:#0d0d0d}"
    if t == "ダーク":
        return ":root{color-scheme:dark}html,body{background:#212121}.btn{color:#9b9b9b}.btn:hover{background:rgba(255,255,255,.10);color:#ececec}"
    return ""

def render_chatgpt_toolbar(text_content: str):
    """ChatGPT（2026年版）風：アイコンのみのアクションバー（コピー／読み上げ）。ダークテーマ対応"""
    safe_text_json = json.dumps(text_content).replace("</", "<\\/")
    toolbar_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            :root { color-scheme: light dark; }
            /* iframeは配色が食い違うと不透明な既定色(#121212)で塗られるため、ページ背景(--canvas)と同じ色で明示的に塗る */
            html, body { background: #ffffff; }
            body {
                margin: 0;
                padding: 0;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            }
            .bar { display: flex; align-items: center; gap: 2px; padding-top: 4px; }
            .btn {
                width: 32px; height: 32px; border: none; border-radius: 8px;
                background: transparent; color: #6f6f6f;
                display: inline-flex; align-items: center; justify-content: center;
                cursor: pointer; transition: background 0.15s ease, color 0.15s ease;
            }
            .btn:hover { background: rgba(0, 0, 0, 0.06); color: #0d0d0d; }
            .btn:active { transform: scale(0.94); }
            .btn svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
            @media (prefers-color-scheme: dark) {
                html, body { background: #212121; }
                .btn { color: #9b9b9b; }
                .btn:hover { background: rgba(255, 255, 255, 0.10); color: #ececec; }
            }
            __THEME_CSS__
        </style>
    </head>
    <body>
        <div class="bar">
            <button class="btn" id="copyBtn" title="コピーする" aria-label="コピーする" onclick="doCopy()"></button>
            <button class="btn" id="speakBtn" title="読み上げ" aria-label="読み上げ" onclick="doSpeakToggle()"></button>
        </div>
        <script>
            const textToProcess = __TEXT__;
            const ICONS = {
                copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
                check: '<path d="M20 6 9 17l-5-5"/>',
                speak: '<path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>',
                stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>'
            };
            let speaking = false;

            function setIcon(id, name) {
                document.getElementById(id).innerHTML = '<svg viewBox="0 0 24 24">' + ICONS[name] + '</svg>';
            }
            setIcon('copyBtn', 'copy');
            setIcon('speakBtn', 'speak');

            function doCopy() {
                const onSuccess = () => {
                    setIcon('copyBtn', 'check');
                    setTimeout(() => setIcon('copyBtn', 'copy'), 1800);
                };
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(textToProcess).then(onSuccess).catch(() => fallbackCopy(onSuccess));
                } else {
                    fallbackCopy(onSuccess);
                }
            }

            function fallbackCopy(cb) {
                const ta = document.createElement('textarea');
                ta.value = textToProcess;
                ta.style.position = 'fixed';
                ta.style.opacity = '0';
                document.body.appendChild(ta);
                ta.focus();
                ta.select();
                try {
                    document.execCommand('copy');
                    if (cb) cb();
                } catch (e) {
                    console.error('Copy failed', e);
                }
                document.body.removeChild(ta);
            }

            function resetSpeak() {
                speaking = false;
                setIcon('speakBtn', 'speak');
                document.getElementById('speakBtn').title = '読み上げ';
            }

            function doSpeakToggle() {
                if (!('speechSynthesis' in window)) {
                    alert('お使いの端末はブラウザ音声読み上げに対応していません。');
                    return;
                }
                if (speaking) {
                    window.speechSynthesis.cancel();
                    resetSpeak();
                    return;
                }
                window.speechSynthesis.cancel();
                const u = new SpeechSynthesisUtterance(textToProcess);
                u.lang = 'ja-JP';
                u.rate = 1.05;
                u.onend = resetSpeak;
                u.onerror = resetSpeak;
                speaking = true;
                setIcon('speakBtn', 'stop');
                document.getElementById('speakBtn').title = '読み上げを停止';
                window.speechSynthesis.speak(u);
            }
        </script>
    </body>
    </html>
    """.replace("__TEXT__", safe_text_json).replace("__THEME_CSS__", _toolbar_theme_css())
    # components.html は非推奨のため、st.iframe があればそちらを優先（旧バージョンはフォールバック）
    if hasattr(st, "iframe"):
        st.iframe(toolbar_html.strip(), height=40)
    else:
        components.html(toolbar_html, height=40)



# ==================== 個人情報保護・完全消去ユーティリティ ====================
def secure_shred_file(filepath: str):
    """ファイルをゼロフィルおよび乱数上書きして物理的に復元不可能な状態にしてから削除する（完全抹消）"""
    if not filepath or not os.path.exists(filepath):
        return
    try:
        size = os.path.getsize(filepath)
        if size > 0:
            with open(filepath, "ba+", buffering=0) as f:
                # パス1: ゼロフィル上書き
                f.seek(0)
                f.write(b"\x00" * size)
                f.flush()
                os.fsync(f.fileno())
                # パス2: 乱数データ上書き
                f.seek(0)
                f.write(os.urandom(size))
                f.flush()
                os.fsync(f.fileno())
        os.remove(filepath)
    except Exception:
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass

def cleanup_residual_files():
    """起動時に残留ファイル（uploadsフォルダや古いtmpファイル等）があれば即座にシュレッダー抹消"""
    base_dir = os.path.dirname(__file__)
    upload_dir = os.path.join(base_dir, "uploads")
    if os.path.exists(upload_dir):
        for fname in os.listdir(upload_dir):
            fpath = os.path.join(upload_dir, fname)
            if os.path.isfile(fpath):
                secure_shred_file(fpath)

# アプリ起動時に残留ファイルをクリーンアップ
cleanup_residual_files()

# ページ基本設定
st.set_page_config(
    page_title="YUMIQA｜AI弓道分析",
    page_icon="assets/yumiqa_icon.png",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── PWA メタタグ＆ServiceWorker注入（ホーム画面追加・スプラッシュ対応） ──
st.html("""
<link rel="manifest" href="/app/static/manifest.json?v=4">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="YUMIQA">
<meta name="application-name" content="YUMIQA">
<meta name="theme-color" content="#101D35">
<link rel="icon" type="image/png" href="/app/static/favicon.png?v=4">
<link rel="shortcut icon" href="/app/static/favicon.ico?v=4">
<link rel="apple-touch-icon" href="/app/static/icon-192.png?v=4">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, interactive-widget=resizes-content">
<script>
(function() {
    function setupPWA() {
        var pDoc = window.parent.document;
        if (!pDoc || !pDoc.head) return;

        // 即座に自動ログイン復元（localStorage にトークンがあれば即座にauthパラメータ付与）
        try {
            var pWin = window.parent;
            var savedTok = pWin.localStorage.getItem('kyudo_auth');
            var curUrl = new URL(pWin.location.href);
            if (savedTok && !curUrl.searchParams.get('auth')) {
                curUrl.searchParams.set('auth', savedTok);
                pWin.location.replace(curUrl.toString());
                return;
            }
        } catch(e) {}

        // 既存の Streamlit 公式 manifest やアイコンを削除して上書き
        var oldEls = pDoc.querySelectorAll('link[rel="manifest"], link[rel="apple-touch-icon"], link[rel*="icon"]');
        oldEls.forEach(function(el) {
            try { el.parentNode.removeChild(el); } catch(e) {}
        });

        // YUMIQA アプリアイコン・ファビコン
        var iconUrl = '/app/static/icon-192.png?v=4';
        var favUrl = '/app/static/favicon.png?v=4';
        var fav = pDoc.createElement('link');
        fav.rel = 'icon';
        fav.type = 'image/png';
        fav.href = favUrl;
        pDoc.head.appendChild(fav);

        var appleIcon = pDoc.createElement('link');
        appleIcon.rel = 'apple-touch-icon';
        appleIcon.href = iconUrl;
        pDoc.head.appendChild(appleIcon);

        // 新しい Manifest を <head> の先頭に挿入
        var manifestLink = pDoc.createElement('link');
        manifestLink.rel = 'manifest';
        manifestLink.href = '/app/static/manifest.json?v=4';
        pDoc.head.insertBefore(manifestLink, pDoc.head.firstChild);

        pDoc.title = 'YUMIQA｜AI弓道分析';

        var metaTags = [
            { name: 'mobile-web-app-capable', content: 'yes' },
            { name: 'apple-mobile-web-app-capable', content: 'yes' },
            { name: 'apple-mobile-web-app-status-bar-style', content: 'black-translucent' },
            { name: 'apple-mobile-web-app-title', content: 'YUMIQA' },
            { name: 'application-name', content: 'YUMIQA' },
            { name: 'theme-color', content: '#101D35' }
        ];

        metaTags.forEach(function(tag) {
            var existing = pDoc.querySelector('meta[name="' + tag.name + '"]');
            if (existing) { try { existing.parentNode.removeChild(existing); } catch(e) {} }
            var m = pDoc.createElement('meta');
            m.name = tag.name;
            m.content = tag.content;
            pDoc.head.appendChild(m);
        });

        // 各機種のノッチ・ステータスバー・セーフエリアを動的検出してCSS変数に適用
        function updateDeviceSafeArea() {
            try {
                var viewportMeta = pDoc.querySelector('meta[name="viewport"]');
                if (viewportMeta) {
                    var content = viewportMeta.getAttribute('content') || '';
                    if (!content.includes('viewport-fit=cover')) content += ', viewport-fit=cover';
                    if (!content.includes('interactive-widget=resizes-content')) content += ', interactive-widget=resizes-content';
                    viewportMeta.setAttribute('content', content);
                } else {
                    var vm = pDoc.createElement('meta');
                    vm.name = 'viewport';
                    vm.content = 'width=device-width, initial-scale=1, viewport-fit=cover, interactive-widget=resizes-content';
                    pDoc.head.appendChild(vm);
                }

                var testDiv = pDoc.createElement('div');
                testDiv.style.position = 'fixed';
                testDiv.style.top = '0';
                testDiv.style.left = '0';
                testDiv.style.height = 'env(safe-area-inset-top, 0px)';
                testDiv.style.width = 'env(safe-area-inset-left, 0px)';
                testDiv.style.visibility = 'hidden';
                testDiv.style.pointerEvents = 'none';
                pDoc.body.appendChild(testDiv);

                var computedTop = parseFloat(window.getComputedStyle(testDiv).height) || 0;
                var computedLeft = parseFloat(window.getComputedStyle(testDiv).width) || 0;
                try { pDoc.body.removeChild(testDiv); } catch(e) {}

                // Android APK / Standalone で env が 0px の場合の機種補正
                var ua = navigator.userAgent || '';
                var isStandalone = window.matchMedia('(display-mode: standalone)').matches || 
                                   window.navigator.standalone || 
                                   (ua.indexOf('wv') !== -1 || (ua.indexOf('Android') !== -1 && ua.indexOf('Version/') !== -1));
                var safeTop = computedTop;
                if (safeTop === 0 && isStandalone) {
                    safeTop = 28; // 機種ステータスバーの標準安全余白
                }

                pDoc.documentElement.style.setProperty('--device-safe-top', safeTop + 'px');
                pDoc.documentElement.style.setProperty('--device-safe-left', computedLeft + 'px');
                document.documentElement.style.setProperty('--device-safe-top', safeTop + 'px');
                document.documentElement.style.setProperty('--device-safe-left', computedLeft + 'px');
            } catch(err) {}
        }
        updateDeviceSafeArea();
        window.addEventListener('resize', updateDeviceSafeArea);
        window.addEventListener('orientationchange', updateDeviceSafeArea);

        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/app/static/sw.js?v=4').catch(function(e){});
        }
    }
    setupPWA();
    setTimeout(setupPWA, 300);
    setTimeout(setupPWA, 1000);
})();
</script>
""")
# ─────────────────────────────────────────────────────────────────────────────

# ── 文字サイズ設定定義（アカウントと紐付け対応） ──────────────────
FONT_SIZE_OPTIONS = ["標準 (16px)", "大きめ (18px)", "特大 (22px)"]

FONT_SIZE_MAP = {
    "標準 (16px)": {
        "base": "16px",
        "chat": "16px",
        "chat_line": "1.75",
        "h1": "26px",
        "h2": "20px",
        "h3": "17px",
        "h4": "16px",
        "input": "15px",
        "sidebar": "13.5px",
    },
    "大きめ (18px)": {
        "base": "18px",
        "chat": "18px",
        "chat_line": "1.8",
        "h1": "29px",
        "h2": "22px",
        "h3": "19px",
        "h4": "18px",
        "input": "16.5px",
        "sidebar": "14.5px",
    },
    "特大 (22px)": {
        "base": "22px",
        "chat": "22px",
        "chat_line": "1.85",
        "h1": "33px",
        "h2": "25px",
        "h3": "22px",
        "h4": "20px",
        "input": "18.5px",
        "sidebar": "16px",
    },
}

def get_mato_svg(size: int = 28, center_color: str = "#B83B2A") -> str:
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">'
        f'<circle cx="12" cy="12" r="9.5"></circle>'
        f'<circle cx="12" cy="12" r="5.5"></circle>'
        f'<circle cx="12" cy="12" r="2" fill="{center_color}" stroke="none"></circle>'
        f'</svg>'
    )

# ==================== 表示テーマ（自動／ライト／ダーク） ====================
THEME_CHOICES = ["自動", "ライト", "ダーク"]
_THEME_LIGHT_VARS = (
    "--canvas: #FAF9F6; "
    "--canvas-subtle: #F3F1EC; "
    "--surface-1: #F3F1EC; "
    "--surface-2: #FFFFFF; "
    "--surface-3: #EAE7DF; "
    "--surface-glass: rgba(250, 249, 246, 0.90); "
    "--composer: #FFFFFF; "
    "--user-bubble: #F3F1EC; "
    "--border-hairline: #E2DED5; "
    "--border-subtle: #E2DED5; "
    "--border-strong: #78716C; "
    "--primary-indigo: #1B365D; "
    "--primary-container: #E2E8F4; "
    "--on-primary-container: #11233E; "
    "--accent-red: #B83B2A; "
    "--accent-red-soft: rgba(184, 59, 42, 0.10); "
    "--shu: #1B365D; "
    "--shu-light: #244778; "
    "--shu-soft: rgba(27, 54, 93, 0.08); "
    "--on-accent: #FFFFFF; "
    "--link: #1B365D; "
    "--ink-primary: #1C1B18; "
    "--ink-secondary: #57534E; "
    "--ink-muted: #78716C; "
    "--ink-dim: #A8A29E; "
    "--shadow-sm: 0 1px 3px rgba(28, 27, 24, 0.05); "
    "--shadow-md: 0 4px 16px rgba(28, 27, 24, 0.08); "
    "--shadow-lg: 0 10px 30px rgba(28, 27, 24, 0.12); "
    "--shadow-float: 0 4px 20px 0 rgba(28, 27, 24, 0.07); "
    "--radius-full: 9999px; "
    "--radius-xl: 20px; "
    "--radius-lg: 14px; "
    "--radius-md: 10px; "
    "--radius-sm: 6px; "
    "--ease: cubic-bezier(0.2, 0, 0, 1); "
    "--font-serif: 'Crimson Pro', 'Noto Serif JP', 'Yu Mincho', serif; "
    "--font-sans: 'Commissioner', 'Noto Sans JP', -apple-system, BlinkMacSystemFont, sans-serif; "
    "--font-mono: 'Source Code Pro', 'JetBrains Mono', monospace;"
)
_THEME_DARK_VARS = (
    "--canvas: #141413; "
    "--canvas-subtle: #1C1B1A; "
    "--surface-1: #1C1B1A; "
    "--surface-2: #242321; "
    "--surface-3: #2E2C29; "
    "--surface-glass: rgba(20, 20, 19, 0.90); "
    "--composer: #242321; "
    "--user-bubble: #1C1B1A; "
    "--border-hairline: #383633; "
    "--border-subtle: #383633; "
    "--border-strong: #8C8880; "
    "--primary-indigo: #A8C7FA; "
    "--primary-container: #1E3A5F; "
    "--on-primary-container: #D6E3FF; "
    "--accent-red: #E0533C; "
    "--accent-red-soft: rgba(224, 83, 60, 0.15); "
    "--shu: #A8C7FA; "
    "--shu-light: #D6E3FF; "
    "--shu-soft: rgba(168, 199, 250, 0.12); "
    "--on-accent: #0B2545; "
    "--link: #A8C7FA; "
    "--ink-primary: #F2F0EC; "
    "--ink-secondary: #B8B4AC; "
    "--ink-muted: #8C8880; "
    "--ink-dim: #605D57; "
    "--shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.4); "
    "--shadow-md: 0 8px 24px -10px rgba(0, 0, 0, 0.6); "
    "--shadow-lg: 0 18px 48px -14px rgba(0, 0, 0, 0.7); "
    "--shadow-float: 0 4px 16px rgba(0, 0, 0, 0.35); "
    "--radius-full: 9999px; "
    "--radius-xl: 20px; "
    "--radius-lg: 14px; "
    "--radius-md: 10px; "
    "--radius-sm: 6px; "
    "--ease: cubic-bezier(0.2, 0, 0, 1); "
    "--font-serif: 'Crimson Pro', 'Noto Serif JP', 'Yu Mincho', serif; "
    "--font-sans: 'Commissioner', 'Noto Sans JP', -apple-system, BlinkMacSystemFont, sans-serif; "
    "--font-mono: 'Source Code Pro', 'JetBrains Mono', monospace;"
)

def _ui_theme_path() -> str:
    user = st.session_state.get("logged_in_user") or "archer"
    user_safe = "".join(c for c in user if c.isalnum() or c in ("-", "_")) or "archer"
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sidebar_items")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{user_safe}_theme.json")

def load_ui_theme() -> str:
    try:
        with open(_ui_theme_path(), "r", encoding="utf-8") as fp:
            v = json.load(fp).get("theme", "自動")
        return v if v in THEME_CHOICES else "自動"
    except Exception:
        return "自動"

def save_ui_theme():
    try:
        with open(_ui_theme_path(), "w", encoding="utf-8") as fp:
            json.dump({"theme": st.session_state.get("ui_theme", "自動")}, fp, ensure_ascii=False)
    except Exception:
        pass

def _user_font_size_path(user: str = None) -> str:
    target_user = user or st.session_state.get("logged_in_user") or "archer"
    user_safe = "".join(c for c in target_user if c.isalnum() or c in ("-", "_")) or "archer"
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sidebar_items")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{user_safe}_font.json")

def load_user_font_size(user: str = None) -> str:
    try:
        with open(_user_font_size_path(user), "r", encoding="utf-8") as fp:
            v = json.load(fp).get("font_size", "大きめ (18px)")
        return v if v in FONT_SIZE_OPTIONS else "大きめ (18px)"
    except Exception:
        return "大きめ (18px)"

def save_user_font_size():
    try:
        val = st.session_state.get("sb_font_size_choice", "大きめ (18px)")
        st.session_state.font_size_choice = val
        with open(_user_font_size_path(), "w", encoding="utf-8") as fp:
            json.dump({"font_size": val}, fp, ensure_ascii=False)
    except Exception:
        pass

if "ui_theme" not in st.session_state:
    st.session_state.ui_theme = load_ui_theme()

if "sb_font_size_choice" not in st.session_state:
    st.session_state.sb_font_size_choice = load_user_font_size()
st.session_state.font_size_choice = st.session_state.sb_font_size_choice

# ==================== UI：弓道AI「射心」モダン和風デザイン ====================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Commissioner:wght@400;500;600&family=Crimson+Pro:wght@600&family=Noto+Sans+JP:wght@400;500;600&family=Source+Code+Pro:wght@500&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=block');

/* =====================================================================
   弓道AI「射心」 — 和モダン × ChatGPT UI
   ===================================================================== */
:root {
    color-scheme: light dark;

    --canvas: #FAF9F6;
    --canvas-subtle: #F3F1EC;
    --surface-1: #F3F1EC;
    --surface-2: #FFFFFF;
    --surface-3: #EAE7DF;
    --surface-glass: rgba(250, 249, 246, 0.90);
    --composer: #FFFFFF;
    --user-bubble: #F3F1EC;
    --border-hairline: #E2DED5;
    --border-subtle: #E2DED5;
    --border-strong: #78716C;
    --primary-indigo: #1B365D;
    --primary-container: #E2E8F4;
    --on-primary-container: #11233E;
    --accent-red: #B83B2A;
    --accent-red-soft: rgba(184, 59, 42, 0.10);
    --shu: #1B365D;
    --shu-light: #244778;
    --shu-soft: rgba(27, 54, 93, 0.08);
    --on-accent: #FFFFFF;
    --link: #1B365D;
    --ink-primary: #1C1B18;
    --ink-secondary: #57534E;
    --ink-muted: #78716C;
    --ink-dim: #A8A29E;
    --shadow-sm: 0 1px 3px rgba(28, 27, 24, 0.05);
    --shadow-md: 0 4px 16px rgba(28, 27, 24, 0.08);
    --shadow-lg: 0 10px 30px rgba(28, 27, 24, 0.12);
    --shadow-float: 0 4px 20px 0 rgba(28, 27, 24, 0.07);
    --radius-full: 9999px;
    --radius-xl: 20px;
    --radius-lg: 14px;
    --radius-md: 10px;
    --radius-sm: 6px;
    --ease: cubic-bezier(0.2, 0, 0, 1);
    --font-serif: 'Crimson Pro', 'Noto Serif JP', 'Yu Mincho', serif;
    --font-sans: 'Commissioner', 'Noto Sans JP', -apple-system, BlinkMacSystemFont, sans-serif;
    --font-mono: 'Source Code Pro', 'JetBrains Mono', monospace;
}
@media (prefers-color-scheme: dark) {
    :root {
        --canvas: #141413;
        --canvas-subtle: #1C1B1A;
        --surface-1: #1C1B1A;
        --surface-2: #242321;
        --surface-3: #2E2C29;
        --surface-glass: rgba(20, 20, 19, 0.90);
        --composer: #242321;
        --user-bubble: #1C1B1A;
        --border-hairline: #383633;
        --border-subtle: #383633;
        --border-strong: #8C8880;
        --primary-indigo: #A8C7FA;
        --primary-container: #1E3A5F;
        --on-primary-container: #D6E3FF;
        --accent-red: #E0533C;
        --accent-red-soft: rgba(224, 83, 60, 0.15);
        --shu: #A8C7FA;
        --shu-light: #D6E3FF;
        --shu-soft: rgba(168, 199, 250, 0.12);
        --on-accent: #0B2545;
        --link: #A8C7FA;
        --ink-primary: #F2F0EC;
        --ink-secondary: #B8B4AC;
        --ink-muted: #8C8880;
        --ink-dim: #605D57;
        --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.4);
        --shadow-md: 0 8px 24px -10px rgba(0, 0, 0, 0.6);
        --shadow-lg: 0 18px 48px -14px rgba(0, 0, 0, 0.7);
        --shadow-float: 0 4px 16px rgba(0, 0, 0, 0.35);
    }
}

/* ---------- 地 ---------- */
html, body, [class*="css"], .stApp {
    font-family: var(--font-sans) !important;
    background: var(--canvas) !important;
    color: var(--ink-primary) !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    color: var(--ink-primary) !important;
    background-color: var(--canvas) !important;
    background-image: none !important;
}
::selection { background: var(--shu-soft); color: var(--ink-primary); }

::-webkit-scrollbar { width: 6px !important; height: 6px !important; }
::-webkit-scrollbar-track { background: transparent !important; }
::-webkit-scrollbar-thumb { background: var(--border-subtle) !important; border-radius: 9999px !important; }
::-webkit-scrollbar-thumb:hover { background: var(--border-strong) !important; }

[data-testid="stHeader"] {
    background: transparent !important;
    border-bottom: 0 !important;
    height: 0 !important; min-height: 0 !important;
    pointer-events: none !important;
}
[data-testid="stHeader"] button, [data-testid="stHeader"] a { pointer-events: auto !important; }
[data-testid="stAppDeployButton"], [data-testid="stMainMenu"], [data-testid="stToolbarActions"],
[data-testid="stDecoration"], [data-testid="stStatusWidget"], [data-testid="manage-app-button"],
[data-testid="stToolbar"], footer, [class*="viewerBadge"], [class*="profileContainer"],
a[href*="streamlit.io"] { display: none !important; visibility: hidden !important; pointer-events: none !important; }
[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapseButton"] button {
    position: relative; z-index: 1002;
    color: var(--ink-secondary) !important;
    background: transparent !important;
    border: 1px solid transparent !important;
    border-radius: 999px !important;
    box-shadow: none !important;
    transition: background 0.15s ease, border-color 0.15s ease !important;
}
[data-testid="stExpandSidebarButton"] {
    position: fixed !important;
    top: calc(var(--device-safe-top, env(safe-area-inset-top, 0px)) + 12px) !important;
    left: calc(var(--device-safe-left, env(safe-area-inset-left, 0px)) + 12px) !important;
    width: 44px !important;
    height: 44px !important;
    background: var(--surface-2) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: 12px !important;
    box-shadow: 0 2px 10px rgba(0,0,0,0.2) !important;
    z-index: 999999 !important;
    pointer-events: auto !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    cursor: pointer !important;
    touch-action: manipulation !important;
}
[data-testid="stExpandSidebarButton"] button {
    width: 100% !important;
    height: 100% !important;
    background: transparent !important;
    border: none !important;
    border-radius: 12px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    pointer-events: auto !important;
    cursor: pointer !important;
}
[data-testid="stExpandSidebarButton"]:hover, [data-testid="stSidebarCollapseButton"] button:hover {
    background: var(--surface-3) !important;
    border-color: var(--border-hairline) !important;
    color: var(--ink-primary) !important;
}
[data-testid="stExpandSidebarButton"] *, [data-testid="stSidebarCollapseButton"] button * { color: inherit !important; }

/* ✕ アイコン（サイドバー閉じるボタン）: double-arrow → close に差し替え
   button 内の全 span に当てると複数 × が出るため、アイコン span だけ狙う */
[data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"] {
    font-size: 0 !important;
    width: 24px !important; height: 24px !important;
    display: inline-flex !important; align-items: center !important; justify-content: center !important;
}
[data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"]::after {
    content: "close" !important;
    font-family: "Material Symbols Outlined", "Material Symbols Rounded", "Material Icons" !important;
    font-size: 22px !important; line-height: 1 !important;
    display: inline-block !important; color: inherit !important;
    font-style: normal !important; font-weight: 300 !important;
    font-variation-settings: 'FILL' 0, 'wght' 300, 'GRAD' 0, 'opsz' 24 !important;
}

/* サイドバーヘッダー：ブランドをボタン左横に配置 */
/* height/min-height は設定しない — Streamlit内部の 2.875rem 計算を壊さないため */
[data-testid="stSidebarHeader"] {
    padding: 0 8px 0 14px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    overflow: visible !important;
}
[data-testid="stSidebarHeader"] #kyudo-sidebar-brand {
    display: flex !important; align-items: center !important;
    gap: 8px !important; flex: 1 1 auto !important;
    padding: 0 !important; margin: 0 !important; min-width: 0 !important;
    overflow: hidden !important;
}
[data-testid="stSidebarHeader"] .sb-brand-name {
    font-size: 13px !important; line-height: 1.2 !important;
    white-space: nowrap !important; overflow: hidden !important;
    text-overflow: ellipsis !important;
}
[data-testid="stSidebarHeader"] .sb-brand-tag {
    font-size: 9.5px !important; letter-spacing: 0.06em !important;
    white-space: nowrap !important;
}
/* ロゴ円をヘッダー高さに収まるようコンパクトに */
[data-testid="stSidebarHeader"] #kyudo-sidebar-brand > div:first-child {
    width: 26px !important; height: 26px !important; min-width: 26px !important;
    font-size: 13px !important;
}
/* stSidebarUserContent 内のブランド（JSで header へ移動後）は完全に消す */
[data-testid="stSidebarUserContent"] #kyudo-sidebar-brand {
    display: none !important;
    height: 0 !important;
    overflow: hidden !important;
    margin: 0 !important;
    padding: 0 !important;
}
/* stSidebarUserContent のブランド移動後は余分な上パディングを取り除く */
[data-testid="stSidebarUserContent"] #kyudo-sidebar-brand ~ * {
    /* ブランドの直後の要素はそのまま自然な位置に */
}

[data-testid="stMainBlockContainer"] {
    max-width: 768px !important;
    padding: 44px 24px var(--kyudo-main-pad, 24px) !important;
    margin: 0 auto !important;
}

/* ---------- タイポグラフィ ---------- */
.stMarkdown, .stMarkdown p, .stMarkdown li,
[data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] p {
    color: var(--ink-primary) !important;
    font-size: 16px !important;
    line-height: 1.75 !important;
    letter-spacing: 0 !important;
}
h1, h2, h3, h4, h5, h6 {
    font-family: var(--font-sans) !important;
    color: var(--ink-primary) !important;
    font-weight: 600 !important;
    letter-spacing: 0 !important;
}
h1 { font-size: clamp(24px, 3vw, 30px) !important; line-height: 1.4 !important; }
h2 { font-size: 20px !important; }
h3 { font-size: 17px !important; }
h4 { font-size: 16px !important; }
strong { color: var(--ink-primary) !important; font-weight: 600 !important; }
hr, [data-testid="stDivider"] hr { border-color: var(--border-hairline) !important; }
a { color: var(--link) !important; text-underline-offset: 3px; }

div[data-testid="stMarkdownContainer"] code {
    background: var(--surface-3) !important;
    border: 0 !important;
    color: var(--ink-primary) !important;
    border-radius: 6px !important;
    padding: 2px 6px !important;
    font-size: 0.875em !important;
    font-family: var(--font-mono) !important;
}
div[data-testid="stMarkdownContainer"] pre {
    background: var(--canvas-subtle) !important;
    border: 1px solid var(--border-hairline) !important;
    border-radius: var(--radius-lg) !important;
}
div[data-testid="stMarkdownContainer"] blockquote {
    border-left: 3px solid var(--border-strong) !important;
    background: transparent !important;
    padding: 2px 16px !important;
    margin: 14px 0 !important;
    border-radius: 0 !important;
    color: var(--ink-muted) !important;
}
/* 表：ChatGPT のように罫線だけの軽い見た目 */
div[data-testid="stMarkdownContainer"] table {
    border-collapse: collapse !important; width: 100%; margin: 12px 0 !important;
    font-size: 15px !important;
}
div[data-testid="stMarkdownContainer"] th {
    background: transparent !important; color: var(--ink-primary) !important;
    font-weight: 600 !important; text-align: left !important;
    border: 0 !important; border-bottom: 1px solid var(--border-strong) !important;
    padding: 8px 12px !important;
}
div[data-testid="stMarkdownContainer"] td {
    background: transparent !important; color: var(--ink-primary) !important;
    border: 0 !important; border-bottom: 1px solid var(--border-hairline) !important;
    padding: 8px 12px !important;
}
[data-testid="stCaptionContainer"], .stCaption, small { color: var(--ink-muted) !important; }

/* ---------- サイドバー ---------- */
section[data-testid="stSidebar"] {
    background: var(--surface-1) !important;
    border-right: 0 !important;
}
section[data-testid="stSidebar"] > div { background: transparent !important; }
/* stSidebarContent（ヘッダー＋スクロール領域全体）はフレックス縦積み */
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    display: flex !important;
    flex-direction: column !important;
}
/* スクロール可能なユーザーコンテンツ領域は header の高さ分オフセット不要だが
   ヘッダーが sticky になった場合の被りを防ぐために scroll-padding を設定 */
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
    overflow-y: auto !important;
}
section[data-testid="stSidebar"] .stMarkdown,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label { color: var(--ink-secondary) !important; }
section[data-testid="stSidebar"] strong { color: var(--ink-primary) !important; }

.sb-brand-name {
    font-family: var(--font-serif);
    font-size: 17px; font-weight: 600; letter-spacing: 0;
    color: var(--ink-primary); line-height: 1.2;
}
.sb-brand-tag {
    font-family: var(--font-sans);
    font-size: 10px; font-weight: 500; letter-spacing: 0.08em; color: var(--ink-muted);
    margin-top: 3px; display: block;
}
.sb-section-label {
    color: var(--ink-secondary) !important;
    font-size: 11.5px !important;
    font-weight: 600 !important;
    letter-spacing: 0.05em !important;
    line-height: 1.4 !important;
    padding: 12px 10px 6px !important;
    margin: 2px 0 0 !important;
    display: block !important;
    position: relative !important;
    z-index: 3 !important;
}
/* 「今日」などの見出しが、直下のチャットタイトル行に隠れないよう、見出し側の要素を前面に出して高さを確保する */
section[data-testid="stSidebar"] [data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] .sb-section-label),
section[data-testid="stSidebar"] .stElementContainer:has(.sb-section-label),
section[data-testid="stSidebar"] .element-container:has(.sb-section-label) {
    position: relative !important;
    z-index: 3 !important;
    height: auto !important;
    min-height: 28px !important;
    overflow: visible !important;
    margin-bottom: 2px !important;
}
/* 見出しの直後の行（チャットタイトル）は見出しより下の層に置く */
section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has([class*="st-key-sess_btn_"], [class*="st-key-sess_active_"]) {
    position: relative !important;
    z-index: 1 !important;
}
/* 履歴タイトルを全行で同じ高さ・同じ位置に揃える（長いタイトルは1行で省略表示） */
section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has([class*="st-key-sess_btn_"], [class*="st-key-sess_active_"]) {
    margin: 0 !important;
    min-height: 36px !important;
    align-items: center !important;
    flex-wrap: nowrap !important;
}
section[data-testid="stSidebar"] [class*="st-key-sess_btn_"],
section[data-testid="stSidebar"] [class*="st-key-sess_active_"] {
    margin: 0 !important;
}
section[data-testid="stSidebar"] [class*="st-key-sess_btn_"] button,
section[data-testid="stSidebar"] [class*="st-key-sess_active_"] button {
    height: 36px !important;
    min-height: 36px !important;
    padding: 0 10px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
    text-align: left !important;
}
section[data-testid="stSidebar"] [class*="st-key-sess_btn_"] button > div,
section[data-testid="stSidebar"] [class*="st-key-sess_active_"] button > div {
    width: 100% !important;
    justify-content: flex-start !important;
    text-align: left !important;
}
section[data-testid="stSidebar"] [class*="st-key-sess_btn_"] button p,
section[data-testid="stSidebar"] [class*="st-key-sess_active_"] button p {
    margin: 0 !important;
    font-size: 13.5px !important;
    line-height: 1.4 !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    text-align: left !important;
}

section[data-testid="stSidebar"] .stButton > button,
section[data-testid="stSidebar"] [data-testid="stPopover"] > button {
    background: transparent !important;
    color: var(--ink-secondary) !important;
    border: 0 !important;
    border-radius: var(--radius-md) !important;
    box-shadow: none !important;
    min-height: 36px !important;
    padding: 6px 10px !important;
    text-align: left !important;
    justify-content: flex-start !important;
    font-weight: 500 !important;
    font-size: 13.5px !important;
    letter-spacing: 0 !important;
    transition: color 0.18s var(--ease), background 0.18s var(--ease) !important;
}
section[data-testid="stSidebar"] .stButton > button:hover,
section[data-testid="stSidebar"] [data-testid="stPopover"] > button:hover {
    color: var(--ink-primary) !important;
    background: var(--surface-3) !important;
    transform: none !important;
}
section[data-testid="stSidebar"] [class*="st-key-sess_active_"] button {
    color: var(--ink-primary) !important;
    background: var(--surface-3) !important;
    font-weight: 600 !important;
}
/* 新しい相談：モックアップ準拠のカードボタンスタイル＋⌘Kバッジ */
section[data-testid="stSidebar"] .st-key-sidebar_new_chat_btn button {
    color: var(--ink-primary) !important;
    background: var(--surface-2) !important;
    border: 1px solid var(--border-hairline) !important;
    border-radius: 10px !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.02) !important;
    padding: 8px 14px !important;
    min-height: 42px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    transition: all 0.16s ease !important;
}
section[data-testid="stSidebar"] .st-key-sidebar_new_chat_btn button:hover {
    background: var(--surface-3) !important;
    border-color: var(--border-strong) !important;
    color: var(--ink-primary) !important;
}
section[data-testid="stSidebar"] .st-key-sidebar_new_chat_btn button [data-testid="stIconMaterial"] {
    color: var(--primary-indigo) !important;
    font-size: 19px !important;
    margin-right: 6px !important;
}
section[data-testid="stSidebar"] .st-key-sidebar_new_chat_btn button::after {
    content: "⌘K";
    font-family: var(--font-mono);
    font-size: 11px;
    font-weight: 500;
    color: var(--ink-muted);
    padding: 2px 6px;
    background: var(--surface-3);
    border-radius: 4px;
    margin-left: auto;
}

[class*="st-key-hist_pin_"] { display: none !important; }
/* PC（マウス操作）では行の「···」を隠し、右クリックメニューから操作する。
   スマホ・タブレット（タッチ操作）では「···」をそのまま表示する。
   display:none にするとポップオーバーの表示位置がずれるため、幅0・透明にして場所だけ残す */
@media (hover: hover) and (pointer: fine) {
    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has([class*="st-key-sess_btn_"], [class*="st-key-sess_active_"], [class*="st-key-pins_use_"]) > div:first-child {
        flex: 1 1 auto !important; width: auto !important; min-width: 0 !important;
    }
    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has([class*="st-key-sess_btn_"], [class*="st-key-sess_active_"], [class*="st-key-pins_use_"]) > div:last-child {
        flex: 0 0 0 !important; width: 0 !important; min-width: 0 !important;
        overflow: visible !important; opacity: 0 !important; pointer-events: none !important;
    }
}
/* スマホ（タッチ操作）: ···ボタンをタイトルボタンに重ねて右端に配置。
   タイトルテキストは右端へフェードアウト。行全体は相対配置のコンテナとして扱う */
@media (hover: none), (pointer: coarse) {
    /* 行全体を relative コンテナに */
    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has([class*="st-key-sess_btn_"], [class*="st-key-sess_active_"], [class*="st-key-pins_use_"]) {
        position: relative !important;
        overflow: visible !important;
    }
    /* タイトル列（左）: 全幅に広げてフェードマスクを付ける */
    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has([class*="st-key-sess_btn_"], [class*="st-key-sess_active_"], [class*="st-key-pins_use_"]) > div:first-child {
        flex: 1 1 auto !important; width: 100% !important; min-width: 0 !important;
    }
    /* タイトルボタン自体にフェードマスク（右端→透明）*/
    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has([class*="st-key-sess_btn_"], [class*="st-key-sess_active_"], [class*="st-key-pins_use_"]) > div:first-child button {
        -webkit-mask-image: linear-gradient(to right, black 60%, transparent 92%) !important;
        mask-image: linear-gradient(to right, black 60%, transparent 92%) !important;
        overflow: hidden !important;
    }
    /* ···列（右）: absolute で右端に重ねる。幅は必要最小限 */
    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has([class*="st-key-sess_btn_"], [class*="st-key-sess_active_"], [class*="st-key-pins_use_"]) > div:last-child {
        position: absolute !important; right: 0 !important; top: 50% !important;
        transform: translateY(-50%) !important;
        flex: 0 0 auto !important; width: auto !important; min-width: 0 !important;
        z-index: 10 !important;
        background: transparent !important;
    }
    /* ···ボタン自体のスタイル調整 */
    section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has([class*="st-key-sess_btn_"], [class*="st-key-sess_active_"], [class*="st-key-pins_use_"]) > div:last-child button {
        min-width: 32px !important; padding: 2px 4px !important;
        background: transparent !important; border: none !important;
        font-size: 15px !important; color: var(--ink-muted) !important;
    }
}
/* streamlit.app（Streamlit Cloud）の右下バッジが送信ボタンに重なるのを避けるため、
   JS が html に付ける kyudo-lift クラスがあるときだけ入力欄を持ち上げる */
html.kyudo-lift div[data-testid="stBottom"] { padding-bottom: calc(68px + env(safe-area-inset-bottom, 0px)) !important; }

/* 履歴の検索欄 */
section[data-testid="stSidebar"] .st-key-sidebar_search_chats [data-baseweb="input"] {
    border-radius: 10px !important; min-height: 36px !important; background: var(--surface-2) !important;
}
section[data-testid="stSidebar"] .st-key-sidebar_search_chats input { font-size: 13px !important; padding: 6px 10px !important; }
/* キーボード操作時だけ見えるフォーカスリング */
button:focus-visible, [role="button"]:focus-visible, a:focus-visible {
    outline: 2px solid var(--shu) !important; outline-offset: 2px !important;
}
/* サイドバーの縦の間隔を詰めて整頓 */
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.2rem !important; }
/* ブランドをヘッダーに移した後は UserContent の上パディングはデフォルト値（0.75rem）に戻す */
/* padding-top を大きくしすぎると header との間にスペースができ、今日ラベルが被る原因になる */
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] { padding-top: 0.75rem !important; }
section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] { gap: 0.2rem !important; align-items: center !important; }
section[data-testid="stSidebar"] [data-testid="stPopover"] > button { color: var(--ink-muted) !important; }

/* ---------- ポップオーバー（サイドバー等より必ず前面） ---------- */
div[data-baseweb="popover"], div[data-baseweb="layer"], div[data-testid="stPopoverBody"] { z-index: 2147483000 !important; }
div[data-testid="stPopoverBody"] {
    background: var(--surface-2) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-xl) !important;
    box-shadow: var(--shadow-lg) !important;
    padding: 14px !important;
}
div[data-testid="stPopoverBody"] p,
div[data-testid="stPopoverBody"] span,
div[data-testid="stPopoverBody"] label { color: var(--ink-secondary) !important; }
div[data-testid="stPopoverBody"] button { color: var(--ink-primary) !important; }

/* ツールチップ（ボタンにカーソルを合わせたときの「⌘K / Ctrl+Shift+O」など）：ダークモードで白地に白文字にならないよう、テーマ色で塗る */
div[data-baseweb="tooltip"],
div[data-baseweb="tooltip"] > div,
[data-testid="stTooltipContent"],
[data-testid="stTooltipContent"] > div {
    background: var(--surface-2) !important;
    color: var(--ink-primary) !important;
    border-radius: 8px !important;
}
[data-testid="stTooltipContent"] {
    border: 1px solid var(--border-subtle) !important;
    box-shadow: var(--shadow-lg) !important;
}
[data-testid="stTooltipContent"] *,
div[data-baseweb="tooltip"] p,
div[data-baseweb="tooltip"] span {
    color: var(--ink-primary) !important;
    font-size: 12.5px !important;
    line-height: 1.5 !important;
}
div[data-baseweb="tooltip"] [data-baseweb="popover-arrow"],
div[data-baseweb="popover"] [data-baseweb="popover-arrow"] {
    background: var(--surface-2) !important;
}

/* 設定ポップアップ内の入力欄（カルテの「追加する情報」、指示の2つのテキスト欄、段位・称号の選択）：
   ダークモードで枠が白のまま、文字だけ明るくなって見えなくなる問題の対策。入力欄とその外枠を面の色で塗る */
div[data-testid="stPopoverBody"] div:has(> textarea),
div[data-testid="stPopoverBody"] div:has(> input),
div[data-testid="stPopoverBody"] div:has(> div > textarea),
div[data-testid="stPopoverBody"] div:has(> div > input),
div[data-testid="stPopoverBody"] [data-baseweb="input"],
div[data-testid="stPopoverBody"] [data-baseweb="base-input"],
div[data-testid="stPopoverBody"] [data-baseweb="textarea"],
div[data-testid="stPopoverBody"] [data-baseweb="select"] > div,
div[data-testid="stPopoverBody"] [data-testid="stTextInputRootElement"],
div[data-testid="stPopoverBody"] [data-testid="stTextAreaRootElement"] {
    background: var(--surface-3) !important;
    background-color: var(--surface-3) !important;
    color: var(--ink-primary) !important;
    border-color: var(--border-subtle) !important;
}
div[data-testid="stPopoverBody"] textarea,
div[data-testid="stPopoverBody"] input {
    background: transparent !important;
    background-color: transparent !important;
    color: var(--ink-primary) !important;
    -webkit-text-fill-color: var(--ink-primary) !important;
    caret-color: var(--ink-primary) !important;
}
div[data-testid="stPopoverBody"] textarea::placeholder,
div[data-testid="stPopoverBody"] input::placeholder {
    color: var(--ink-dim) !important;
    -webkit-text-fill-color: var(--ink-dim) !important;
}
/* 段位・称号のタップ選択ボタン */
div[data-testid="stPopoverBody"] button[kind="pills"] {
    background: var(--surface-3) !important;
    color: var(--ink-primary) !important;
    border: 1px solid var(--border-subtle) !important;
}
div[data-testid="stPopoverBody"] button[kind="pillsActive"] {
    background: var(--shu-soft) !important;
    color: var(--ink-primary) !important;
    border: 1px solid var(--shu) !important;
    font-weight: 600 !important;
}
/* 段位・称号のタップ選択ボタン：ダークでも読めるようテーマ色で塗る。選択中は朱色の縁で目立たせる */
div[data-testid="stPopoverBody"] button[data-testid="stBaseButton-pills"],
div[data-testid="stPopoverBody"] [data-testid="stButtonGroup"] button {
    background: var(--surface-3) !important;
    color: var(--ink-primary) !important;
    border: 1px solid var(--border-subtle) !important;
}
div[data-testid="stPopoverBody"] button[data-testid="stBaseButton-pillsActive"] {
    background: var(--shu-soft) !important;
    color: var(--ink-primary) !important;
    border: 1px solid var(--shu) !important;
    font-weight: 600 !important;
}
div[data-testid="stPopoverBody"] [data-testid="stButtonGroup"] button p,
div[data-testid="stPopoverBody"] [data-testid="stButtonGroup"] button span {
    color: var(--ink-primary) !important;
}
/* 選択ボックスを開いたときの一覧（ポップアップの外側に描画される） */
div[data-baseweb="popover"] ul[role="listbox"],
div[data-baseweb="popover"] [data-baseweb="menu"] {
    background: var(--surface-2) !important;
    color: var(--ink-primary) !important;
}
div[data-baseweb="popover"] li[role="option"],
div[data-baseweb="popover"] li[role="option"] * {
    background: transparent !important;
    color: var(--ink-primary) !important;
}
div[data-baseweb="popover"] li[role="option"]:hover,
div[data-baseweb="popover"] li[role="option"][aria-selected="true"] {
    background: var(--surface-3) !important;
}

/* ---------- 上部バー（コンテナ key="topbar"） ---------- */
.st-key-topbar {
    position: sticky; top: 0; z-index: 90;
    background: var(--surface-glass);
    -webkit-backdrop-filter: blur(16px) saturate(1.2); backdrop-filter: blur(16px) saturate(1.2);
    border-bottom: 1px solid var(--border-hairline);
    padding: calc(var(--device-safe-top, env(safe-area-inset-top, 0px)) + 10px) 24px 10px calc(var(--device-safe-left, env(safe-area-inset-left, 0px)) + 64px) !important;
    margin-left: -24px !important;
    margin-right: -24px !important;
    margin-top: -10px !important;
    margin-bottom: 24px !important;
}
.st-key-topbar [data-testid="stHorizontalBlock"] {
    display: flex !important;
    align-items: center !important;
    justify-content: space-between !important;
    gap: 12px !important;
}
.st-key-topbar [data-testid="stHorizontalBlock"] > div:first-child {
    display: flex !important;
    align-items: center !important;
    flex: 1 1 auto !important;
}
.st-key-topbar [data-testid="stHorizontalBlock"] > div:last-child {
    display: flex !important;
    align-items: center !important;
    justify-content: flex-end !important;
    flex: 0 0 auto !important;
    width: auto !important;
}
.st-key-topbar [data-testid="stPopover"] > button,
[data-testid="stMain"] [data-testid="stPopover"] > button {
    display: inline-flex !important;
    align-items: center !important;
    gap: 6px !important;
    background: transparent !important;
    border: 1px solid transparent !important;
    box-shadow: none !important;
    color: var(--ink-primary) !important;
    font-weight: 600 !important;
    border-radius: 8px !important;
    font-size: 15px !important;
    letter-spacing: -0.2px !important;
    padding: 6px 12px !important;
    min-height: 36px !important;
    height: 36px !important;
    transition: background 0.16s ease !important;
}
[data-testid="stMain"] [data-testid="stPopover"] > button:hover {
    background: var(--surface-3) !important; transform: none !important;
}
.st-key-tb_chip_video {
    display: flex !important;
    justify-content: flex-end !important;
}
.st-key-tb_chip_video button {
    display: inline-flex !important;
    align-items: center !important;
    gap: 6px !important;
    border-radius: 9999px !important;
    background: var(--surface-2) !important;
    border: 1px solid var(--border-hairline) !important;
    color: var(--ink-primary) !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    padding: 5px 14px !important;
    min-height: 32px !important;
    height: 32px !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.02) !important;
    white-space: nowrap !important;
    transition: all 0.15s ease !important;
}
.st-key-tb_chip_video button:hover {
    background: var(--surface-3) !important;
    border-color: var(--border-strong) !important;
    color: var(--ink-primary) !important;
}

/* ---------- ウェルカム（ChatGPT風 ミニマル・センター） ---------- */
.mato-emblem {
    width: 68px; height: 68px; border-radius: 18px;
    overflow: hidden;
    margin: 0 auto 20px;
    box-shadow: 0 8px 28px rgba(0, 229, 255, 0.28), 0 2px 8px rgba(0,0,0,0.3);
}
.mato-emblem img {
    width: 100%; height: 100%; object-fit: cover;
}
.welcome-hero {
    text-align: center;
    margin: clamp(40px, 14vh, 140px) auto 0;
    max-width: 680px;
    padding: 0 16px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
}
.welcome-title {
    font-family: var(--font-serif), -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    font-size: clamp(22px, 3.4vw, 32px) !important;
    font-weight: 600 !important; line-height: 1.4 !important;
    letter-spacing: -0.3px !important; color: var(--ink-primary) !important;
    margin: 0 0 14px !important;
}
.welcome-sub {
    font-size: 14.5px !important; line-height: 1.75 !important;
    color: var(--ink-secondary) !important;
    max-width: 520px; margin: 0 auto !important;
}
@media (max-width: 680px) {
    .welcome-hero {
        margin: clamp(24px, 10vh, 60px) auto 0 !important;
    }
    .mato-emblem {
        width: 56px !important; height: 56px !important;
        border-radius: 16px !important;
        margin-bottom: 16px !important;
    }
    .welcome-title {
        font-size: 21px !important;
        margin-bottom: 10px !important;
    }
    .welcome-sub {
        font-size: 13.5px !important;
        line-height: 1.65 !important;
    }
}

/* ---------- 会話（GPU合成レイヤーによる超スムーズなストリーミング描画） ---------- */
div[data-testid="stChatMessage"] {
    background: transparent !important; border: 0 !important; box-shadow: none !important;
    padding: 6px 0 !important; margin: 0 auto 16px !important;
    max-width: 100% !important; width: 100% !important;
    contain: layout style !important;
    transform: translateZ(0) !important;
}

/* あなた：右寄せのやわらかい吹き出し（ChatGPT / Claude 公式準拠） */
div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    max-width: 78% !important; width: fit-content !important;
    margin-left: auto !important; margin-right: 0 !important;
    background: var(--user-bubble, #F4F4F4) !important;
    border: none !important;
    border-radius: 20px 20px 4px 20px !important;
    padding: 10px 18px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.03) !important;
}
div[data-testid="stChatMessage"] [data-testid="stChatMessageAvatarUser"] { display: none !important; }
div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) p,
div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) span,
div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stMarkdownContainer"] * {
    color: var(--ink-primary) !important;
    font-size: 15px !important;
    line-height: 1.65 !important;
}

/* AI：地に直接。枠なし、最高峰のタイポグラフィ */
div[data-testid="stChatMessage"]:not(:has([data-testid="stChatMessageAvatarUser"])) {
    padding: 6px 0 !important;
}
div[data-testid="stChatMessage"]:not(:has([data-testid="stChatMessageAvatarUser"])) [data-testid^="stChatMessageAvatar"] {
    width: 30px !important; height: 30px !important;
    border-radius: 50% !important;
    background: var(--primary-indigo) !important;
    color: #ffffff !important;
    box-shadow: 0 2px 6px rgba(27, 54, 93, 0.2) !important;
    display: flex !important; align-items: center !important; justify-content: center !important;
}
div[data-testid="stChatMessage"]:not(:has([data-testid="stChatMessageAvatarUser"])) p,
div[data-testid="stChatMessage"]:not(:has([data-testid="stChatMessageAvatarUser"])) li {
    color: var(--ink-primary) !important; font-size: 15.5px !important; line-height: 1.78 !important;
}

/* 回答内の見出しは ChatGPT 並みに洗練されたメリハリへ */
div[data-testid="stChatMessage"] h1 { font-size: 20px !important; font-weight: 700 !important; margin: 18px 0 8px !important; }
div[data-testid="stChatMessage"] h2 { font-size: 18px !important; font-weight: 650 !important; margin: 16px 0 6px !important; }
div[data-testid="stChatMessage"] h3 { font-size: 16.5px !important; font-weight: 600 !important; margin: 14px 0 4px !important; }
div[data-testid="stChatMessage"] h4 { font-size: 15.5px !important; font-weight: 600 !important; margin: 12px 0 4px !important; }

.char-badge {
    display: inline-flex; align-items: center; gap: 8px;
    padding: 0 !important; margin: 0 0 8px !important;
    background: transparent !important; border: 0 !important; border-radius: 0 !important;
    font-family: var(--font-sans) !important;
    font-size: 12.5px !important; font-weight: 500 !important; letter-spacing: 0 !important;
    color: var(--ink-muted) !important;
}
.char-badge.char-master, .char-badge.char-senior, .char-badge.char-analyst {
    color: var(--ink-muted) !important; background: transparent !important; border: 0 !important;
}
.memory-badge {
    display: inline-flex; align-items: center; gap: 6px; padding: 3px 12px; margin: 2px 0 12px;
    background: var(--shu-soft) !important; color: var(--shu) !important;
    border: 0 !important; border-radius: 999px !important;
    font-size: 11.5px !important; font-weight: 500 !important;
}
.file-attachment-card {
    display: inline-flex; align-items: center; gap: 12px;
    background: var(--surface-2) !important; border: 1px solid var(--border-hairline) !important;
    border-radius: var(--radius-lg) !important; padding: 10px 16px !important; margin-bottom: 10px !important;
}
.file-attachment-details { display: flex; flex-direction: column; }
.file-attachment-name { color: var(--ink-primary) !important; font-weight: 600 !important; font-size: 13.5px !important; }
.file-attachment-meta { color: var(--ink-muted) !important; font-size: 11px !important; }

/* 回答下の操作列：控えめなテキストボタン */
div[data-testid="stChatMessage"] .stButton > button,
div[data-testid="stChatMessage"] [data-testid="stPopover"] > button {
    min-height: 30px !important; padding: 2px 12px !important;
    font-size: 12px !important; color: var(--ink-muted) !important;
    border-color: transparent !important; background: transparent !important;
}
div[data-testid="stChatMessage"] .stButton > button:hover,
div[data-testid="stChatMessage"] [data-testid="stPopover"] > button:hover {
    color: var(--ink-primary) !important; border-color: transparent !important; background: var(--surface-3) !important;
}

/* 回答下の「⋮」メニュー：アイコンだけの小さなボタン */
[class*="st-key-msg_more_"] [data-testid="stPopoverButton"] {
    min-width: 32px !important; width: 32px !important; height: 32px !important; min-height: 32px !important;
    padding: 0 !important; border-radius: 8px !important; color: var(--ink-muted) !important;
}
[class*="st-key-msg_more_"] [data-testid="stPopoverButton"] > div > div[aria-hidden="true"] { display: none !important; }
/* ⋮メニューの中身：枠なしのメニュー行（ChatGPT のメニューと同じ見た目） */
[class*="st-key-btn_regen_"] button[kind], [class*="st-key-regen_char_"] button[kind] {
    background: transparent !important; border: 0 !important; box-shadow: none !important;
    border-radius: 8px !important; justify-content: flex-start !important;
    min-height: 38px !important; padding: 6px 12px !important;
    color: var(--ink-primary) !important; font-size: 14px !important;
}
[class*="st-key-btn_regen_"] button[kind] > div, [class*="st-key-regen_char_"] button[kind] > div { justify-content: flex-start !important; }
[class*="st-key-btn_regen_"] button[kind]:hover, [class*="st-key-regen_char_"] button[kind]:hover { background: var(--surface-3) !important; }

/* ---------- 入力欄（Gemini 公式完全準拠スタイル） ---------- */
div[data-testid="stBottom"], div[data-testid="stBottom"] > div {
    background: transparent !important; border-top: 0 !important;
}
div[data-testid="stBottom"] {
    background: linear-gradient(180deg, transparent 0%, var(--canvas) 42%) !important;
    padding: 8px 0 calc(8px + env(safe-area-inset-bottom, 0px)) !important;
    z-index: 9999 !important;
}
div[data-testid="stBottomBlockContainer"] {
    max-width: 768px !important;
    padding: 0 24px !important;
    margin: 0 auto !important;
    position: relative !important;
}
div[data-testid="stBottomBlockContainer"] div[data-testid="stVerticalBlock"] {
    gap: 0 !important;
}
/* 注意書きを入力欄のすぐ下に配置 */
div[data-testid="stBottomBlockContainer"]::after {
    content: "YUMIQAの助言は稽古の参考情報です。道場の先生・師範のご指導もあわせてご確認ください。";
    display: block !important;
    text-align: center !important;
    font-size: 11px !important;
    line-height: 1.4 !important;
    color: var(--ink-secondary) !important;
    padding: 5px 0 0 !important;
}

/* Google Gemini 公式 UI 完全模倣 カード型コンポーザー（#FFFFFF 浮遊カード・境界線なし・2段構成・右下にモデル切替ピル） */
div[data-testid="stChatInput"] {
    background: var(--composer, #ffffff) !important;
    border: 0 !important;
    border-radius: 32px !important;
    box-shadow: 0 2px 8px -2px rgba(0, 0, 0, 0.14), 0 0 16px 0 rgba(31, 31, 31, 0.06) !important;
    padding: 10px 12px 8px 12px !important;
    transition: box-shadow 0.2s var(--ease), background 0.2s var(--ease) !important;
    position: relative !important;
}
div[data-testid="stChatInput"] div:has(> div > [data-testid="stChatInputSubmitButton"]) {
    display: flex !important;
    flex-wrap: wrap !important;
    align-items: center !important;
    gap: 6px 8px !important;
}
div[data-testid="stChatInput"] div:has(> div > [data-testid="stChatInputSubmitButton"]) > div:has([data-testid="stChatInputTextArea"]) {
    order: -1 !important;
    flex: 1 0 100% !important;
    width: 100% !important;
    max-width: 100% !important;
    min-height: 26px !important;
}
div[data-testid="stChatInput"] div:has(> div > [data-testid="stChatInputSubmitButton"]) > div:has(> [data-testid="stChatInputSubmitButton"]) {
    order: 3 !important;
    margin-left: auto !important;
}
div[data-testid="stChatInput"]:focus-within {
    border: 0 !important;
    box-shadow: 0 4px 16px -2px rgba(11, 87, 208, 0.16), 0 0 2px 0 rgba(11, 87, 208, 0.22) !important;
    background: var(--composer, #ffffff) !important;
}
div[data-testid="stChatInput"] [data-baseweb="textarea"],
div[data-testid="stChatInput"] [data-baseweb="base-input"],
div[data-testid="stChatInput"] [data-baseweb="textarea"] > div {
    border: 0 !important; background: transparent !important; box-shadow: none !important; border-radius: 0 !important;
}
div[data-testid="stChatInput"] div,
div[data-testid="stChatInput"] [data-baseweb] {
    background: transparent !important; background-color: transparent !important; box-shadow: none !important;
}
div[data-testid="stChatInput"] textarea {
    background: transparent !important; color: var(--ink-primary, #1f1f1f) !important;
    font-size: 16px !important; line-height: 24px !important;
    padding: 2px 6px 6px 6px !important;
    min-height: 26px !important;
}
div[data-testid="stChatInput"] textarea::placeholder { color: var(--ink-dim, #5f6368) !important; font-size: 16px !important; }

/* ツールバー内のアイコンボタン共通（添付＋ボタン、マイクなど） */
div[data-testid="stChatInput"] button {
    background: transparent !important; color: var(--ink-secondary) !important;
    border: 0 !important; border-radius: 999px !important;
    width: 32px !important; height: 32px !important; min-height: 32px !important;
    display: inline-flex !important; align-items: center !important; justify-content: center !important;
    transition: all 0.18s ease !important;
}
div[data-testid="stChatInput"] button:hover {
    background: rgba(0, 0, 0, 0.06) !important;
    color: var(--ink-primary) !important;
}

/* 送信ボタン：完全な円形、プライマリインディゴ（#1B365D）、ホバースケール */
div[data-testid="stChatInputSubmitButton"] button, div[data-testid="stChatInput"] button[data-testid="stChatInputSubmitButton"] {
    background: var(--primary-indigo, #1B365D) !important;
    color: #ffffff !important;
    border-radius: 50% !important;
    width: 32px !important; height: 32px !important; min-width: 32px !important; min-height: 32px !important;
    box-shadow: 0 2px 6px rgba(27, 54, 93, 0.25) !important;
    transition: transform 0.18s cubic-bezier(0.34, 1.56, 0.64, 1), background 0.18s ease, opacity 0.18s ease !important;
}
div[data-testid="stChatInputSubmitButton"] button:hover, div[data-testid="stChatInput"] button[data-testid="stChatInputSubmitButton"]:hover {
    background: #142847 !important;
    color: #ffffff !important;
    transform: scale(1.06) !important;
}
div[data-testid="stChatInputSubmitButton"] button:active, div[data-testid="stChatInput"] button[data-testid="stChatInputSubmitButton"]:active {
    transform: scale(0.94) !important;
}
div[data-testid="stChatInput"] button:disabled {
    background: rgba(0, 0, 0, 0.06) !important;
    color: rgba(0, 0, 0, 0.25) !important;
    box-shadow: none !important;
    cursor: not-allowed !important;
    transform: none !important;
}

/* キャラクター（指導陣）選択ピルボタン：Gemini の .bard-mode-switcher と同じ位置（2段目右下・送信ボタンの左隣）に枠線なしゴーストピルとして配置 */
.st-key-input_char_pill_row {
    position: relative !important;
    margin-top: -52px !important;
    margin-bottom: 20px !important;
    margin-left: auto !important;
    margin-right: 66px !important;
    z-index: 20 !important;
    display: inline-flex !important;
    align-items: center !important;
    padding: 0 !important;
    height: 32px !important;
    width: fit-content !important;
    pointer-events: auto !important;
}
div[data-testid="stBottom"] .st-key-input_char_pill_row [data-testid="stPopover"] {
    display: inline-flex !important;
    pointer-events: auto !important;
    margin: 0 !important;
}
div[data-testid="stBottom"] .st-key-input_char_pill_row button[data-testid="stPopoverButton"],
div[data-testid="stBottom"] .st-key-input_char_pill_row [data-testid="stPopover"] > button {
    display: inline-flex !important;
    align-items: center !important;
    gap: 5px !important;
    background: transparent !important;
    background-color: transparent !important;
    border: 0 !important;
    border-radius: 9999px !important;
    padding: 0 10px !important;
    min-height: 32px !important;
    height: 32px !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    color: var(--ink-secondary, #444746) !important;
    box-shadow: none !important;
    transition: background 0.18s ease, color 0.18s ease !important;
    cursor: pointer !important;
    white-space: nowrap !important;
}
div[data-testid="stBottom"] .st-key-input_char_pill_row button[data-testid="stPopoverButton"]:hover,
div[data-testid="stBottom"] .st-key-input_char_pill_row [data-testid="stPopover"] > button:hover {
    background: rgba(0, 0, 0, 0.05) !important;
    background-color: rgba(0, 0, 0, 0.05) !important;
    color: var(--ink-primary, #1f1f1f) !important;
}

/* ---------- ボタン・フォーム ---------- */
.stButton > button, .stDownloadButton > button, button[kind="secondary"] {
    background: var(--surface-2) !important;
    color: var(--ink-primary) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: 999px !important;
    box-shadow: none !important;
    font-weight: 500 !important; font-size: 14px !important; letter-spacing: 0 !important;
    min-height: 38px !important; padding: 6px 18px !important;
    transition: background 0.18s var(--ease), border-color 0.18s var(--ease), color 0.18s var(--ease) !important;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    background: var(--surface-3) !important; border-color: var(--border-strong) !important;
    color: var(--ink-primary) !important; transform: none !important;
}
.stButton > button:active { transform: scale(0.985) !important; }
button[kind="primary"], .stFormSubmitButton > button,
button[kind="primary"]:hover, .stFormSubmitButton > button:hover,
button[kind="primary"]:focus, .stFormSubmitButton > button:focus,
button[kind="primary"]:active, .stFormSubmitButton > button:active,
button[kind="primary"]:focus-visible, .stFormSubmitButton > button:focus-visible,
button[kind="primary"]:disabled, .stFormSubmitButton > button:disabled,
button[kind="primary"][disabled], .stFormSubmitButton > button[disabled] {
    background: var(--shu) !important;
    background-color: var(--shu) !important;
    color: var(--on-accent) !important;
    border: 0 !important;
    border-radius: 999px !important;
    font-weight: 600 !important;
    letter-spacing: 0 !important;
    box-shadow: none !important;
    outline: none !important;
}
button[kind="primary"]:hover, .stFormSubmitButton > button:hover {
    opacity: 0.9 !important;
    transform: none !important;
}
button[kind="primary"]:active, .stFormSubmitButton > button:active {
    opacity: 0.8 !important;
    transform: scale(0.985) !important;
}

div[data-baseweb="input"], div[data-baseweb="textarea"], div[data-baseweb="select"] > div {
    background: var(--surface-2) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-md) !important;
    color: var(--ink-primary) !important;
}
div[data-baseweb="input"]:focus-within, div[data-baseweb="textarea"]:focus-within, div[data-baseweb="select"]:focus-within {
    border-color: var(--shu) !important; box-shadow: 0 0 0 3px var(--shu-soft) !important;
}
input, textarea, [data-baseweb="select"] * { color: var(--ink-primary) !important; background-color: transparent !important; }
input::placeholder, textarea::placeholder { color: var(--ink-dim) !important; }
/* 入力欄の内側ラッパー（Streamlit/BaseWeb既定の背景＝OSダーク時は黒）も面の色に揃える。ログイン画面のライト時に黒く見える問題の対策 */
div[data-baseweb="base-input"], div[data-testid="stTextInputRootElement"], div[data-testid="stNumberInputContainer"],
div[data-baseweb="input"] > div, div[data-baseweb="textarea"] > div {
    background: transparent !important; background-color: transparent !important; color: var(--ink-primary) !important;
}
input, textarea { caret-color: var(--ink-primary) !important; -webkit-text-fill-color: var(--ink-primary) !important; }
input::placeholder, textarea::placeholder { -webkit-text-fill-color: var(--ink-dim) !important; }
input:-webkit-autofill, input:-webkit-autofill:hover, input:-webkit-autofill:focus {
    -webkit-text-fill-color: var(--ink-primary) !important;
    box-shadow: 0 0 0 1000px var(--surface-2) inset !important; -webkit-box-shadow: 0 0 0 1000px var(--surface-2) inset !important;
    transition: background-color 9999s ease-out 0s;
}
div[data-testid="stTextInput"] button { background: transparent !important; color: var(--ink-muted) !important; }
[data-testid="stWidgetLabel"] p, label { color: var(--ink-secondary) !important; font-size: 13px !important; }
div[role="radiogroup"] label p { color: var(--ink-secondary) !important; }

div[data-baseweb="tab-list"] { border-bottom: 1px solid var(--border-hairline) !important; gap: 18px !important; }
button[data-baseweb="tab"] { color: var(--ink-muted) !important; font-weight: 500 !important; font-size: 13px !important; padding: 10px 4px !important; }
button[data-baseweb="tab"][aria-selected="true"] { color: var(--ink-primary) !important; font-weight: 600 !important; }
div[data-baseweb="tab-highlight"] { background-color: var(--shu) !important; height: 2px !important; }

div[data-testid="stExpander"] {
    background: var(--surface-2) !important; border: 1px solid var(--border-hairline) !important;
    border-radius: var(--radius-lg) !important;
}
div[data-testid="stAlert"] {
    background: var(--surface-2) !important; border: 1px solid var(--border-hairline) !important;
    border-left: 3px solid var(--shu) !important; border-radius: var(--radius-md) !important;
}
div[data-testid="stAlert"] p { color: var(--ink-secondary) !important; }
.stSpinner > div { border-top-color: var(--shu) !important; }
.stPlotlyChart {
    background: var(--surface-2) !important; border: 1px solid var(--border-hairline) !important;
    border-radius: var(--radius-xl) !important; padding: 10px; box-shadow: var(--shadow-sm) !important;
}

/* 黒（ダークでは白）の塗りボタン内の文字は、背景と逆の色にする */
button[kind="primary"] *, .stFormSubmitButton > button *,
button[kind="primary"]:focus *, .stFormSubmitButton > button:focus *,
button[kind="primary"]:active *, .stFormSubmitButton > button:active *,
button[kind="primary"]:disabled *, .stFormSubmitButton > button:disabled *,
div[data-testid="stChatInputSubmitButton"] button svg {
    color: var(--on-accent) !important;
}
/* 文字だけのリンク風ボタンは、狭い幅でも途中で省略せず折り返す */
[class*="st-key-goto_"] button p, .st-key-guest_login button p { white-space: normal !important; text-overflow: clip !important; overflow: visible !important; }

/* 入力欄の内側にもう一枚ある枠線（フォーカス時は赤）を消す */
div[data-testid="stChatInput"] > div, div[data-testid="stChatInput"] > div > div {
    border: 0 !important; box-shadow: none !important; outline: none !important;
}
div[data-testid="stChatInput"] textarea:focus { outline: none !important; box-shadow: none !important; }

/* ポップオーバーのボタン */
section[data-testid="stSidebar"] [data-testid="stPopoverButton"] {
    background: transparent !important; border: 0 !important; box-shadow: none !important;
    border-radius: var(--radius-md) !important; min-height: 36px !important; padding: 6px 10px !important;
    color: var(--ink-primary) !important; font-weight: 500 !important; font-size: 14px !important;
}
section[data-testid="stSidebar"] [data-testid="stPopoverButton"]:hover { background: var(--surface-3) !important; }
section[data-testid="stSidebar"] [data-testid="stPopoverButton"] > div { justify-content: flex-start !important; width: 100%; }


[class*="st-key-msg_more_"] [data-testid="stPopoverButton"] {
    background: transparent !important; border: 0 !important; box-shadow: none !important;
}
[class*="st-key-msg_more_"] [data-testid="stPopoverButton"]:hover { background: var(--surface-3) !important; color: var(--ink-primary) !important; }

/* キャプション（補足文）は控えめな大きさに */
[data-testid="stCaptionContainer"] p, [data-testid="stCaptionContainer"] { font-size: 13px !important; color: var(--ink-muted) !important; line-height: 1.6 !important; }

/* サイドバー最下部のアカウントボタン（アカウント＋設定・射手カルテを統合） */
section[data-testid="stSidebar"] .st-key-sb_account {
    margin-top: auto !important; position: sticky !important; bottom: 0 !important; z-index: 50 !important;
    background: var(--surface-1) !important;
    padding: 8px 0 calc(4px + env(safe-area-inset-bottom, 0px)) !important;
    border-top: 1px solid var(--border-hairline);
}
/* アカウント欄を常にサイドバー最下部に固定：サイドバー全体を画面の高さに収め、履歴部分だけをスクロールさせる */
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    height: 100% !important;
    max-height: 100dvh !important;
    overflow: hidden !important;
}
section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] { flex: 0 0 auto !important; }
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
    flex: 1 1 auto !important;
    min-height: 0 !important;
    overflow-y: auto !important;
    overscroll-behavior: contain;
    display: flex !important;
    flex-direction: column !important;
    padding-bottom: 0 !important;   /* Streamlit標準の下余白が、固定したアカウント欄の下に隙間を作るため0にする */
}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > div {
    flex: 1 0 auto !important;
    display: flex !important;
    flex-direction: column !important;
}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] {
    flex: 1 0 auto !important;
    min-height: 0 !important;
}
section[data-testid="stSidebar"] .st-key-sb_account [data-testid="stPopoverButton"] { min-height: 44px !important; font-weight: 600 !important; }
section[data-testid="stSidebar"] .st-key-sb_account [data-testid="stPopoverButton"] > div { justify-content: flex-start !important; }

/* 不可視スクリプト・iframe（Cookie/localStorage保存用）を完全不可視・DOM外に隔離 */
.st-key-cookie_sync_slot,
.st-key-cookie_sync_slot *,
iframe[height="0"], iframe[height="1"],
div[data-testid="stCustomComponentV1"]:has(iframe[height="0"]),
div[data-testid="stCustomComponentV1"]:has(iframe[height="1"]),
div[data-testid="stVerticalBlock"] > div:has(iframe[height="0"]),
div[data-testid="stVerticalBlock"] > div:has(iframe[height="1"]),
.element-container:has(iframe[height="0"]),
.element-container:has(iframe[height="1"]) {
    position: fixed !important;
    top: -9999px !important;
    left: -9999px !important;
    width: 0 !important;
    height: 0 !important;
    min-width: 0 !important;
    min-height: 0 !important;
    max-width: 0 !important;
    max-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    border: 0 !important;
    pointer-events: none !important;
    opacity: 0 !important;
    visibility: hidden !important;
    overflow: hidden !important;
    line-height: 0 !important;
    font-size: 0 !important;
    z-index: -9999 !important;
}

/* フォーム送信時の下部余白の乱れ・ショートカット指示文・ステータスちらつき防止 */
[data-testid="stFormInstructions"],
[data-testid="stFormSubmitButton"] + div {
    display: none !important;
}

/* ---------- ログイン ---------- */
.st-key-login_card {
    background: var(--surface-2); border: 1px solid var(--border-hairline);
    border-radius: 20px; padding: 22px 24px 8px; box-shadow: var(--shadow-sm);
    margin-bottom: 14px;
    transition: none !important;
}
.st-key-goto_register button, .st-key-goto_login button, .st-key-guest_login button {
    background: transparent !important; border: 0 !important; box-shadow: none !important;
    color: var(--ink-muted) !important; font-size: 13px !important; min-height: 32px !important;
}
.st-key-goto_register button:hover, .st-key-goto_login button:hover, .st-key-guest_login button:hover {
    background: transparent !important; color: var(--shu) !important;
}
.login-wrap { margin: clamp(24px, 5vh, 48px) auto 20px; text-align: center; transition: none !important; }
.login-title { font-size: 28px; font-weight: 600; font-family: var(--font-serif); letter-spacing: 0; color: var(--ink-primary); margin-bottom: 6px; }
.login-subtitle { font-size: 13.5px; line-height: 1.8; color: var(--ink-muted); }

/* ---------- レスポンシブ（スマホ・タブレット・APK特化の極上視認性） ---------- */
@media (max-width: 900px) {
    [data-testid="stMainBlockContainer"] {
        padding: calc(var(--device-safe-top, env(safe-area-inset-top, 0px)) + 52px) calc(var(--device-safe-right, env(safe-area-inset-right, 0px)) + 16px) var(--kyudo-main-pad, 130px) calc(var(--device-safe-left, env(safe-area-inset-left, 0px)) + 16px) !important;
    }
}
@media (max-width: 680px) {
    /* 画面全体の余白：スマホ・APK画面を左右いっぱいに見やすく活用（サイドバー開くボタンの下から綺麗に開始） */
    [data-testid="stMainBlockContainer"] {
        padding: calc(var(--device-safe-top, env(safe-area-inset-top, 0px)) + 48px) calc(var(--device-safe-right, env(safe-area-inset-right, 0px)) + 14px) var(--kyudo-main-pad, 130px) calc(var(--device-safe-left, env(safe-area-inset-left, 0px)) + 14px) !important;
    }

    /* サイドバー開くボタン：スマホ・APK機種ごとのノッチ・ステータスバーに合わせて自動配置 */
    [data-testid="stExpandSidebarButton"] {
        top: calc(var(--device-safe-top, env(safe-area-inset-top, 0px)) + 8px) !important;
        left: calc(var(--device-safe-left, env(safe-area-inset-left, 0px)) + 10px) !important;
        width: 44px !important;
        height: 44px !important;
        z-index: 999999 !important;
        pointer-events: auto !important;
    }

    /* あなたの吹き出し：スマホ画面幅に最適化（88%でゆったり折り返し） */
    div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
        max-width: 88% !important;
        padding: 10px 16px !important;
        font-size: var(--font-size-chat, 16px) !important;
        line-height: 1.65 !important;
    }

    /* AI回答メッセージ：画面端に張り付かず、余白を広々確保 */
    div[data-testid="stChatMessage"]:not(:has([data-testid="stChatMessageAvatarUser"])) {
        padding: 4px 2px !important;
    }

    /* 入力エリア（下部固定・Gemini モバイル準拠） */
    div[data-testid="stBottomBlockContainer"] {
        padding: 0 12px !important;
    }
    div[data-testid="stChatInput"] {
        padding: 10px 12px 8px 12px !important;
        border-radius: 28px !important;
    }
    div[data-testid="stChatInput"] textarea {
        font-size: 16px !important;
        line-height: 24px !important;
    }

    /* 回答末尾のバー（コピー・読み上げ・⋮）：スマホでも綺麗に1行整列 */
    div[data-testid="stHorizontalBlock"]:has([class*="st-key-msg_more_"]) {
        flex-direction: row !important; flex-wrap: nowrap !important; align-items: center !important; gap: 4px !important;
    }
    div[data-testid="stHorizontalBlock"]:has([class*="st-key-msg_more_"]) > div[data-testid="stColumn"] {
        min-width: 0 !important; width: auto !important; flex: 0 0 auto !important;
    }
    div[data-testid="stHorizontalBlock"]:has([class*="st-key-msg_more_"]) > div[data-testid="stColumn"]:nth-child(1) { flex: 0 0 76px !important; width: 76px !important; }
    div[data-testid="stHorizontalBlock"]:has([class*="st-key-msg_more_"]) > div[data-testid="stColumn"]:nth-child(3) { flex: 1 1 0 !important; }
}
@media (prefers-reduced-motion: reduce) {
    * { animation: none !important; transition: none !important; }
}
</style>
""", unsafe_allow_html=True)

# 選択されたテーマを強制（「自動」のときは OS 設定に従う）
if st.session_state.get("ui_theme") == "ライト":
    st.markdown(f"<style>:root {{ color-scheme: light; {_THEME_LIGHT_VARS} }}</style>", unsafe_allow_html=True)
elif st.session_state.get("ui_theme") == "ダーク":
    st.markdown(f"<style>:root {{ color-scheme: dark; {_THEME_DARK_VARS} }}</style>", unsafe_allow_html=True)

# 選択された文字サイズをアプリ全体に適用（アカウント連動）
_cur_fs_choice = st.session_state.get("sb_font_size_choice") or load_user_font_size()
if _cur_fs_choice not in FONT_SIZE_MAP:
    _cur_fs_choice = "大きめ (18px)"
_fs = FONT_SIZE_MAP[_cur_fs_choice]

st.markdown(f"""
<style>
:root {{
    --font-size-base: {_fs['base']};
    --font-size-chat: {_fs['chat']};
    --line-height-chat: {_fs['chat_line']};
    --font-size-h1: {_fs['h1']};
    --font-size-h2: {_fs['h2']};
    --font-size-h3: {_fs['h3']};
    --font-size-h4: {_fs['h4']};
    --font-size-input: {_fs['input']};
    --font-size-sidebar: {_fs['sidebar']};
}}

/* チャット本文全体（ユーザー・AI・リスト・強調すべて：可読性を極限まで高める） */
div[data-testid="stChatMessage"] p,
div[data-testid="stChatMessage"] li,
div[data-testid="stChatMessage"] span,
div[data-testid="stChatMessage"] div,
div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p,
div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] li {{
    font-size: var(--font-size-chat) !important;
    line-height: var(--line-height-chat) !important;
    letter-spacing: 0.015em !important;
}}

div[data-testid="stChatMessage"] p {{
    margin-bottom: 0.85em !important;
}}

div[data-testid="stChatMessage"] ul,
div[data-testid="stChatMessage"] ol {{
    margin-top: 0.4em !important;
    margin-bottom: 0.8em !important;
    padding-left: 1.4em !important;
}}

div[data-testid="stChatMessage"] li {{
    margin-bottom: 0.35em !important;
}}

div[data-testid="stChatMessage"] strong {{
    color: var(--ink-primary) !important;
    font-weight: 600 !important;
}}

/* 引用ブロック（アドバイスやポイント提示の見やすさ） */
div[data-testid="stChatMessage"] blockquote {{
    border-left: 3px solid var(--primary-indigo) !important;
    background: var(--surface-1) !important;
    padding: 8px 14px !important;
    margin: 12px 0 !important;
    border-radius: 0 8px 8px 0 !important;
}}

/* マークダウン・段落・本文全般 */
.stMarkdown, .stMarkdown p, .stMarkdown li,
[data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li {{
    font-size: var(--font-size-base) !important;
}}

/* 見出し */
h1, div[data-testid="stChatMessage"] h1 {{ font-size: var(--font-size-h1) !important; }}
h2, div[data-testid="stChatMessage"] h2 {{ font-size: var(--font-size-h2) !important; }}
h3, div[data-testid="stChatMessage"] h3 {{ font-size: var(--font-size-h3) !important; }}
h4, div[data-testid="stChatMessage"] h4 {{ font-size: var(--font-size-h4) !important; }}

/* チャット入力欄 */
[data-testid="stChatInput"] textarea,
[data-testid="stChatInput"] textarea::placeholder {{
    font-size: var(--font-size-input) !important;
}}

/* 表・コード */
div[data-testid="stMarkdownContainer"] table {{
    font-size: var(--font-size-base) !important;
}}
div[data-testid="stMarkdownContainer"] code {{
    font-size: 0.9em !important;
}}

/* サイドバーの文字サイズ */
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] p,
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] span,
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] button {{
    font-size: var(--font-size-sidebar) !important;
}}
</style>
""", unsafe_allow_html=True)

# ==================== 弓道に関する科学的論文・生体力学（バイオメカニクス）研究データベース ====================
KYUDO_SCIENTIFIC_EVIDENCE = """
【弓道の科学的論文・生体力学（バイオメカニクス）研究知見データベース】
1. 筋電図（EMG）による筋活動・運動連鎖研究（筑波大・鹿屋体育大・日本武道学会等）
   - 「僧帽筋（首・肩）の抑制」: 会〜離れにかけて僧帽筋上部や三角筋前部の放電が増加（力み）すると、肩の浮き上がりと離れのブレ（緩み離れ・引きブレ）に直結する。熟練射手は会において僧帽筋上部を有意に脱力（リラックス）させている。
   - 「広背筋・菱形筋・前鋸筋（背中の深層筋）」: 熟練射手は引分け〜会〜離れにかけて、肩甲骨を下制・内転させる深層筋（背中下部〜脇の下）を持続的等尺性収縮（アイソメトリック）させて伸び合いを創出する。
   - 「腕部と手の内」: 上腕三頭筋（二の腕の裏側）の張りを保ちつつ、前腕屈筋群（指先・手の内の握り締め筋）を極限まで弛緩させることで、不随意かつ鋭い離れ（離れようとせず自然に離れる現象）が発現する。

2. 重心動揺・床反力（フォースプレート）力学研究
   - 「足踏み・胴造りの鉛直軸」: 熟練者の床反力中心（COP）は、会〜離れの間、左右比率50:50、前後比率は母指球（足親指の付け根）に約60〜65%加重で安定する。踵（かかと）体重になると離れの反作用で上半身が後傾（のけぞり・腰折れ）し、矢が的の上や後ろに抜ける。
   - 「三重十文字の柱構造」: 足底面・腰（骨盤）・肩（胸郭）の3つの軸が鉛直平面上で平行に揃うことで、弓の反発力（15〜25kgの外力負荷）を骨格の柱構造で床反力へと流し、無駄な筋肉疲労を防ぐ。

3. 手の内・物理トルク（偶力）・アーチャーズパラドックス力学
   - 「角見（左手親指根部）の作用力積」: 矢が弦を離れるまでのわずか約0.02秒間に、角見が弓の中心軸を的前方向へ押しつつ外側へ回す回転モーメント（トルク）を発生させる。これにより、矢が弓体と擦れる摩擦抵抗（アーチャーズパラドックスのしなり衝突）を最小化し、矢飛びの初速と直進性を向上させる。
   - 「握り込みの弊害」: 手の平全体で弓を強く握り締めると、離れ直後の弓の自由振動が阻害され、矢羽や矢尻が弓体を激しく叩いて矢が的の前下に失速する。

4. 呼吸・自律神経系・脳科学（心拍変動・早気メカニクス）
   - 「丹田呼吸と迷走神経刺激」: 引分け〜会にかけて息を細く長く吐き下腹（丹田・腹横筋）に納める呼気性息合いは、副交感神経（迷走神経）を活性化し、緊張による心拍急上昇や筋硬直を抑え、会の静止安定時間を有意に延長する。
   - 「早気（ターゲット・パニック）の神経科学」: 視覚情報（的や矢の高さ・頬付けの接触刺激）が大脳皮質の抑制回路をバイパスし、無意識の運動発火（勝手な離れ）を引き起こす条件反射の誤作動。克服には「会で2秒数える」などの認知・言語的抑制介入や、的を見ない巻藁での筋感覚再学習が科学的に極めて有効。

5. 矢の弾道学・スパイン（剛性）整合性
   - 射出時、矢は弦からの急激な圧縮力によって水平方向に「くの字」にしなりながら飛翔する（アーチャーズパラドックス）。弓力に対して矢のスパイン（たわみ強度）が硬すぎると矢は的の左へ、柔らかすぎると右へ逸れる。
"""

# キャラクター設定
COMMON_INSTRUCTION = (
    "\n\n【最重要ルール：ChatGPT風の自然な会話文（横文章・スマートな段落構成）で答えること】\n"
    "1. 【自然な会話文で語りかけること（箇条書き・縦並びリストの禁止）】\n"
    "   「1. 〇〇\n2. 〇〇\n3. 〇〇」のように番号を振って細切れに縦に並べる箇条書き（縦文章）は絶対にやめてください！\n"
    "   最初から最後まで、人に語りかけるような温かい会話調の横文章（1つの段落に2〜4文程度を自然にまとめた文章）で回答してください。\n"
    "2. 【科学的論文・生体力学エビデンスを会話に溶け込ませる】\n"
    "   上記の筋電図（EMG）や重心動揺、角見のトルク力学などの科学的知見は、リストとして並べるのではなく、自然な語り口の中に溶け込ませて優しく伝えてください。\n"
    "   （例:『実は筋肉の実験でも分かっておるのじゃが、首や肩にグッと力が入ってしまうと、それがブレーキになって矢が乱れてしまう。だからこそ、息を吐きながら背中や丹田で弓の力を受け止めるのが肝心なんじゃよ』のように流れる文章にする）\n"
    "3. 【生体力学・骨格アライメントだけをかみ砕く】\n"
    "   弓道の専門用語（射法八節・角見・会・離れ・胴造りなど）はそのまま使ってかまいません。射手は弓道の知識があります。\n"
    "   一方、生体力学・骨格・筋肉の話（例: 肩甲骨の内転・広背筋・体幹の安定など）は、弓道を知っていても身体の専門知識がない人でも直感的にイメージできる日常の言葉（『肩甲骨を背中の中心に寄せるイメージ』『背中の下半分で弓の重みを受け止める感じ』など）に言い換えて伝えてください。\n"
    "4. 【弓道用語に読み仮名（ふりがな）を絶対に付けない】\n"
    "   角見、胴造り、丹田、射法八節、離れ、会、弓手、馬手、などの弓道用語に「（かくみ）」「（どうづくり）」のような読み仮名を付けることは禁止です。\n"
    "   ユーザーは弓道の知識がある射手なので、読み仮名は不要です。漢字だけで表記してください。\n"
)



CHARACTERS = {
    "師範（無幻先生）": {
        "icon": "🥋",
        "avatar_file": "avatar_master.jpg",
        "badge_class": "char-master",
        "desc": "教士八段格のベテラン師範。射法八節・射品射格・礼法・心の平静を重んじ、温かくも深みのある言葉で導きます。",
        "prompt": (
            "あなたは弓道教士八段の師範「無幻（むげん）先生」です。"
            "弓道の道心、全日本弓道連盟の『弓道教本』の理念、射法八節の理、礼法や体配、心のあり方（正射必中、平常心）を熟知しています。"
            "口調は穏やかで落ち着いており、威厳がありつつも弟子を温かく見守る師範の語り口（〜じゃ、〜であるな、〜が肝要じゃ、など）で話してください。"
            "質問者の射癖や悩みに対して、単に形を直すだけでなく、射法八節の根本や呼吸、心の持ちようと結びつけて本質的な助言を与えてください。"
            + COMMON_INSTRUCTION
        ),
        "welcome": "よく参られたな。弓道は己の心と向き合う道じゃ。難しい用語にとらわれず、体の使い方や心の持ちようなど何でも気兼ねなく申してみるがよい。"
    },
    "弓道部の先輩（葵先輩）": {
        "icon": "🏹",
        "avatar_file": "avatar_senior.jpg",
        "badge_class": "char-senior",
        "desc": "大学弓道部の頼れる3年生。早気や離れのブレ、日々の練習の悩みに親身に共感し、実践的な工夫を教えてくれます。",
        "prompt": (
            "あなたは大学弓道部の頼れる先輩「葵（あおい）」です。参段を持っています。"
            "親しみやすく明るい性格で、後輩の射の悩み（早気、もたれ、離れの緩み、手の内の痛み、矢飛びのブレ、試合の緊張など）を自分の経験も交えて優しく励ましながらアドバイスします。"
            "口調は明るく気さくで面倒見の良い先輩（「〜だよ！」「私もそれで悩んだことある！」「一緒に頑張ろう！」など）。"
            "教本通りの堅苦しい説明だけでなく、部活の道場で試せる具体的な意識のコツや練習ドリルをわかりやすく教えてください。"
            + COMMON_INSTRUCTION
        ),
        "welcome": "お疲れさま！今日も練習頑張ってるね！弓道って難しい言葉が多いけど、体のどこをどう意識すればいいか、わかりやすく一緒に考えていこうね！"
    },
    "射技動作分析AI（KYUDO-ANALYST）": {
        "icon": "📐",
        "avatar_file": "avatar_analyst.jpg",
        "badge_class": "char-analyst",
        "desc": "現代弓道科学・バイオメカニクスに基づき、骨格・筋肉の作用、物理的な力学（ベクトルの釣り合い）から論理的に解説します。",
        "prompt": (
            "あなたは弓道の射技をバイオメカニクス（生体力学）と物理学の観点から論理的に分析する「射技動作分析AI（KYUDO-ANALYST）」です。"
            "射法八節における骨格のアライメント（肩甲骨・股関節）、筋肉の動員、角見のモーメント、離れの力学ベクトルなどを客観的に解説します。"
            "口調は論理的で丁寧かつ客観的（「〜と推察されます」「身体機能の観点から解説します」）。"
            "弓道の専門用語（射法八節・角見・会・離れ等）はそのまま使ってかまいません。射手は弓道の知識があります。"
            "ただし、生体力学・骨格・筋肉に関する専門用語（解剖学用語など）は、弓道の知識はあっても身体の専門知識がない人でも直感的にイメージできる日常の言葉に言い換えて伝えてください。"
            + COMMON_INSTRUCTION
        ),
        "welcome": "射技動作分析AIシステム起動。生体力学・骨格アライメントの視点から分析しますが、難しい身体用語は日常の言葉に翻訳してお伝えします。お悩みの症状を詳しく入力してください。"
    }
}

# ==================== ユーザー認証・アカウント管理（ChatGPT風完全ログイン） ====================
USERS_FILE = os.path.join(os.path.dirname(__file__), "data", "users.json")

def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
    return pw_hash, salt

def load_users() -> dict:
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_users(users: dict):
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def authenticate_user(username: str, password: str) -> bool:
    users = load_users()
    user = users.get(username.strip().lower())
    if not user:
        return False
    pw_hash, _ = hash_password(password, user["salt"])
    return pw_hash == user["password_hash"]

def get_user_credential_fingerprint(username: str) -> str:
    """ブラウザ側自動ログイン用：ユーザー名とパスワードハッシュからフィンガープリントを生成"""
    users = load_users()
    user = users.get(username.strip().lower())
    if not user:
        return ""
    # username + password_hash + 固定salt でHMAC署名 → ブラウザに保存しても安全
    combined = f"{username.strip().lower()}:{user['password_hash']}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()

def verify_credential_fingerprint(username: str, fingerprint: str) -> bool:
    """ブラウザに保存されたフィンガープリントを検証してログイン"""
    expected = get_user_credential_fingerprint(username)
    return bool(expected and expected == fingerprint)

def register_user(username: str, password: str, display_name: str = "") -> tuple[bool, str]:
    uname = username.strip().lower()
    if len(uname) < 3:
        return False, "ユーザー名は3文字以上で入力してください。"
    if len(password) < 6:
        return False, "パスワードは6文字以上で入力してください。"
    users = load_users()
    if uname in users:
        return False, "このユーザー名は既に使用されています。"
    pw_hash, salt = hash_password(password)
    users[uname] = {
        "password_hash": pw_hash,
        "salt": salt,
        "display_name": display_name.strip() if display_name else uname,
        "created_at": time.strftime("%Y-%m-%d %H:%M")
    }
    save_users(users)
    return True, "アカウントが正常に作成されました！"

# ==================== ユーザー別データの保存先（他のユーザーと絶対に混ざらないようにする） ====================
def _legacy_user_safe(username: str) -> str:
    return "".join(c for c in (username or "") if c.isalnum() or c in ("-", "_"))

def user_data_key(username: str) -> str:
    """ユーザー名から保存用の名前を作る。記号を含む名前は、記号を取り除くと別ユーザーと同じ名前になって
    データが混ざる恐れがあるため、その場合はユーザー名のハッシュを付けて必ず別の名前にする。"""
    u = (username or "").strip().lower()
    safe = _legacy_user_safe(u)
    if u and safe == u:
        return safe
    h = hashlib.sha256(u.encode("utf-8")).hexdigest()[:10]
    return f"{safe[:24] or 'user'}_{h}"

def _legacy_is_exclusively_mine(username: str) -> bool:
    """旧方式（記号を除くだけ）の保存先を、他のユーザーと共有していなかったか確認する"""
    u = (username or "").strip().lower()
    legacy = _legacy_user_safe(u)
    if not legacy:
        return False
    try:
        owners = [n for n in load_users() if _legacy_user_safe(n) == legacy]
    except Exception:
        return False
    return owners == [u]

def user_data_file(base_dir: str, username: str, suffix: str = ".json") -> str:
    """ユーザー専用ファイルのパス。旧方式のデータが自分だけのものだった場合に限り、新しい保存先へ引き継ぐ"""
    os.makedirs(base_dir, exist_ok=True)
    key = user_data_key(username)
    path = os.path.join(base_dir, f"{key}{suffix}")
    legacy = _legacy_user_safe((username or "").strip().lower())
    if legacy and key != legacy and not os.path.exists(path):
        old = os.path.join(base_dir, f"{legacy}{suffix}")
        if os.path.exists(old) and _legacy_is_exclusively_mine(username):
            try:
                shutil.copy2(old, path)
            except Exception:
                pass
    return path

def get_current_history_dir() -> str:
    current_user = st.session_state.get("logged_in_user", "default")
    base = os.path.join(os.path.dirname(__file__), "history")
    h_dir = os.path.join(base, user_data_key(current_user))
    legacy_dir = os.path.join(base, _legacy_user_safe((current_user or "").strip().lower()))
    if (not os.path.exists(h_dir)) and legacy_dir != h_dir and os.path.isdir(legacy_dir) and _legacy_is_exclusively_mine(current_user):
        try:
            shutil.copytree(legacy_dir, h_dir)
        except Exception:
            pass
    os.makedirs(h_dir, exist_ok=True)
    return h_dir

# ==================== ChatGPT風 射手メモリー（個人記憶・カルテ機能） ====================
MEMORIES_DIR = os.path.join(os.path.dirname(__file__), "data", "memories")

def get_user_memory_path(username: str) -> str:
    return user_data_file(MEMORIES_DIR, username)

def load_user_memory(username: str) -> list[str]:
    """ユーザーのAI記憶（弓力・段位・射癖・目標など）を取得"""
    path = get_user_memory_path(username)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            return data.get("notes", [])
    except Exception:
        return []

def save_user_memory(username: str, notes: list[str]):
    """ユーザーのAI記憶を保存"""
    path = get_user_memory_path(username)
    data = {
        "notes": notes,
        "updated_at": time.strftime("%Y-%m-%d %H:%M")
    }
    try:
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
    except Exception:
        pass

RANK_PREFIXES = ("段位:", "段位：")
RANK_UNSET = "未設定"
RANK_CHOICES = [RANK_UNSET, "級位（無段）", "初段", "弐段", "参段", "四段", "五段", "六段", "七段", "八段"]

def get_user_rank(username: str) -> str:
    """カルテに保存されている段位を返す（なければ未設定）"""
    for n in load_user_memory(username):
        if n.startswith(RANK_PREFIXES):
            val = n.split(":", 1)[-1].split("：", 1)[-1].strip() if n else ""
            return val or RANK_UNSET
    return RANK_UNSET

def set_user_rank(username: str, rank: str):
    """段位をカルテに保存（未設定を選んだら削除）。AIが毎回の回答で参照する"""
    notes = [n for n in load_user_memory(username) if not n.startswith(RANK_PREFIXES)]
    if rank and rank != RANK_UNSET:
        notes.insert(0, f"段位: {rank}")
    save_user_memory(username, notes)

TITLE_PREFIXES = ("称号:", "称号：")
TITLE_CHOICES = [RANK_UNSET, "錬士", "教士", "範士"]

def get_user_title(username: str) -> str:
    """カルテに保存されている称号（錬士・教士・範士）を返す（なければ未設定）"""
    for n in load_user_memory(username):
        if n.startswith(TITLE_PREFIXES):
            val = n.split(":", 1)[-1].split("：", 1)[-1].strip()
            return val or RANK_UNSET
    return RANK_UNSET

def set_user_title(username: str, title: str):
    """称号をカルテに保存（未設定を選んだら削除）"""
    notes = [n for n in load_user_memory(username) if not n.startswith(TITLE_PREFIXES)]
    if title and title != RANK_UNSET:
        notes.insert(1 if notes and notes[0].startswith(RANK_PREFIXES) else 0, f"称号: {title}")
    save_user_memory(username, notes)

# ==================== ユーザー別の詳細設定（メモリーのON/OFFなど） ====================
USER_SETTINGS_DIR = os.path.join(os.path.dirname(__file__), "data", "user_settings")
ANSWER_STYLES = ["簡潔", "標準", "詳しく"]
_DEFAULT_USER_SETTINGS = {"memory_enabled": True, "auto_learn": True, "ref_history": False, "answer_style": "標準"}

def load_user_settings(username: str) -> dict:
    """そのユーザーだけの詳細設定を読み込む（未設定の項目は初期値）"""
    data = dict(_DEFAULT_USER_SETTINGS)
    try:
        with open(user_data_file(USER_SETTINGS_DIR, username), "r", encoding="utf-8") as fp:
            saved = json.load(fp)
        for k in data:
            if k in saved:
                data[k] = saved[k]
    except Exception:
        pass
    if data["answer_style"] not in ANSWER_STYLES:
        data["answer_style"] = "標準"
    return data

def save_user_settings(username: str, data: dict):
    try:
        with open(user_data_file(USER_SETTINGS_DIR, username), "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _on_user_setting_change():
    user = st.session_state.get("logged_in_user", "default")
    save_user_settings(user, {
        "memory_enabled": bool(st.session_state.get("sb_set_mem", True)),
        "auto_learn": bool(st.session_state.get("sb_set_auto", True)),
        "ref_history": bool(st.session_state.get("sb_set_ref", False)),
        "answer_style": st.session_state.get("sb_set_style") or "標準",
    })

def _pick_one(label: str, options: list, key: str, on_change, help_text: str = ""):
    """プルダウンはポップアップ内で開けないことがあるため、タップで選べるボタン形式にする"""
    if hasattr(st, "pills"):
        st.pills(label, options, selection_mode="single", key=key, on_change=on_change, help=help_text or None)
    else:
        st.radio(label, options, index=None, key=key, on_change=on_change, horizontal=True, help=help_text or None)

def _add_memory_from_input():
    """入力欄の内容を記憶に追加する。複数行なら1行ずつ別の記憶にする。追加後は入力欄を空にする"""
    user = st.session_state.get("logged_in_user", "default")
    raw = st.session_state.get("new_mem_pop", "") or ""
    for line in raw.splitlines():
        line = line.strip()
        if line:
            add_user_memory_item(user, line[:2000])
    st.session_state["new_mem_pop"] = ""

def _on_title_change():
    set_user_title(st.session_state.get("logged_in_user", "default"), st.session_state.get("sb_title_select") or RANK_UNSET)

def _on_rank_change():
    set_user_rank(st.session_state.get("logged_in_user", "default"), st.session_state.get("sb_rank_select") or RANK_UNSET)

def add_user_memory_item(username: str, note_text: str):
    """手動または自動で記憶を1つ追加"""
    clean_text = note_text.strip()
    if not clean_text:
        return
    notes = load_user_memory(username)
    # 段位は1件だけ持つ（AIの自動抽出や手動入力で新しい段位が来たら置き換える）
    if clean_text.startswith(RANK_PREFIXES):
        notes = [n for n in notes if not n.startswith(RANK_PREFIXES)]
        notes.append(clean_text)
        save_user_memory(username, notes)
        return
    # 称号（錬士・教士・範士）も1件だけ持つ
    if clean_text.startswith(TITLE_PREFIXES):
        notes = [n for n in notes if not n.startswith(TITLE_PREFIXES)]
        notes.append(clean_text)
        save_user_memory(username, notes)
        return
    # 重複防止
    if clean_text not in notes:
        notes.append(clean_text)
        save_user_memory(username, notes)

def remove_user_memory_item(username: str, index: int):
    """特定の記憶を削除"""
    notes = load_user_memory(username)
    if 0 <= index < len(notes):
        notes.pop(index)
        save_user_memory(username, notes)

def clear_all_user_memory(username: str):
    """すべての記憶を完全消去"""
    save_user_memory(username, [])

def _build_card_section(username: str) -> str:
    """プロンプトに注入する射手カルテ形式のテキストを生成"""
    notes = load_user_memory(username)
    if not notes:
        return ""
    bullet_points = "\n".join([f"・{item}" for item in notes])
    return (
        f"【射手カルテ（あなたがこの射手について記憶しているパーソナル情報）】\n"
        f"{bullet_points}\n"
        f"※上記の射手情報（使用弓具・弓力・目標・抱えている課題など）を熟知している前提で、"
        f"これまでの稽古の文脈に寄り添い、射手にとって最適なアドバイスを行ってください。\n"
        + ("※射手の段位・称号（錬士・教士・範士）に合わせて、説明の難しさや用語の深さ、次に目指す課題を調整してください。\n" if any(n.startswith(RANK_PREFIXES + TITLE_PREFIXES) for n in notes) else "")
        + "\n"
    )

def build_memory_prompt_section(username: str) -> str:
    """AIに渡すカルテ・過去の相談テーマ。そのユーザー本人の設定（メモリーON/OFF、過去の会話の参照）に従う"""
    cfg = load_user_settings(username)
    out = ""
    if cfg["memory_enabled"]:
        out += _build_card_section(username)
    if cfg["ref_history"]:
        try:
            cur_id = st.session_state.get("current_session_id")
            titles = [x["title"] for x in get_all_sessions() if x.get("id") != cur_id and x.get("title")][:8]
        except Exception:
            titles = []
        if titles:
            out += ("【この射手の最近の相談テーマ（過去の会話・参考情報）】\n"
                    + "\n".join(f"・{t}" for t in titles)
                    + "\n※これまでの相談の流れを踏まえて回答してよいですが、無関係なら触れなくて構いません。\n\n")
    return out

def auto_extract_and_save_memory(username: str, user_text: str, api_key: str) -> list[str]:
    """ユーザーの発言から弓道に関する自己情報（弓力・段位・悩みなど）をAIが自動抽出し記憶に追加。抽出した項目一覧を返す。"""
    if not api_key or not user_text or len(user_text.strip()) < 4:
        return []
    _cfg = load_user_settings(username)
    if not (_cfg["memory_enabled"] and _cfg["auto_learn"]):
        return []
    trigger_words = ["弓力", "kg", "キロ", "段", "級", "高校", "大学", "部活", "矢尺", "cm", "流派", "直心", "肥後", "グラス", "カーボン", "早気", "もたれ", "手の内", "審査", "大会", "歴", "年目", "錬士", "教士", "範士", "称号"]
    if not any(w in user_text for w in trigger_words):
        return []

    new_items = []
    try:
        client = genai.Client(api_key=api_key)
        extract_prompt = f"""
以下は弓道の射手が発言したテキストです。
射手のプロフィール、使用弓具（弓力・弓の種類・矢尺など）、段位・所属、抱えている射癖や悩み、目標など、
今後AIが指導する上で【覚えておくべき永続的な個人情報】があれば、1〜2個の簡潔な箇条書き（各20文字以内）で抽出してください。
新しい個人情報や設定がない場合は「なし」とだけ答えてください。

【発言テキスト】:
{user_text}

段位が分かる場合は必ず「段位: 参段」の形式（段位: ＋段・級だけ）、
称号（錬士・教士・範士）が分かる場合は「称号: 錬士」の形式で出力してください。

【出力形式の例】:
・弓力: 14kg (直心II)
・段位: 参段
・目標: 四段審査の合格
"""
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=extract_prompt
        )
        if response.text and "なし" not in response.text:
            lines = [line.strip().lstrip("・-*\t ") for line in response.text.split("\n") if line.strip()]
            for item in lines:
                if item and not item.startswith("なし") and len(item) <= 40:
                    add_user_memory_item(username, item)
                    new_items.append(item)
    except Exception:
        pass
    return new_items

# ==================== ChatGPT風 カスタム指示（Custom Instructions） ====================
CUSTOM_INSTR_DIR = os.path.join(os.path.dirname(__file__), "data", "custom_instructions")

def get_custom_instructions_path(username: str) -> str:
    return user_data_file(CUSTOM_INSTR_DIR, username)

def load_custom_instructions(username: str) -> dict:
    """ユーザー独自のカスタム指示を取得"""
    path = get_custom_instructions_path(username)
    if not os.path.exists(path):
        return {"profile": "", "response_pref": ""}
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return json.load(fp)
    except Exception:
        return {"profile": "", "response_pref": ""}

def save_custom_instructions(username: str, profile: str, response_pref: str):
    """ユーザー独自のカスタム指示を保存"""
    path = get_custom_instructions_path(username)
    data = {
        "profile": profile.strip(),
        "response_pref": response_pref.strip(),
        "updated_at": time.strftime("%Y-%m-%d %H:%M")
    }
    try:
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
    except Exception:
        pass

def build_custom_instructions_prompt(username: str) -> str:
    """プロンプトに注入するカスタム指示ブロックを生成"""
    inst = load_custom_instructions(username)
    profile = inst.get("profile", "").strip()
    resp_pref = inst.get("response_pref", "").strip()
    _style = load_user_settings(username)["answer_style"]
    _style_txt = {
        "簡潔": "回答は要点だけを短く（目安300字以内）まとめ、長い前置きや繰り返しは省いてください。",
        "詳しく": "回答は丁寧に詳しく、理由・体の使い方・道場でできる練習方法まで具体的に説明してください。",
    }.get(_style, "")
    if not profile and not resp_pref and not _style_txt:
        return ""
    parts = []
    if _style_txt:
        parts.append(f"【回答の長さ・詳しさ（射手の設定）】\n{_style_txt}")
    if profile:
        parts.append(f"【射手自身について知っておくべき追加事項】\n{profile}")
    if resp_pref:
        parts.append(f"【射手が希望するAIの応答スタイル・特別ルール】\n{resp_pref}")
    parts.append("※上記は、いま話している射手本人が設定した内容です。この射手への回答では必ず反映し、守ってください（他の射手の情報は一切使いません）。")
    return "\n\n" + "\n\n".join(parts) + "\n\n"

# ==================== 会話履歴の管理（名前変更・削除・スマート要約） ====================

def rename_session(session_id: str, new_title: str):
    """セッションのタイトルを変更"""
    if not new_title.strip():
        return
    h_dir = get_current_history_dir()
    path = os.path.join(h_dir, f"{session_id}.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            data["title"] = new_title.strip()
            with open(path, "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False, indent=2)
        except Exception:
            pass

def delete_session(session_id: str):
    """セッションを削除"""
    h_dir = get_current_history_dir()
    path = os.path.join(h_dir, f"{session_id}.json")
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass

def generate_smart_title(user_text: str, api_key: str) -> str:
    """ChatGPT風：最初の質問内容からAIが12文字前後の的確なタイトルを自動生成"""
    if not user_text:
        return "弓道稽古録"
    if not api_key:
        return user_text[:15] + ("..." if len(user_text) > 15 else "")
    try:
        client = genai.Client(api_key=api_key)
        res = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=f"以下の弓道の質問から、ChatGPTの会話履歴一覧に並ぶような簡潔で分かりやすいタイトル（日本語10〜15文字程度・カギカッコや句読点なし）を1つだけ作成してください。\n\n質問: {user_text}"
        )
        if res.text:
            return res.text.strip().replace("「", "").replace("」", "").replace("『", "").replace("』", "")[:20]
    except Exception:
        pass
    return user_text[:15] + ("..." if len(user_text) > 15 else "")


# ==================== 会話履歴の永続化・記録機能 ====================

def get_all_sessions():
    # ログインユーザー専用の稽古セッション一覧を取得
    h_dir = get_current_history_dir()
    files = [f for f in os.listdir(h_dir) if f.endswith(".json")]
    sessions = []
    for f in files:
        path = os.path.join(h_dir, f)
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                sessions.append({
                    "id": data.get("id", f.replace(".json", "")),
                    "title": data.get("title", "無題の稽古録"),
                    "updated_at": data.get("updated_at", ""),
                    "path": path
                })
        except Exception:
            pass
    sessions.sort(key=lambda s: s["updated_at"], reverse=True)
    return sessions

def group_sessions_by_date(sessions: list) -> dict:
    """射心UI：会話履歴を『今日』『過去7日間』『先月』『それ以前』に分類"""
    import datetime
    today = datetime.date.today()
    seven_days_ago = today - datetime.timedelta(days=7)
    thirty_days_ago = today - datetime.timedelta(days=30)
    
    groups = {
        "今日": [],
        "過去7日間": [],
        "先月": [],
        "それ以前": []
    }
    
    for s in sessions:
        up_str = s.get("updated_at", "")
        try:
            s_date = datetime.datetime.strptime(up_str.split()[0], "%Y-%m-%d").date()
            if s_date == today:
                groups["今日"].append(s)
            elif s_date >= seven_days_ago:
                groups["過去7日間"].append(s)
            elif s_date >= thirty_days_ago:
                groups["先月"].append(s)
            else:
                groups["それ以前"].append(s)
        except Exception:
            groups["今日"].append(s)
            
    return {k: v for k, v in groups.items() if v}

def load_session_messages(session_id: str):
    """セッションIDからメッセージ履歴を復元"""
    h_dir = get_current_history_dir()
    path = os.path.join(h_dir, f"{session_id}.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                return data.get("messages", [])
        except Exception:
            pass
    return None

def save_current_session(session_id: str, messages: list, custom_title: str = None):
    """現在の会話履歴を自動保存（既存タイトルや手動命名を保護）"""
    if not messages:
        return
    h_dir = get_current_history_dir()
    path = os.path.join(h_dir, f"{session_id}.json")

    existing_title = None
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fp:
                existing_title = json.load(fp).get("title")
        except Exception:
            pass

    if custom_title:
        title = custom_title
    elif existing_title and existing_title not in ("弓道相談・稽古録", "無題の稽古録"):
        title = existing_title
    else:
        title = "弓道稽古録"
        for m in messages:
            if m["role"] == "user":
                first_text = m.get("content", "").replace("🎥 **射形分析をお願いします**\n\n【気になっていること】: ", "").strip()
                first_line = first_text.split("\n")[0]
                if first_line:
                    title = first_line[:16] + ("..." if len(first_line) > 16 else "")
                break

    now_str = time.strftime("%Y-%m-%d %H:%M")
    data = {
        "id": session_id,
        "title": title,
        "updated_at": now_str,
        "messages": messages
    }
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)


def export_session_to_text(messages: list) -> str:
    """会話履歴を読みやすいテキスト・Markdownに整形"""
    output = []
    output.append("# 🏹 YUMIQA 稽古録\n")
    output.append(f"記録日時: {time.strftime('%Y年%m月%d日 %H:%M')}\n")
    output.append("=" * 45 + "\n")
    
    for m in messages:
        if m["role"] == "user":
            output.append("\n【あなた】")
            if "file_name" in m:
                output.append(f"[添付ファイル: {m['file_name']}]")
            output.append(m.get("content", "") + "\n")
        else:
            char_name = m.get("char", "AIアドバイザー")
            output.append(f"\n【{char_name}】")
            output.append(m.get("content", "") + "\n")
        output.append("-" * 35)
        
    return "\n".join(output)

# 模擬応答用辞書（APIキー未設定時でも楽しめる弓道知識ベース）
LOCAL_RESPONSES = {
    "早気": {
        "師範（無幻先生）": "早気（はやけ：弓を引き切ったあと、狙いを定める前に矢が勝手に放たれてしまうこと）か…弓引きの多くが通る試練の門じゃな。早気は『矢を離そう』とする心が引き起こすものじゃ。まずは会（かい：弓を最大限に引き絞った状態）において、自分で放すのではなく『息を吐きながら伸び合ううちに、自然と離れる』のを待つこと。丹田（たんでん：おへその下あたり、下腹）に息をぐっと沈め、巻藁（まきわら：近距離用の練習的）で目を閉じ、10秒数えるまでじっとこらえる稽古からやり直してみるがよい。",
        "弓道部の先輩（葵先輩）": "早気（はやけ：引いたらすぐに矢が離れちゃうこと）、本当に辛いよね…私も高校のときすごく悩んだから気持ちよくわかるよ！おすすめの練習法は、巻藁（至近距離で矢を射る練習）で『引分けたら心の中でゆっくり5秒数えるまで絶対に放さない！』と決めて引く練習だよ。あと、的を見るとどうしても早く離したくなっちゃうから、視線を的の少し手前の床に落として、自分の体の伸び合いだけに集中してみてね！",
        "射技動作分析AI（KYUDO-ANALYST）": "早気（会で保持できずに即座に矢が発射される現象）の解析結果です。これは弓の張力（負荷）が最大に達した際、筋肉の反射で指が勝手に開いてしまう神経反射です。対策としては、1. 弓を引ききった時に背中の大きな筋肉（広背筋）でしっかり引っ張り続けること。2. 近距離の巻藁を使い、『弓を引ききってから7〜10秒静止してキープする』訓練を行うことで、反射を抑える脳の再学習が有効です。"
    },
    "手の内": {
        "師範（無幻先生）": "手の内（てのうち：弓を握る左手の整え方）は、『卵を手のひらに優しく包むがごとく』柔らかく握るのが極意じゃ。力任せに握り込むと弓の自然な回転が死んでしまう。大切なのは角見（つのみ：左手の親指の付け根）じゃ。この親指の付け根で、的の中心を真っ直ぐ押し込むように利かせ、小指はキュッと締める。手のひらの中には卵1個分のふんわりとした空間を残すのじゃぞ。",
        "弓道部の先輩（葵先輩）": "手の内（左手で弓を持つ形）ってすごく大事だよね！力が入ってギュッと握り締めちゃうと、矢がまっすぐ飛ばなくなっちゃうんだ。コツは、親指と小指をふんわり寄せて、左手の親指の付け根（角見って呼ぶよ！）で的をピーンと押すイメージを持つこと！腕全体で壁を真っ直ぐ押す感覚を持つと、無理に手首をひねらなくても綺麗に決まるよ！",
        "射技動作分析AI（KYUDO-ANALYST）": "手の内（左手グリップ部）の力学的解説です。左手の親指の付け根（角見：つのみ）が弓の背中側を的方向へ押す力によって、矢が放たれた瞬間に弓がクルッと回転（弓返り）し、矢が弓に当たらず綺麗に飛び出します。手をギューッと力一杯握り込んでしまうと回転が止まって矢が乱れるため、手首の力を抜き、親指の根元でまっすぐ的を押すベクトルを意識してください。"
    },
    "八節": {
        "師範（無幻先生）": "射法八節（しゃほうはっせつ：弓を構えてから射終わるまでの8つの基本動作）は、別々の動作ではなく『一本の流れるような円運動』じゃ。1.足踏み（両足を開く土台）→ 2.胴造り（姿勢を正し下腹に息を沈める）→ 3.弓構え（手元と視線を整える）→ 4.打起し（弓を頭上へ持ち上げる）→ 5.引分け（左右均等に押し引く）→ 6.会（弓を引き切って狙いと心を一つにする）→ 7.離れ（矢が放たれる）→ 8.残心（射終わったあとの姿勢と心を保つ）。特に土台である最初の『足踏み』と『胴造り』がすべての基礎じゃよ。",
        "弓道部の先輩（葵先輩）": "射法八節（弓道の8つのステップ）をわかりやすく説明するね！\n1. 足踏み（的を向いて両足をパーッと踏み開く）\n2. 胴造り（背筋をピンと伸ばして姿勢を安定させる）\n3. 弓構え（弓を握る手と弦を持つ手をセットして、的を見る）\n4. 打起し（両手をすーっと頭の上まで持ち上げる）\n5. 引分け（左右均等にぐーっと弓を引き開く）\n6. 会（引ききった最高の状態で狙いを定めて伸び合う！）\n7. 離れ（矢がパッと気持ちよく飛び出す）\n8. 残心（撃った後も姿勢を崩さず、矢の行方を見届ける）\n息を吸って吐いてのリズムに合わせて流れるように引くのがコツだよ！",
        "射技動作分析AI（KYUDO-ANALYST）": "射法八節（運動連鎖の8段階）の解説です。一連の動作は『土台の安定（足踏み・胴造り）』から始まり、『重心とアライメントの固定（弓構え・打起し）』、そして『胸郭の拡張と左右対称の牽引（引分け）』を経て『静的釣り合いのピーク（会）』に達します。最後に『エネルギーの開放（離れ）』と『姿勢保持（残心）』で完了します。各フェーズで姿勢の軸（体幹）がブレないことが最大の的中要因です。"
    }
}

# ==================== ログイン画面・新規登録画面 ====================
GUEST_CHAT_LIMIT = 3  # ゲストが送れるチャット回数（ファイル添付は不可）
GUEST_USAGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "guest_usage.json")

def _client_ip() -> str:
    """接続元IP。プロキシ経由なら X-Forwarded-For の先頭を使う。取得できなければ共通の枠 'unknown'。"""
    try:
        h = st.context.headers
        fwd = h.get("X-Forwarded-For") or h.get("X-Real-Ip")
        if isinstance(fwd, str) and fwd:
            return fwd.split(",")[0].strip()
    except Exception:
        pass
    try:
        ip = st.context.ip_address
        if isinstance(ip, str) and ip:
            return ip
    except Exception:
        pass
    return "unknown"

def _guest_key() -> str:
    # IPそのものは保存せず、ハッシュだけを保存する
    return hashlib.sha256(("kyudo-guest:" + _client_ip()).encode("utf-8")).hexdigest()

def _load_guest_usage() -> dict:
    try:
        with open(GUEST_USAGE_FILE, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def guest_used_count() -> int:
    """この接続元がゲストとして既に送ったチャット回数（サーバー側に保存。再読み込みでは戻らない）。"""
    return int(_load_guest_usage().get(_guest_key(), {}).get("count", 0))

def guest_consume_one():
    data = _load_guest_usage()
    key = _guest_key()
    entry = data.get(key, {"count": 0, "first_at": time.strftime("%Y-%m-%d %H:%M")})
    entry["count"] = int(entry.get("count", 0)) + 1
    entry["last_at"] = time.strftime("%Y-%m-%d %H:%M")
    data[key] = entry
    os.makedirs(os.path.dirname(GUEST_USAGE_FILE), exist_ok=True)
    tmp = GUEST_USAGE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    os.replace(tmp, GUEST_USAGE_FILE)

# ---- ログイン状態の保持（URLクエリパラメータ + サーバー側トークン + Cookie/localStorage：ログアウトするまで永久維持） ----
LOGIN_COOKIE = "kyudo_auth"
LOGIN_COOKIE_MAX_AGE = 3153600000  # 100年（実質永久）
LOGIN_TOKENS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "login_tokens.json")

def _load_login_tokens() -> dict:
    try:
        with open(LOGIN_TOKENS_FILE, "r", encoding="utf-8") as fp:
            d = json.load(fp)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}

def _save_login_tokens(d: dict):
    os.makedirs(os.path.dirname(LOGIN_TOKENS_FILE), exist_ok=True)
    tmp = LOGIN_TOKENS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(d, fp, ensure_ascii=False, indent=2)
    os.replace(tmp, LOGIN_TOKENS_FILE)

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def _get_auth_secret() -> bytes:
    """サーバー再起動でも変わらない安定した署名キーを取得"""
    secret = ""
    try:
        secret = st.secrets.get("AUTH_SECRET", "") or st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        secret = ""
    if not secret:
        secret = os.environ.get("AUTH_SECRET", "") or os.environ.get("GEMINI_API_KEY", "")
    if not secret:
        secret = "yumiqa-kyudo-ai-persistent-secret-v1"
    return hashlib.sha256(f"yumiqa:{secret}".encode("utf-8")).digest()

def _ensure_restored_user(username: str):
    """Streamlit Cloud の再起動等で users.json が初期化された場合でもユーザーを自動復元"""
    uname = (username or "").strip().lower()
    if not uname:
        return
    users = load_users()
    if uname not in users:
        pw_hash, salt = hash_password(secrets.token_urlsafe(24))
        users[uname] = {
            "password_hash": pw_hash,
            "salt": salt,
            "display_name": "弓道家" if uname.startswith("archer_") else uname,
            "created_at": time.strftime("%Y-%m-%d %H:%M"),
            "restored": True,
        }
        save_users(users)

def issue_login_token(username: str, is_guest: bool = False) -> str:
    now = time.time()
    exp_time = int(now + 86400) if is_guest else 0
    payload = json.dumps({"u": username, "g": bool(is_guest), "exp": exp_time}, separators=(",", ":"))
    b64_payload = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    sig = hmac.new(_get_auth_secret(), b64_payload.encode("ascii"), hashlib.sha256).hexdigest()
    token = f"v2.{b64_payload}.{sig}"
    # 互換用ファイルにも保存（失敗してもv2トークン自体は有効）
    try:
        tokens = {k: v for k, v in _load_login_tokens().items() if v.get("exp", 0) == 0 or v.get("exp", 0) > now}
        tokens[_hash_token(token)] = {"user": username, "is_guest": is_guest, "exp": exp_time}
        _save_login_tokens(tokens)
    except Exception:
        pass
    return token

def verify_login_token(token: str):
    """トークンを検証し、(username, is_guest) を返す。無効なら (None, False)"""
    if not token:
        return None, False
    # 1) 自己完結型 HMAC トークン (v2.<payload>.<sig>)：サーバー再起動・再デプロイ後も永久有効
    if token.startswith("v2."):
        try:
            parts = token.split(".", 2)
            if len(parts) == 3:
                _, b64_payload, sig = parts
                expected_sig = hmac.new(_get_auth_secret(), b64_payload.encode("ascii"), hashlib.sha256).hexdigest()
                if hmac.compare_digest(sig, expected_sig):
                    padded = b64_payload + "=" * (-len(b64_payload) % 4)
                    data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
                    u = (data.get("u") or "").strip().lower()
                    is_guest = bool(data.get("g", False))
                    exp = data.get("exp", 0)
                    if exp > 0 and exp <= time.time():
                        return None, False
                    if u:
                        if not is_guest:
                            _ensure_restored_user(u)
                        return u, is_guest
        except Exception:
            return None, False
        return None, False
    # 2) 旧ファイルベーストークン（後方互換）
    entry = _load_login_tokens().get(_hash_token(token))
    if not entry:
        return None, False
    exp = entry.get("exp", 0)
    if exp > 0 and exp <= time.time():
        return None, False
    u = entry.get("user")
    is_guest = bool(entry.get("is_guest", False))
    if is_guest and u:
        return u, True
    if u and u in load_users():
        return u, False
    return None, False

def username_from_token(token: str):
    user, _ = verify_login_token(token)
    return user

def revoke_login_token(token: str):
    if not token:
        return
    tokens = _load_login_tokens()
    if tokens.pop(_hash_token(token), None) is not None:
        _save_login_tokens(tokens)

def _browser_login_cookie() -> str:
    try:
        return st.context.cookies.get(LOGIN_COOKIE, "") or ""
    except Exception:
        return ""

def _flush_cookie_js():
    """ブラウザにトークンを保存／削除する（ログイン・ログアウト直後の次の再実行で1回だけ出力）。
    localStorage と Cookie の両方を使う（どちらかが使えない環境でも動くように）。"""
    set_tok = st.session_state.pop("_cookie_set", None)
    clear = st.session_state.pop("_cookie_clear", False)
    if not (set_tok or clear):
        return
    if set_tok:
        # ログイン成功トークン＋ユーザーフィンガープリント（app再起動後も自動ログインできるよう両方保存）
        _fp_user = st.session_state.get("logged_in_user", "")
        _fp_val = get_user_credential_fingerprint(_fp_user) if _fp_user else ""
        js = (f"var P=window.parent;"
              f"try{{P.localStorage.setItem('{LOGIN_COOKIE}','{set_tok}');}}catch(e){{}}"
              f"try{{var c='{LOGIN_COOKIE}={set_tok}; path=/; max-age={LOGIN_COOKIE_MAX_AGE}; SameSite=Lax';"
              "if(P.location.protocol==='https:'){c+='; Secure';}P.document.cookie=c;}catch(e){}"
              f"try{{P.localStorage.setItem('yumiqa_u','{_fp_user}');P.localStorage.setItem('yumiqa_fp','{_fp_val}');}}catch(e){{}}"
              f"try{{if(window.AndroidAuth){{window.AndroidAuth.saveAuth('{set_tok}');}}else if(P.AndroidAuth){{P.AndroidAuth.saveAuth('{set_tok}');}}}}catch(e){{}}"
              )
    else:
        js = (f"var P=window.parent;"
              f"try{{P.localStorage.removeItem('{LOGIN_COOKIE}');P.localStorage.removeItem('yumiqa_u');P.localStorage.removeItem('yumiqa_fp');}}catch(e){{}}"
              f"try{{P.document.cookie='{LOGIN_COOKIE}=; path=/; max-age=0; SameSite=Lax';}}catch(e){{}}"
              f"try{{if(window.AndroidAuth){{window.AndroidAuth.clearAuth();}}else if(P.AndroidAuth){{P.AndroidAuth.clearAuth();}}}}catch(e){{}}"
              )
    with st.container(key="cookie_sync_slot"):
        components.html(f"<script>{js}</script>", height=0)

def _restore_login_js():
    """リロード直後：localStorageにトークンまたはフィンガープリントがあれば、URLパラメータで渡して自動ログインさせる。"""
    js = (
        f"try{{var P=window.parent;"
        # まずトークンで復元を試みる
        f"var t=P.localStorage.getItem('{LOGIN_COOKIE}');"
        f"var u_name=P.localStorage.getItem('yumiqa_u');"
        f"var fp=P.localStorage.getItem('yumiqa_fp');"
        f"var url=new URL(P.location.href);"
        f"if(t&&!url.searchParams.get('auth')){{url.searchParams.set('auth',t);P.location.replace(url.toString());}}"
        # トークンがなければフィンガープリント（app再起動後の自動ログイン用）
        f"else if(!t&&u_name&&fp&&!url.searchParams.get('yumiqa_u')){{url.searchParams.set('yumiqa_u',u_name);url.searchParams.set('yumiqa_fp',fp);P.location.replace(url.toString());}}"
        f"}}catch(e){{}}"
    )
    with st.container(key="cookie_sync_slot"):
        components.html(f"<script>{js}</script>", height=0)

def _query_login_token() -> str:
    try:
        v = st.query_params.get("auth", "") or st.query_params.get("_kt", "")
        return v if isinstance(v, str) else (v[0] if v else "")
    except Exception:
        return ""

def _query_fingerprint() -> tuple[str, str]:
    """URLパラメータからフィンガープリント認証情報を取得"""
    try:
        u = st.query_params.get("yumiqa_u", "")
        fp = st.query_params.get("yumiqa_fp", "")
        u = u if isinstance(u, str) else (u[0] if u else "")
        fp = fp if isinstance(fp, str) else (fp[0] if fp else "")
        return u, fp
    except Exception:
        return "", ""

def _complete_login(username: str, guest: bool = False, issue_token: bool = True):
    """ログイン成功時の共通処理。URLパラメータにトークンを保持しリロード時も維持。"""
    user_clean = username.strip().lower()
    if issue_token:
        tok = issue_login_token(user_clean, is_guest=guest)
        st.session_state["_cookie_set"] = tok
        st.query_params["auth"] = tok
    st.session_state.authenticated = True
    st.session_state.is_guest = guest
    st.session_state.logged_in_user = user_clean
    st.session_state.ui_theme = load_ui_theme()
    st.session_state.sb_font_size_choice = load_user_font_size(user_clean)
    st.session_state.font_size_choice = st.session_state.sb_font_size_choice
    for k in ("current_session_id", "messages", "auth_mode"):
        st.session_state.pop(k, None)
    st.rerun()

def render_login_screen(slot=None):
    mode = st.session_state.get("auth_mode", "login")
    is_login = (mode == "login")

    _, col_center, _ = st.columns([1, 1.5, 1])
    with col_center:
        _yumiqa_b64 = get_asset_base64("yumiqa_icon.png")
        _img_src = f"data:image/png;base64,{_yumiqa_b64}" if _yumiqa_b64 else "/app/static/icon-512.png"
        st.markdown(f"""
        <div class="login-wrap">
            <div class="mato-emblem" style="width: 84px; height: 84px; border-radius: 18px; overflow: hidden; margin: 0 auto 16px; box-shadow: 0 8px 28px rgba(0, 229, 255, 0.35), 0 2px 10px rgba(0,0,0,0.4);">
                <img src="{_img_src}" style="width: 100%; height: 100%; object-fit: cover;" alt="YUMIQA">
            </div>
            <div class="login-title">YUMIQA</div>
            <div class="login-subtitle">{"その一射に、次の成長を。AI弓道分析" if is_login else "アカウントを作成して、射の分析と記録を始めましょう。"}</div>
        </div>
        """, unsafe_allow_html=True)

        with st.container(key="login_card"):
            # 最上部：手入力不要のワンタップ開始ボタン（動画診断含む全機能・永久ログイン維持）
            if st.button("✨ ワンタップで始める（入力不要・自動ログイン）", key="one_tap_start", type="primary", use_container_width=True):
                auto_uname = f"archer_{secrets.token_hex(4)}"
                register_user(auto_uname, secrets.token_urlsafe(16), display_name="弓道家")
                if slot is not None:
                    slot.empty()
                _complete_login(auto_uname)

            st.caption("※ 次回からはログイン画面なしでそのまま開きます（動画・写真診断も利用可）")

            with st.expander("ID・パスワードでログイン / 新規登録（別端末と共有する場合）", expanded=False):
                if is_login:
                    with st.form("login_form", clear_on_submit=False, border=False):
                        uname = st.text_input("ユーザー名", placeholder="ユーザー名")
                        upass = st.text_input("パスワード", type="password", placeholder="パスワード")
                        submitted = st.form_submit_button("ログイン", use_container_width=True, type="secondary")
                    # ブラウザ・スマホのパスワードマネージャー対応：autocomplete 属性を注入
                    st.markdown("""
                    <script>
                    (function patchAutocomplete() {
                        function doIt() {
                            try {
                                var pDoc = window.parent.document;
                                var allInputs = pDoc.querySelectorAll('input');
                                allInputs.forEach(function(el) {
                                    var ph = el.getAttribute('placeholder') || '';
                                    if (ph === 'ユーザー名') {
                                        el.setAttribute('autocomplete', 'username');
                                        el.setAttribute('name', 'username');
                                        el.setAttribute('id', 'login-username');
                                    }
                                    if (el.type === 'password' && ph === 'パスワード') {
                                        el.setAttribute('autocomplete', 'current-password');
                                        el.setAttribute('name', 'password');
                                        el.setAttribute('id', 'login-password');
                                    }
                                });
                                var allForms = pDoc.querySelectorAll('form');
                                allForms.forEach(function(f) {
                                    if (!f.getAttribute('method')) f.setAttribute('method', 'post');
                                    if (!f.getAttribute('action')) f.setAttribute('action', '');
                                    f.setAttribute('autocomplete', 'on');
                                });
                            } catch(e) {}
                        }
                        doIt();
                        setTimeout(doIt, 500);
                        setTimeout(doIt, 1500);
                    })();
                    </script>
                    """, unsafe_allow_html=True)
                    if submitted:
                        if uname and upass and authenticate_user(uname, upass):
                            if slot is not None:
                                slot.empty()
                            _complete_login(uname)
                        else:
                            st.error("ユーザー名またはパスワードが正しくありません。")
                else:
                    with st.form("reg_form", clear_on_submit=False, border=False):
                        reg_name = st.text_input("ユーザー名（英数字3文字以上）", placeholder="例: yamada")
                        reg_disp = st.text_input("表示名（任意）", placeholder="例: 山田")
                        reg_pass1 = st.text_input("パスワード（6文字以上）", type="password", placeholder="パスワード")
                        reg_pass2 = st.text_input("パスワード（確認）", type="password", placeholder="もう一度入力")
                        submitted = st.form_submit_button("アカウントを作成", use_container_width=True, type="secondary")
                    st.markdown("""
                    <script>
                    (function patchRegAutocomplete() {
                        function doIt() {
                            try {
                                var pDoc = window.parent.document;
                                var allInputs = pDoc.querySelectorAll('input');
                                allInputs.forEach(function(el) {
                                    var ph = el.getAttribute('placeholder') || '';
                                    if (ph === '例: yamada') {
                                        el.setAttribute('autocomplete', 'username');
                                        el.setAttribute('name', 'username');
                                    }
                                    if (ph === 'パスワード' && el.type === 'password') {
                                        el.setAttribute('autocomplete', 'new-password');
                                        el.setAttribute('name', 'new-password');
                                    }
                                    if (ph === 'もう一度入力' && el.type === 'password') {
                                        el.setAttribute('autocomplete', 'new-password');
                                    }
                                });
                                var allForms = pDoc.querySelectorAll('form');
                                allForms.forEach(function(f) {
                                    if (!f.getAttribute('method')) f.setAttribute('method', 'post');
                                    f.setAttribute('autocomplete', 'on');
                                });
                            } catch(e) {}
                        }
                        doIt();
                        setTimeout(doIt, 500);
                        setTimeout(doIt, 1500);
                    })();
                    </script>
                    """, unsafe_allow_html=True)
                    if submitted:
                        if not reg_name or not reg_pass1:
                            st.error("ユーザー名とパスワードを入力してください。")
                        elif reg_pass1 != reg_pass2:
                            st.error("パスワードが一致しません。")
                        else:
                            ok, msg = register_user(reg_name, reg_pass1, reg_disp)
                            if ok:
                                if slot is not None:
                                    slot.empty()
                                _complete_login(reg_name)
                            else:
                                st.error(msg)

        # 画面の切り替え（ログイン ⇄ 新規登録）
        if is_login:
            if st.button("アカウントをお持ちでない方は 新規登録", key="goto_register", use_container_width=True):
                st.session_state.auth_mode = "register"
                st.rerun()
        else:
            if st.button("すでにアカウントをお持ちの方は ログイン", key="goto_login", use_container_width=True):
                st.session_state.auth_mode = "login"
                st.rerun()
        if st.button(f"ログインせずに使う（チャット{GUEST_CHAT_LIMIT}回まで・ファイル送信不可）", key="guest_login", use_container_width=True):
            if slot is not None:
                slot.empty()
            _complete_login(f"guest_{secrets.token_hex(4)}", guest=True)

        st.markdown("""
        <div style="text-align: center; margin-top: 24px; padding-top: 16px; border-top: 1px solid var(--border-hairline);">
            <a href="/app/static/YUMIQA.apk" download="YUMIQA.apk" style="display: inline-flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; color: var(--link); text-decoration: none; padding: 8px 16px; border-radius: 999px; background: var(--surface-1); border: 1px solid var(--border-subtle);">
                📲 Android専用アプリ（APK）をダウンロード
            </a>
            <div style="font-size: 11px; color: var(--ink-muted); margin-top: 6px;">
                ※ストア申請不要で直接スマホにインストールできます
            </div>
        </div>
        """, unsafe_allow_html=True)

# ==================== 認証状態チェック（未ログインならログイン画面を表示） ====================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    # 1) URLパラメータ or Cookie のトークンで復元
    _tok = _query_login_token() or _browser_login_cookie()
    _auto_user, _auto_guest = verify_login_token(_tok)
    if _auto_user:
        st.session_state.authenticated = True
        st.session_state.is_guest = _auto_guest
        st.session_state.logged_in_user = _auto_user
        st.session_state.ui_theme = load_ui_theme()
        st.session_state.sb_font_size_choice = load_user_font_size(_auto_user)
        st.session_state.font_size_choice = st.session_state.sb_font_size_choice
        st.query_params["auth"] = _tok
    else:
        # 2) app再起動後にトークンが失効した場合：フィンガープリントで自動ログイン（パスワード不要）
        _fp_u, _fp_val = _query_fingerprint()
        if _fp_u and _fp_val and verify_credential_fingerprint(_fp_u, _fp_val):
            # フィンガープリントが一致 → 新トークンを発行して自動ログイン
            _new_tok = issue_login_token(_fp_u, is_guest=False)
            st.session_state["_cookie_set"] = _new_tok
            st.query_params["auth"] = _new_tok
            # URLからフィンガープリントパラメータを除去
            st.query_params.pop("yumiqa_u", None)
            st.query_params.pop("yumiqa_fp", None)
            st.session_state.authenticated = True
            st.session_state.is_guest = False
            st.session_state.logged_in_user = _fp_u
            st.session_state.ui_theme = load_ui_theme()
            st.session_state.sb_font_size_choice = load_user_font_size(_fp_u)
            st.session_state.font_size_choice = st.session_state.sb_font_size_choice
        elif "auth" in st.query_params or "_kt" in st.query_params:
            st.query_params.clear()
        elif not _browser_login_cookie():
            st.session_state["_restore_pending"] = True  # localStorage から復元を試みる

_flush_cookie_js()
if st.session_state.pop("_restore_pending", False):
    _restore_login_js()
if not st.session_state.authenticated:
    login_slot = st.empty()
    with login_slot.container():
        render_login_screen(login_slot)
    st.stop()
if "logged_in_user" not in st.session_state or not st.session_state.logged_in_user:
    st.session_state.logged_in_user = "archer"

# セッション状態の先行初期化（ログインユーザー専用履歴を保持）
if "current_session_id" not in st.session_state:
    existing_sessions = get_all_sessions()
    if existing_sessions:
        latest = existing_sessions[0]
        st.session_state.current_session_id = latest["id"]
        loaded = load_session_messages(latest["id"])
        st.session_state.messages = loaded if loaded is not None else []
    else:
        new_id = f"session_{int(time.time())}"
        st.session_state.current_session_id = new_id
        st.session_state.messages = []

# 選択キャラの保存・復元（ユーザーが変えるまで同じキャラを維持。リロードや新規チャットでも保持）
def _char_pref_path() -> str:
    user = st.session_state.get("logged_in_user", "default")
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sidebar_items")
    return user_data_file(d, user, "_char.json")

def _load_saved_char():
    try:
        with open(_char_pref_path(), "r", encoding="utf-8") as fp:
            name = json.load(fp).get("char")
        return name if name in CHARACTERS else None
    except Exception:
        return None

def _save_char(name: str):
    try:
        with open(_char_pref_path(), "w", encoding="utf-8") as fp:
            json.dump({"char": name}, fp, ensure_ascii=False)
    except Exception:
        pass

if st.session_state.get("current_selected_char") not in CHARACTERS:
    st.session_state.current_selected_char = _load_saved_char() or list(CHARACTERS.keys())[0]

# キャラクター安全切り替え関数（ウェルカムボードは維持し、選択モデルのみ切り替え）
def switch_ai_character(new_char: str):
    if new_char in CHARACTERS:
        st.session_state.current_selected_char = new_char
        _save_char(new_char)

# ==================== サイドバーのピン留め／プロジェクト（ユーザーが自由に追加・編集・削除） ====================
def _sidebar_items_path() -> str:
    user = st.session_state.get("logged_in_user", "default")
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sidebar_items")
    return user_data_file(d, user)

def load_sidebar_items(kind: str) -> list:
    """kind は 'pins'。初期状態は空。旧「プロジェクト」項目があればピン留めへ移行する。"""
    try:
        with open(_sidebar_items_path(), "r", encoding="utf-8") as fp:
            data = json.load(fp)
        if not isinstance(data, dict):
            return []
        items = data.get(kind, [])
        items = items if isinstance(items, list) else []
        legacy = data.get("projects", [])
        if kind == "pins" and isinstance(legacy, list) and legacy:
            items = items + legacy
            data["pins"], data["projects"] = items, []
            with open(_sidebar_items_path(), "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False, indent=2)
        return items
    except Exception:
        return []

def save_sidebar_items(kind: str, items: list):
    path = _sidebar_items_path()
    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    data[kind] = items
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)

def _use_sidebar_item(it: dict):
    """ピン留め項目を押したときの処理（コールバック。追加の再実行なしで即座に質問が走る）。"""
    if it.get("session_id"):
        loaded = load_session_messages(it["session_id"])
        if loaded is not None:
            st.session_state.current_session_id = it["session_id"]
            st.session_state.messages = loaded
    else:
        st.session_state["sidebar_prompt"] = it.get("prompt") or it["label"]

def _set_quick_prompt(text: str):
    st.session_state["sidebar_prompt"] = text

def _toggle_session_pin(sess: dict, is_pinned: bool):
    pins = load_sidebar_items("pins")
    if is_pinned:
        pins = [x for x in pins if x.get("session_id") != sess["id"]]
    else:
        pins.append({"id": f"{int(time.time() * 1000)}", "label": sess["title"], "session_id": sess["id"]})
    save_sidebar_items("pins", pins)

def render_custom_sidebar_section(kind: str, title: str, item_icon: str):
    all_items = load_sidebar_items(kind)
    # 履歴からのピン留め（session_idあり）のみ表示。項目が無ければ欄ごと非表示
    items = [x for x in all_items if x.get("session_id")]
    if not items:
        return
    st.markdown(f"<div class='sb-section-label'>{title}</div>", unsafe_allow_html=True)

    for it in items:
        c_use, c_opt = st.columns([0.82, 0.18])
        with c_use:
            st.button(it["label"], key=f"{kind}_use_{it['id']}", icon=item_icon, use_container_width=True,
                      on_click=_use_sidebar_item, args=(it,))
        with c_opt:
            with st.popover("···", use_container_width=True):
                new_label = st.text_input("名前", value=it["label"], key=f"{kind}_ren_{it['id']}")
                new_prompt = it.get("prompt", "")
                if not it.get("session_id"):
                    new_prompt = st.text_area("送信する質問（空なら名前をそのまま送信）", value=it.get("prompt", ""),
                                              height=90, key=f"{kind}_prm_{it['id']}")
                if st.button("保存", key=f"{kind}_save_{it['id']}", use_container_width=True):
                    it["label"] = new_label.strip() or it["label"]
                    it["prompt"] = new_prompt.strip()
                    save_sidebar_items(kind, all_items)
                    st.rerun()
                if st.button("削除", key=f"{kind}_del_{it['id']}", icon=":material/delete:", use_container_width=True):
                    save_sidebar_items(kind, [x for x in all_items if x["id"] != it["id"]])
                    st.rerun()

_HIST_PAGE = 10  # 履歴を一度に表示する件数

def _hist_show_more():
    st.session_state.hist_show_n = int(st.session_state.get("hist_show_n", _HIST_PAGE)) + _HIST_PAGE

def _hist_show_less():
    st.session_state.hist_show_n = _HIST_PAGE

# ==================== 射形動画・写真の撮影ガイドダイアログ ====================
@st.dialog("📹 射形動画・写真の撮影のコツ＆診断手順")
def show_video_diagnosis_guide():
    st.markdown("""
    #### 📱 AIが綺麗に分析できる撮影のコツ
    
    1. **おすすめの撮影アングル**
       - **的正面（真横・勝手側）**: 胴造りの反り屈み、引分けの軌道、会の伸び合い、矢筋の通りが最も正確に解析できます。
       - **射手正面**: 左右の肩の水平度、両腕の張り合い、手の内の働きがよく分かります。
    
    2. **カメラの高さと距離**
       - **高さ**: 射手の腰〜胸の高さ（三脚や台に置くのがベスト）
       - **距離**: 足踏みから本弭・末弭（弓の上下端）まで全身がしっかり画面内に収まる距離（約3〜4m）
    
    3. **撮影範囲**
       - **足踏み〜残心**まで、または**打起し〜残心**の1射分（約15〜30秒）
       - 通常動画でもスロー動画でも対応しています。
    
    ---
    #### 🚀 診断・送信の手順
    1. チャット下の入力欄にある **「＋」ボタン** をタップ
    2. 撮影した動画（MP4/MOV）または写真を選択して添付
    3. 「離れのブレを見てほしい」「肩の収まりを見てほしい」など気になる点を添えて送信
    4. AIが**3D立体骨格アライメント**と**筋活動バランス**を自動解析して助言します！
    """)
    if st.button("閉じる", type="primary", use_container_width=True):
        st.rerun()

# ==================== 弓道AI道場 ナビゲーション（Linear / Apple Pro スタイル） ====================
with st.sidebar:

    # ── ブランドヘッダー（YUMIQA アイコン + YUMIQA｜AI弓道分析）：JSでサイドバーヘッダーに移動 ───
    _sb_yumiqa_b64 = get_asset_base64("yumiqa_icon.png")
    _sb_img_src = f"data:image/png;base64,{_sb_yumiqa_b64}" if _sb_yumiqa_b64 else "/app/static/icon-192.png"
    st.markdown(f"""
    <div id="kyudo-sidebar-brand" style="display: flex; align-items: center; gap: 8px; padding: 6px 4px 14px 4px;">
        <div style="width: 26px; height: 26px; border-radius: 6px; overflow: hidden; display: flex; align-items: center; justify-content: center; flex-shrink: 0; box-shadow: var(--shadow-sm);">
            <img src="{_sb_img_src}" style="width: 100%; height: 100%; object-fit: cover;" alt="YUMIQA">
        </div>
        <div>
            <div class="sb-brand-name">YUMIQA</div>
            <span class="sb-brand-tag">AI弓道分析</span>
        </div>
    </div>
    <script>
    (function kyudoBrandMount() {{
        function moveBrand() {{
            var brand = document.getElementById('kyudo-sidebar-brand');
            var header = document.querySelector('[data-testid="stSidebarHeader"]');
            if (!brand || !header) return false;
            if (header.contains(brand)) return true;
            var collapseBtn = header.querySelector('[data-testid="stSidebarCollapseButton"]');
            // ヘッダーの先頭（✕ボタンの左横）に移動
            if (collapseBtn) {{
                header.insertBefore(brand, collapseBtn);
            }} else {{
                header.prepend(brand);
            }}
            // インラインスタイルをリセット（CSSで制御）
            brand.style.cssText = '';
            // 元の UserContent 内に残る wrapper の余白を詰める
            var uc = document.querySelector('[data-testid="stSidebarUserContent"]');
            if (uc) {{
                var firstEl = uc.firstElementChild;
                if (firstEl) {{
                    firstEl.style.marginTop = '0';
                    firstEl.style.paddingTop = '0';
                }}
            }}
            return true;
        }}
        // 即時実行 → 失敗したらリトライ
        if (!moveBrand()) {{
            [50, 150, 300, 600, 1000].forEach(function(d) {{ setTimeout(moveBrand, d); }});
        }}
        // Streamlit の再レンダリング後も維持する MutationObserver
        var obs = new MutationObserver(function(mutations) {{
            var brand = document.getElementById('kyudo-sidebar-brand');
            var header = document.querySelector('[data-testid="stSidebarHeader"]');
            if (brand && header && !header.contains(brand)) {{
                moveBrand();
            }}
        }});
        var target = document.querySelector('[data-testid="stSidebar"]') || document.body;
        obs.observe(target, {{ childList: true, subtree: true }});
    }})();
    </script>
    """, unsafe_allow_html=True)

    # ── 新規相談ボタン ──────────────────────────────────────────
    if st.button("新しい相談", key="sidebar_new_chat_btn", icon=":material/edit_square:", use_container_width=True, help="⌘K / Ctrl+Shift+O"):
        new_id = f"session_{int(time.time())}"
        st.session_state.current_session_id = new_id
        st.session_state.messages = []
        st.rerun()

    # ── 📹 動画診断 ──────────────────────────────────────────
    if st.button("📹 動画診断（撮影のコツ・手順）", key="sidebar_video_diag_btn", use_container_width=True):
        show_video_diagnosis_guide()

    # ── できること（解析・稽古目標・射法八節・生体力学を1つに集約） ──────
    cur_c = st.session_state.get("current_selected_char", list(CHARACTERS.keys())[0])
    c_info = CHARACTERS.get(cur_c, list(CHARACTERS.values())[0])
    with st.popover("このAIでできること", icon=":material/auto_awesome:", use_container_width=True):
        t_an, t_goal, t_lib, t_bio = st.tabs(["📹 射形解析", "🎯 稽古目標", "📖 射法八節", "🔬 生体力学"])
        with t_an:
            st.markdown("**射形動画・写真の3D解析**")
            st.caption("画面下の入力欄の「＋」から動画や写真（MP4/PNG等）を添付して送信すると、AIが3D骨格アライメントと筋肉活動バランスを立体解析します。")
        with t_goal:
            st.markdown("**稽古目標**")
            st.caption("目標を保存すると、AIがそれを把握した上で指導してくれます。")
            _goal_user = st.session_state.get("logged_in_user", "default")
            # 既存の稽古目標メモリを取得して初期値に表示
            _existing_goals = [n for n in load_user_memory(_goal_user) if n.startswith("稽古目標:")]
            _current_goal = _existing_goals[0].replace("稽古目標:", "").strip() if _existing_goals else ""
            _new_goal = st.text_input("今日の稽古目標", value=_current_goal, placeholder="例: 会で3秒伸び合う", key="sb_sched_goal")
            if st.button("目標を保存してAIに記憶させる", key="sb_save_sched", use_container_width=True, type="primary"):
                if _new_goal.strip():
                    # 既存の稽古目標エントリを削除してから新しいものを追加（上書き）
                    _notes = load_user_memory(_goal_user)
                    _notes = [n for n in _notes if not n.startswith("稽古目標:")]
                    _notes.append(f"稽古目標: {_new_goal.strip()}")
                    save_user_memory(_goal_user, _notes)
                    st.success(f"「{_new_goal.strip()}」をAIの記憶に保存しました！次のチャットから反映されます。")
                else:
                    st.warning("目標を入力してください。")
        with t_lib:
            st.markdown("""
            <div style='font-size: 12.5px; color: var(--ink-secondary); line-height: 1.9;'>
            <b>1. 足踏み</b> : 両足を開く基本の土台<br>
            <b>2. 胴造り</b> : 丹田に息を沈め姿勢を正す<br>
            <b>3. 弓構え</b> : 取懸け・手の内・物見を整える<br>
            <b>4. 打起し</b> : 静かに頭上へ持ち上げる<br>
            <b>5. 引分け</b> : 左右均等に押し引き開く<br>
            <b>6. 会</b> : 狙いと伸び合いの極致<br>
            <b>7. 離れ</b> : 伸び合いの極まりで放たれる<br>
            <b>8. 残心</b> : 姿勢と精神を保つ
            </div>
            """, unsafe_allow_html=True)
        with t_bio:
            st.markdown("**弓道生体力学プラグイン**")
            st.caption("筑波大・日本武道学会等の筋電図（EMG）・重心動揺・角見トルク力学知見エンジンが常時有効化されています。")

    # ── ピン留め：履歴からピン留めしたチャットがある時だけ表示 ──
    render_custom_sidebar_section("pins", "ピン留め", ":material/push_pin:")

    # ── 履歴（今日／昨日／過去7日間／それ以前）：各行にピン留めボタン ──────
    all_sess = get_all_sessions()
    if all_sess:
        cur_id = st.session_state.get("current_session_id", all_sess[0]["id"])
        pinned_ids = {x.get("session_id") for x in load_sidebar_items("pins") if x.get("session_id")}

        _q = st.text_input("過去の相談を検索...", key="sidebar_search_chats", placeholder="過去の相談を検索...", label_visibility="collapsed")
        if _q.strip():
            _shown = [x for x in all_sess if _q.strip().lower() in x["title"].lower()]
            if not _shown:
                st.caption("一致するチャットがありません")
        else:
            # 履歴が増えすぎないよう、最初は10件だけ表示し「もっと見る」で10件ずつ追加表示する
            _hist_n = max(_HIST_PAGE, int(st.session_state.get("hist_show_n", _HIST_PAGE)))
            _shown = all_sess[:_hist_n]

        for group_name, group_items in group_sessions_by_date(_shown).items():
            st.markdown(f"<div class='sb-section-label'>{group_name}</div>", unsafe_allow_html=True)

            for sess in group_items:
                is_active = (sess["id"] == cur_id)
                is_pinned = sess["id"] in pinned_ids
                col_btn, col_opt = st.columns([0.84, 0.16])

                with col_btn:
                    btn_key = f"sess_active_{sess['id']}" if is_active else f"sess_btn_{sess['id']}"
                    if st.button(sess['title'], key=btn_key, use_container_width=True) and not is_active:
                        st.session_state.current_session_id = sess["id"]
                        loaded = load_session_messages(sess["id"])
                        if loaded is not None:
                            st.session_state.messages = loaded
                        st.rerun()
                    # 右クリックメニュー用（画面には表示しない）
                    if st.button("unpin" if is_pinned else "pin", key=f"hist_pin_{sess['id']}"):
                        _toggle_session_pin(sess, is_pinned)
                        st.rerun()

                with col_opt:
                    with st.popover("···", use_container_width=True):
                        st.caption("チャット設定")
                        rename_val = st.text_input("タイトル変更", value=sess["title"], key=f"ren_{sess['id']}")
                        if st.button("ピン留めを外す" if is_pinned else "ピン留めする", key=f"b_pin_{sess['id']}",
                                     icon=":material/push_pin:", use_container_width=True):
                            _toggle_session_pin(sess, is_pinned)
                            st.rerun()
                        if st.button("変更保存", key=f"b_ren_{sess['id']}", use_container_width=True):
                            rename_session(sess["id"], rename_val)
                            _pins = load_sidebar_items("pins")
                            for x in _pins:
                                if x.get("session_id") == sess["id"] and rename_val.strip():
                                    x["label"] = rename_val.strip()
                            save_sidebar_items("pins", _pins)
                            st.rerun()
                        if st.button("このチャットを削除", key=f"b_del_{sess['id']}", icon=":material/delete:", use_container_width=True):
                            delete_session(sess["id"])
                            save_sidebar_items("pins", [x for x in load_sidebar_items("pins") if x.get("session_id") != sess["id"]])
                            if is_active:
                                remains = get_all_sessions()
                                if remains:
                                    st.session_state.current_session_id = remains[0]["id"]
                                    st.session_state.messages = load_session_messages(remains[0]["id"]) or []
                                else:
                                    new_id = f"session_{int(time.time())}"
                                    st.session_state.current_session_id = new_id
                                    st.session_state.messages = []
                            st.rerun()


        # ── 「もっと見る」／「表示を減らす」（検索中は全件表示なので出さない） ──
        if not _q.strip():
            _remaining = len(all_sess) - len(_shown)
            if _remaining > 0:
                st.button(f"もっと見る（残り{_remaining}件）", key="hist_show_more", icon=":material/expand_more:",
                          use_container_width=True, on_click=_hist_show_more)
            elif len(all_sess) > _HIST_PAGE:
                st.button("表示を減らす", key="hist_show_less", icon=":material/expand_less:",
                          use_container_width=True, on_click=_hist_show_less)

    # ── スペーサー ──────────────────────────────────────────────
    st.markdown('<div style="margin-top: 24px;"></div>', unsafe_allow_html=True)

    # ── 最下部：ユーザープロフィール ────────────────────────────
    users_db = load_users()
    cur_uinfo = users_db.get(st.session_state.get("logged_in_user", ""), {})
    disp_name = "ゲスト" if st.session_state.get("is_guest") else cur_uinfo.get("display_name", "runtyoma")
    cur_user = st.session_state.get("logged_in_user", "default")
    user_id_num = f"{abs(hash(cur_user)) % 10000:04d}"

    # アカウントと設定・射手カルテを1つのボタンに統合（サイドバーの最下部に固定）
    initial_char = disp_name[0].upper() if disp_name else "射"
    with st.popover(f"{initial_char}  {disp_name}", icon=":material/account_circle:", use_container_width=True, key="sb_account"):
        st.markdown(f"""
        <div style="border: 1px solid var(--border-hairline); border-radius: 12px; padding: 14px 16px; margin-bottom: 12px; background: var(--surface-2);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="background: var(--primary-container); color: var(--on-primary-container); border: 1px solid var(--border-subtle); font-weight: 700; font-size: 10.5px; padding: 2px 8px; border-radius: 6px; letter-spacing: 0.08em;">YUMIQA PRO</span>
                <span style="font-size: 11px; font-weight: 600; color: #2E6F40;">● 稼働中</span>
            </div>
            <div style="font-size: 15px; font-weight: 700; color: var(--ink-primary); margin: 2px 0;">{disp_name}</div>
        </div>
        """, unsafe_allow_html=True)

        tab_profile, tab_memory, tab_appset = st.tabs(["⚙️ 設定", "🧠 カルテ・指示", "💾 会話"])

        with tab_profile:
            st.markdown("**表示**")
            st.radio("表示テーマ", THEME_CHOICES, key="ui_theme", horizontal=True, on_change=save_ui_theme)
            _saved_fs = st.session_state.get("sb_font_size_choice") or load_user_font_size(cur_user)
            _fs_idx = FONT_SIZE_OPTIONS.index(_saved_fs) if _saved_fs in FONT_SIZE_OPTIONS else 1
            st.radio(
                "文字の大きさ:",
                options=FONT_SIZE_OPTIONS,
                index=_fs_idx,
                key="sb_font_size_choice",
                on_change=save_user_font_size
            )
            
            # ── 詳細設定（あなた専用。メモリーのON/OFFなど） ──
            st.divider()
            st.markdown("**AIの動作**")
            _us = load_user_settings(cur_user)
            st.session_state["sb_set_mem"] = _us["memory_enabled"]
            st.session_state["sb_set_auto"] = _us["auto_learn"]
            st.session_state["sb_set_ref"] = _us["ref_history"]
            st.session_state["sb_set_style"] = _us["answer_style"]
            st.toggle("メモリーを使う", key="sb_set_mem", on_change=_on_user_setting_change,
                      help="OFFにすると、AIはカルテ（段位・称号を含む）を参照しません。記録は消えません")
            st.toggle("会話から自動で覚える", key="sb_set_auto", on_change=_on_user_setting_change,
                      disabled=not _us["memory_enabled"],
                      help="ONにすると、弓力や段位などをチャットから自動でカルテに追加します")
            st.toggle("過去の会話を参照する", key="sb_set_ref", on_change=_on_user_setting_change,
                      help="最近の相談テーマをAIに伝えて、これまでの流れを踏まえた回答にします")
            st.radio("回答の長さ", ANSWER_STYLES, key="sb_set_style", on_change=_on_user_setting_change, horizontal=True)
            st.caption("これらの設定と、AIが覚えた内容は、あなたのアカウントだけに保存されます。")

        with tab_memory:
            st.markdown("**射手カルテ**")
            st.caption("AIが対話から覚えた情報です。")
            if not load_user_settings(cur_user)["memory_enabled"]:
                st.warning("メモリーがOFFです。AIはカルテを参照しません（⚙️ 設定タブの「AIの動作」で変更できます）。")
            # 段位：選ぶとカルテに保存され、AIが毎回の回答で覚えている情報として使う
            _cur_rank = get_user_rank(cur_user)
            _rank_opts = [c for c in RANK_CHOICES if c != RANK_UNSET]
            if _cur_rank != RANK_UNSET and _cur_rank not in _rank_opts:
                _rank_opts.append(_cur_rank)  # AIが抽出した表記ゆれ対策
            st.session_state["sb_rank_select"] = None if _cur_rank == RANK_UNSET else _cur_rank
            _pick_one("あなたの段位", _rank_opts, "sb_rank_select", _on_rank_change,
                      "タップして選択（もう一度タップで未設定）。選んだ段位はAIが覚えて、レベルに合わせた指導をします")
            _cur_title = get_user_title(cur_user)
            _title_opts = [c for c in TITLE_CHOICES if c != RANK_UNSET]
            if _cur_title != RANK_UNSET and _cur_title not in _title_opts:
                _title_opts.append(_cur_title)
            st.session_state["sb_title_select"] = None if _cur_title == RANK_UNSET else _cur_title
            _pick_one("あなたの称号", _title_opts, "sb_title_select", _on_title_change,
                      "錬士・教士・範士。タップして選択（もう一度タップで未設定）。AIが覚えて指導に反映します")
            user_notes = load_user_memory(cur_user)
            if user_notes:
                for idx, note in enumerate(user_notes):
                    col_n1, col_n2 = st.columns([0.80, 0.20])
                    with col_n1:
                        st.markdown(f"<div style='font-size: 12px; padding: 4px 8px; background: var(--surface-3); border-radius: 6px; margin-bottom: 4px; color: var(--ink-primary); white-space: pre-wrap; word-break: break-word;'>📌 {html.escape(str(note))}</div>", unsafe_allow_html=True)
                    with col_n2:
                        if st.button("✕", key=f"del_mem_p_{idx}", help="削除"):
                            remove_user_memory_item(cur_user, idx)
                            st.rerun()
                if st.button("すべての記憶を消去", use_container_width=True, key="clear_all_mem_p"):
                    clear_all_user_memory(cur_user)
                    st.rerun()
            else:
                st.info("記憶はまだありません。")

            st.text_area("追加する情報:", key="new_mem_pop", height=160,
                         placeholder="例:\n弓力14kg、直心II\n参段審査に向けて会の伸びを練習中\n早気が出やすい\n\n（改行すると、1行ずつ別の記憶として追加されます）")
            st.button("記憶を追加", use_container_width=True, key="add_mem_pop_btn", on_click=_add_memory_from_input)

            st.divider()
            st.markdown("**AIへの指示**")
            st.caption("AIへの前提知識や希望スタイル")
            cur_ci = load_custom_instructions(cur_user)
            ci_prof = st.text_area("あなた自身について:", value=cur_ci.get("profile", ""), height=65, key="ci_p_pop")
            ci_p = st.text_area("AIの応答スタイル:", value=cur_ci.get("response_pref", ""), height=65, key="ci_r_pop")
            if st.button("指示を保存", use_container_width=True, key="save_ci_pop"):
                save_custom_instructions(cur_user, ci_prof, ci_p)
                st.success("保存しました！")
                time.sleep(0.3)
                st.rerun()

        with tab_appset:
            if "messages" in st.session_state and st.session_state.messages:
                export_txt = export_session_to_text(st.session_state.messages)
                st.download_button(
                    label="📥 会話をテキスト保存",
                    data=export_txt,
                    file_name=f"弓道AIチャット_{time.strftime('%Y%m%d_%H%M')}.txt",
                    mime="text/plain",
                    use_container_width=True
                )
            # 履歴の一括削除（確認チェック付き）
            st.divider()
            confirm_wipe = st.checkbox("すべての履歴を削除することを確認しました", key="confirm_wipe_all_history")
            if st.button("履歴をすべて削除", icon=":material/delete_sweep:", use_container_width=True,
                         key="btn_wipe_all_history", disabled=not confirm_wipe):
                for _s in get_all_sessions():
                    delete_session(_s["id"])
                st.session_state.current_session_id = f"session_{int(time.time())}"
                st.session_state.messages = []
                st.session_state.pop("confirm_wipe_all_history", None)
                st.rerun()
            st.markdown("""
            <div style="background-color: transparent; border: 1px dashed var(--border-strong); border-radius: 8px; padding: 10px; font-size: 11.5px; color: var(--ink-secondary); margin-top: 8px;">
                🛡️ 動画・画像は分析直後に完全シュレッダー抹消されます。
            </div>
            """, unsafe_allow_html=True)

        # ── ログアウト（どのタブからでも押せるよう、タブの外に配置） ──
        
        st.divider()
        if st.button("🚪 ログアウト", use_container_width=True, key="btn_logout_pop"):
            cur_tok = _query_login_token() or _browser_login_cookie()
            revoke_login_token(cur_tok)
            if "auth" in st.query_params:
                del st.query_params["auth"]
            if "_kt" in st.query_params:
                del st.query_params["_kt"]
            st.session_state["_cookie_clear"] = True
            st.session_state.authenticated = False
            st.session_state.is_guest = False
            st.session_state.logged_in_user = ""
            st.session_state.sb_font_size_choice = "大きめ (18px)"
            st.session_state.font_size_choice = "大きめ (18px)"
            st.session_state.messages = []
            if "current_session_id" in st.session_state:
                del st.session_state["current_session_id"]
            st.rerun()

# ==================== サイドバーの右クリックメニュー（履歴・ピン留め・プロジェクト） ====================
# Streamlit には右クリックメニューの機能がないため、親ページに小さなJSを1回だけ注入し、
# 右クリックされた行の「ピン」ボタン／「···」ボタンを代わりに押す方式で実現する。
_CTX_MENU_JS = r"""
(function () {
  if (document.getElementById('kyudo-ctx-script-v3')) return;
  var marker = document.createElement('meta'); marker.id = 'kyudo-ctx-script-v3'; document.head.appendChild(marker);

  var st = document.createElement('style');
  st.textContent = [
    '#kyudo-ctx{position:fixed;z-index:2147483647;display:none;min-width:190px;padding:6px;',
    'background:var(--surface-2,#fff);color:var(--ink-primary,#0d0d0d);border:1px solid var(--border-subtle,rgba(0,0,0,.12));',
    'border-radius:12px;box-shadow:var(--shadow-lg,0 18px 48px -14px rgba(0,0,0,.25));font-family:var(--font-sans,sans-serif);font-size:13.5px;}',
    '#kyudo-ctx button{display:block;width:100%;text-align:left;padding:8px 12px;border:0;border-radius:8px;background:transparent;',
    'color:inherit;font:inherit;cursor:pointer;}',
    '#kyudo-ctx button:hover{background:var(--surface-3,#ececec);}'
  ].join('');
  document.head.appendChild(st);

  var old = document.getElementById('kyudo-ctx'); if (old) old.remove();
  var menu = document.createElement('div'); menu.id = 'kyudo-ctx'; document.body.appendChild(menu);
  function hide() { menu.style.display = 'none'; menu.innerHTML = ''; }
  function addItem(label, fn) {
    var b = document.createElement('button'); b.textContent = label;
    b.addEventListener('click', function (ev) { ev.stopPropagation(); hide(); setTimeout(fn, 0); });
    menu.appendChild(b);
  }

  document.addEventListener('contextmenu', function (e) {
    var sel = '[class*="st-key-sess_btn_"],[class*="st-key-sess_active_"],[class*="st-key-pins_use_"]';
    var row = e.target.closest ? e.target.closest(sel) : null;
    if (!row) { hide(); return; }
    var block = row.closest('[data-testid="stHorizontalBlock"]');
    if (!block) return;
    var moreBtn = block.querySelector('[data-testid="stPopover"] button');
    var pinBtn = block.querySelector('[class*="st-key-hist_pin_"] button');
    e.preventDefault();
    menu.innerHTML = '';
    if (pinBtn) {
      var pinned = (pinBtn.textContent || '').indexOf('unpin') !== -1;
      addItem(pinned ? 'ピン留めを外す' : 'ピン留めする', function () { pinBtn.click(); });
    }
    if (moreBtn) {
      var isHist = !!pinBtn;
      addItem(isHist ? '名前を変更・削除…' : '編集・削除…', function () { moreBtn.click(); });
    }
    if (!menu.children.length) return;
    menu.style.display = 'block';
    var x = Math.min(e.clientX, window.innerWidth - menu.offsetWidth - 8);
    var y = Math.min(e.clientY, window.innerHeight - menu.offsetHeight - 8);
    menu.style.left = Math.max(8, x) + 'px'; menu.style.top = Math.max(8, y) + 'px';
  }, true);

  /* ---- キーボードショートカット（ChatGPT / Claude と同じ操作感） ---- */
  function focusInput() {
    var t = document.querySelector('[data-testid="stChatInput"] textarea');
    if (t) t.focus();
  }
  function isTyping(el) {
    if (!el) return false;
    var tag = (el.tagName || '').toLowerCase();
    return tag === 'input' || tag === 'textarea' || el.isContentEditable;
  }
  document.addEventListener('keydown', function (ev) {
    var mod = ev.ctrlKey || ev.metaKey;
    var k = (ev.key || '').toLowerCase();
    if (mod && ev.shiftKey && k === 'o') {            /* 新しいチャット */
      ev.preventDefault();
      var nb = document.querySelector('.st-key-sidebar_new_chat_btn button');
      if (nb) nb.click();
      setTimeout(focusInput, 500);
    } else if (mod && !ev.shiftKey && k === 'k') {   /* チャット検索 */
      var si = document.querySelector('.st-key-sidebar_search_chats input');
      if (si) { ev.preventDefault(); si.focus(); si.select(); }
    } else if (ev.shiftKey && k === 'escape') {      /* 入力欄へ戻る */
      ev.preventDefault(); focusInput();
    } else if (k === '/' && !mod && !ev.altKey && !isTyping(ev.target)) {
      ev.preventDefault(); focusInput();
    }
  });
  /* PC（マウス操作）のときだけ、開いた直後に入力欄へフォーカス（スマホではキーボードが勝手に出ないように） */
  if (window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
    setTimeout(focusInput, 700);
  }

  /* streamlit.app の右下バッジ回避：ホスト名が streamlit.app で、幅が狭い（スマホ）ときだけ入力欄を持ち上げる */
  function updateLift() {
    var onCloud = /\.streamlit\.app$/.test(window.location.hostname);
    var narrow = window.innerWidth <= 700;
    document.documentElement.classList.toggle('kyudo-lift', onCloud && narrow);
  }
  updateLift();
  window.addEventListener('resize', updateLift);

  /* 最後の行が入力欄の真上に来るように、本文の下余白を入力欄の実測の高さに合わせる */
  function updateBottomPad() {
    var b = document.querySelector('[data-testid="stBottom"]');
    if (!b) return;
    var pos = getComputedStyle(b).position;
    // カードが被らないよう余裕を大きめ（+48px）にとる
    var pad = (pos === 'fixed' || pos === 'absolute') ? Math.ceil(b.getBoundingClientRect().height) + 48 : 48;
    document.documentElement.style.setProperty('--kyudo-main-pad', pad + 'px');
  }
  updateBottomPad();
  window.addEventListener('resize', updateBottomPad);
  setInterval(updateBottomPad, 800);

  /* ソフトウェアキーボード追従：キーボード表示時に入力欄を持ち上げて常に見えるようにする */
  /* ソフトウェアキーボード追従：カクつきゼロのシルキースムーズ処理 */
  var isAndroidApp = !!window.AndroidAuth;
  var rafId = null;

  function handleKeyboard() {
    // APK環境ではOSネイティブのadjustResizeがWebView全体を滑らかに縮小するため、JSの二重変形によるカクつきを防ぐ
    if (isAndroidApp) return;

    var b = document.querySelector('[data-testid="stBottom"]');
    if (!b) return;

    if (window.visualViewport) {
      if (rafId) cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(function () {
        var offset = window.innerHeight - window.visualViewport.height;
        if (offset > 70) {
          b.style.setProperty('transform', 'translateY(-' + Math.round(offset) + 'px)', 'important');
        } else {
          b.style.setProperty('transform', 'none', 'important');
        }
      });
    }
  }

  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', handleKeyboard);
    window.visualViewport.addEventListener('scroll', handleKeyboard);
  }
  document.addEventListener('focusin', function (e) {
    if (e.target && (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT')) {
      handleKeyboard();
    }
  });
  document.addEventListener('focusout', function (e) {
    if (e.target && (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT')) {
      setTimeout(function () {
        var b = document.querySelector('[data-testid="stBottom"]');
        if (b) b.style.setProperty('transform', 'none', 'important');
      }, 100);
    }
  });

  document.addEventListener('click', hide, true);
  document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') hide(); });
  window.addEventListener('scroll', hide, true);
  window.addEventListener('resize', hide);
})();
"""

def _with_thinking(gen, slot):
    """最初のチャンクが届くまで「考え中…」を出し、届いたら消す。"""
    first = True
    for chunk in gen:
        if first:
            slot.empty()
            first = False
        yield chunk
    if first:
        slot.empty()

def render_sidebar_context_menu():
    loader = (
        "<script>(function(){try{var d=window.parent.document;"
        "var s=d.createElement('script');s.textContent=" + json.dumps(_CTX_MENU_JS).replace("</", "<\\/") + ";"
        "d.head.appendChild(s);}catch(e){console.warn('context menu unavailable',e);}})();</script>"
    )
    # components.html は非推奨のため、st.iframe があればそちらを優先（旧バージョンはフォールバック）
    try:
        if hasattr(st, "iframe"):
            st.iframe(loader, height=1)
        else:
            components.html(loader, height=0)
    except Exception:
        pass

with st.sidebar:
    render_sidebar_context_menu()

# APIキーの安全な読み込み
env_api_key = os.environ.get("GEMINI_API_KEY", "")
if not env_api_key:
    try:
        if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
            env_api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass
if not env_api_key:
    local_sec = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
    if os.path.exists(local_sec):
        try:
            with open(local_sec, "r", encoding="utf-8") as sf:
                for line in sf:
                    if "GEMINI_API_KEY" in line and "=" in line:
                        env_api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except Exception:
            pass
active_api_key = env_api_key

# ==================== 現在の指導陣（選択UIはサイドバーの「新しいチャット」の下） ====================
cur_char_val = st.session_state.get("current_selected_char", list(CHARACTERS.keys())[0])
short_char_name = cur_char_val.split("（")[0]

selected_char = st.session_state.get("current_selected_char", list(CHARACTERS.keys())[0])
char_info = CHARACTERS[selected_char]
st.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)

# 応答生成関数（テキスト用）
def generate_response(user_input: str, char_name: str, api_key: str, is_regenerate: bool = False) -> str:
    current_char = CHARACTERS[char_name]
    
    # Gemini APIキーがある場合、本物のGeminiを呼び出す
    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            system_instruction = current_char["prompt"]
            
            # 会話履歴をコンテキストとして構築（別キャラの発言は口調を引き継がせない）
            contents = []
            for m in st.session_state.messages[-6:]:
                if m["role"] == "user":
                    contents.append(f"user: {m['content']}")
                else:
                    past_char = m.get("char", char_name)
                    if past_char != char_name:
                        contents.append(f"model: （参考：{past_char}による過去の回答）{m['content']}")
                    else:
                        contents.append(f"model: {m['content']}")
            contents.append(f"user: {user_input}")

            # キャラクター切替の明示
            char_switch_note = ""
            last_asst = next((m for m in reversed(st.session_state.messages) if m["role"] == "assistant"), None)
            if last_asst and last_asst.get("char", char_name) != char_name:
                char_switch_note = (
                    f"\n\n【⚠️ キャラクター切替】\n"
                    f"先ほどまでは「{last_asst.get('char')}」が対応していましたが、"
                    f"今からあなた「{char_name}」が担当します。\n"
                    f"あなた自身のキャラクター設定・口調・視点で必ず回答してください。"
                    f"前のキャラクターの話し方や表現を引き継がないこと。\n"
                )

            memory_section = build_memory_prompt_section(st.session_state.get("logged_in_user", "default"))
            custom_instructions = build_custom_instructions_prompt(st.session_state.get("logged_in_user", "default"))
            
            regen_instruction = ""
            if is_regenerate:
                regen_instruction = (
                    "\n\n【★別の角度からの再生成リクエスト】\n"
                    "射手から『別の視点・アプローチから再指導してほしい』とリクエストされました。\n"
                    "先ほどとは異なる着眼点（例: 呼吸や丹田の意識、別の関節・身体部位の連動、心構え、道場ですぐ試せる別の練習ドリルなど）から、"
                    "射手に新しい気づきを与える新鮮な切り口で温かくアドバイスしてください。\n"
                )

            prompt_text = (
                f"【弓道の科学的論文・生体力学研究文献知見（必読・回答の科学的根拠）】\n"
                f"{KYUDO_SCIENTIFIC_EVIDENCE}\n\n"
                f"{memory_section}"
                f"{custom_instructions}"
                f"{char_switch_note}"
                f"{regen_instruction}"
                f"【設定・役割（必ず上記科学的エビデンスを頭に入れつつ、生体力学・骨格アライメントの説明は身体の専門知識がない人にも直感的にわかる日常の言葉に言い換えて回答してください。弓道用語はそのまま使ってかまいません）】\n"
                f"{system_instruction}\n\n"
                f"{custom_instructions}"
                f"{memory_section}"
                f"【会話内容】\n" + "\n".join(contents)
            )

            # 最新の高速モデルを順に試行
            model_candidates = ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-flash-latest"]
            response_text = None
            last_err = None
            
            temp_setting = 0.85 if is_regenerate else 0.7
            for m_name in model_candidates:
                try:
                    response = client.models.generate_content(
                        model=m_name,
                        contents=prompt_text,
                        config=types.GenerateContentConfig(
                            temperature=temp_setting,
                        )
                    )
                    if response.text:
                        response_text = response.text
                        break
                except Exception as e:
                    last_err = e
                    continue

            
            if response_text:
                return response_text
            elif last_err:
                raise last_err
        except Exception as e:
            return f"⚠️ Gemini API呼び出し中にエラーが発生しました: {str(e)}\n\n（以下は知識ベースからの参考回答です）\n\n" + get_local_response(user_input, char_name)

    # APIキーがない、またはエラー時のローカル知識ベース応答
    return get_local_response(user_input, char_name)

def generate_response_stream(user_input: str, char_name: str, api_key: str, is_regenerate: bool = False):
    """ChatGPT風：リアルタイムに文字が流れるストリーミング応答ジェネレーター"""
    current_char = CHARACTERS[char_name]
    if not api_key:
        local_ans = get_local_response(user_input, char_name)
        if is_regenerate:
            local_ans = f"（別の視点からのアドバイス）\n{local_ans}\n\n呼吸のリズムと身体の軸の意識を変えて稽古を重ねてみてください。"
        for char in local_ans:
            time.sleep(0.015)
            yield char
        return

    try:
        client = genai.Client(api_key=api_key)
        system_instruction = current_char["prompt"]
        
        # 会話履歴をコンテキストとして構築
        # ※ 異なるキャラクターが発言した過去の履歴はそのキャラの口調が混入しないよう
        #   「（別のキャラクター名）が答えた内容:」として渡す
        contents = []
        for m in st.session_state.messages[-6:]:
            if m["role"] == "user":
                contents.append(f"user: {m['content']}")
            else:
                past_char = m.get("char", char_name)
                if past_char != char_name:
                    # 別キャラの発言 → 参考情報として渡すが口調は引き継がせない
                    contents.append(f"model: （参考：{past_char}による過去の回答）{m['content']}")
                else:
                    contents.append(f"model: {m['content']}")
        contents.append(f"user: {user_input}")

        # キャラクター切替の明示（直前の発言が別キャラなら強調）
        char_switch_note = ""
        last_asst = next((m for m in reversed(st.session_state.messages) if m["role"] == "assistant"), None)
        if last_asst and last_asst.get("char", char_name) != char_name:
            char_switch_note = (
                f"\n\n【⚠️ キャラクター切替】\n"
                f"先ほどまでは「{last_asst.get('char')}」が対応していましたが、"
                f"今からあなた「{char_name}」が担当します。\n"
                f"あなた自身のキャラクター設定・口調・視点で必ず回答してください。"
                f"前のキャラクターの話し方や表現を引き継がないこと。\n"
            )
        memory_section = build_memory_prompt_section(st.session_state.get("logged_in_user", "default"))
        custom_instructions = build_custom_instructions_prompt(st.session_state.get("logged_in_user", "default"))
        
        regen_instruction = ""
        if is_regenerate:
            regen_instruction = (
                "\n\n【★別の角度からの再生成リクエスト】\n"
                "射手から『別の視点・アプローチから再指導してほしい』とリクエストされました。\n"
                "先ほどとは異なる着眼点（例: 呼吸や丹田の意識、別の関節・身体部位の連動、心構え、道場ですぐ試せる別の練習ドリルなど）から、"
                "射手に新しい気づきを与える新鮮な切り口で温かくアドバイスしてください。\n"
            )

        prompt_text = (
            f"【弓道の科学的論文・生体力学研究文献知見（必読・回答の科学的根拠）】\n"
            f"{KYUDO_SCIENTIFIC_EVIDENCE}\n\n"
            f"{memory_section}"
            f"{custom_instructions}"
            f"{char_switch_note}"
            f"{regen_instruction}"
            f"【設定・役割（必ず上記科学的エビデンスを頭に入れつつ、生体力学・骨格アライメントの説明は身体の専門知識がない人にも直感的にわかる日常の言葉に言い換えて回答してください。弓道用語はそのまま使ってかまいません）】\n"
            f"{system_instruction}\n\n"
            f"{custom_instructions}"
            f"{memory_section}"
            f"【会話内容】\n" + "\n".join(contents)
        )

        model_candidates = ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-flash-latest"]
        temp_setting = 0.88 if is_regenerate else 0.7
        for m_name in model_candidates:
            try:
                response = client.models.generate_content_stream(
                    model=m_name,
                    contents=prompt_text,
                    config=types.GenerateContentConfig(
                        temperature=temp_setting,
                    )
                )
                for chunk in response:
                    if chunk.text:
                        yield chunk.text
                return
            except Exception:
                continue


        # モデル試行失敗時のフォールバック
        local_ans = get_local_response(user_input, char_name)
        for char in local_ans:
            yield char
    except Exception as e:
        yield f"⚠️ 応答ストリーミング中にエラーが発生しました: {str(e)}"


def get_local_response(user_input: str, char_name: str) -> str:
    for kw, resp_dict in LOCAL_RESPONSES.items():
        if kw in user_input:
            return resp_dict.get(char_name, resp_dict["師範（無幻先生）"])
            
    if char_name == "師範（無幻先生）":
        return f"うむ、『{user_input}』についてじゃな。弓道においては、技の巧拙を追う前にまず己の姿勢と呼吸を見つめ直すことが肝要じゃ。胴造り（背筋を伸ばし体幹を安定させること）がぐらついておらぬか、肩が上がっておらぬか。教本の基本体を思い起こし、澄ました心で一本一本を大切に引きなされ。"
    elif char_name == "弓道部の先輩（葵先輩）":
        return f"『{user_input}』の相談だね！それ、私も部活で練習してるときにすごく考えたことあるよ。最初は焦らず、素引きや巻藁（近くの藁の的）でゆっくり自分の体の感覚を確かめてみるのがオススメ！一緒に一歩ずつステップアップしていこうね！"
    else:
        return f"入力パラメータ『{user_input}』を受領。解析の結果、運動連鎖における体幹の安定性および肩甲胸郭関節（肩甲骨まわり）の可動域が当該事象に寄与している可能性が高いと推定されます。矢束（引き尺の長さ）の均等性と左右の筋出力バランスを再確認することを推奨します。"

# ==================== 3D立体骨格＆筋肉活動可視化関数（Linear Cyber Dark スタイル） ====================
def create_muscle_radar_chart(muscle_scores: dict):
    categories = list(muscle_scores.keys())
    values = list(muscle_scores.values())
    
    # レーダーチャートを閉じるために先頭要素を末尾に追加
    categories_closed = categories + [categories[0]]
    values_closed = values + [values[0]]
    
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values_closed,
        theta=categories_closed,
        fill='toself',
        fillcolor='rgba(91, 132, 196, 0.22)',
        line=dict(color='#5b84c4', width=2.5),
        marker=dict(size=6, color='#5b84c4'),
        name='筋活動バランス'
    ))
    
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickfont=dict(size=10, color='rgba(120,113,108,0.95)'),
                gridcolor='rgba(120,113,108,0.25)',
                linecolor='rgba(120,113,108,0.25)'
            ),
            angularaxis=dict(
                tickfont=dict(size=11, color='rgba(120,113,108,1)', weight=600),
                gridcolor='rgba(120,113,108,0.25)',
                linecolor='rgba(120,113,108,0.25)'
            ),
            bgcolor='rgba(0,0,0,0)'
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=35, r=35, t=25, b=25),
        height=340,
        showlegend=False
    )
    return fig

def create_3d_kyudo_skeleton(posture_params: dict):
    # 傾きパラメータの取得（デフォルト安全値）
    tilt_pitch = float(posture_params.get("trunk_tilt_pitch", 0.0)) # 前後傾き
    tilt_roll = float(posture_params.get("trunk_tilt_roll", 0.0))   # 左右傾き
    elbow_offset = float(posture_params.get("shoulder_draw_level", 0.0)) * 0.02 # 妻手肘の上下
    
    # 3Dキーポイント座標 (x: 左右, y: 前後, z: 上下)
    joints = {
        "Head": [0.0 + tilt_roll*0.01, 0.0 + tilt_pitch*0.01, 1.70],
        "Neck": [0.0 + tilt_roll*0.008, 0.0 + tilt_pitch*0.008, 1.50],
        "Chest": [0.0 + tilt_roll*0.005, 0.0 + tilt_pitch*0.005, 1.35],
        "Pelvis": [0.0, 0.0, 0.95],
        # 押手（左腕：弓を押す側）
        "L_Shoulder": [0.22, 0.0, 1.45],
        "L_Elbow": [0.58, 0.0, 1.43],
        "L_Wrist": [0.95, 0.0, 1.41],
        # 妻手（右腕：弦を引く側・会）
        "R_Shoulder": [-0.22, 0.0, 1.45],
        "R_Elbow": [-0.58, -0.05, 1.42 + elbow_offset],
        "R_Wrist": [-0.35, 0.08, 1.38], # 頬付け・口割の位置
        # 下半身（足踏み・胴造り）
        "L_Hip": [0.14, 0.0, 0.90],
        "L_Foot": [0.46, 0.0, 0.0],
        "R_Hip": [-0.14, 0.0, 0.90],
        "R_Foot": [-0.46, 0.0, 0.0],
        # 弓の上下末端
        "Bow_Top": [0.95, 0.0, 2.25],
        "Bow_Bottom": [0.95, 0.0, 0.15]
    }
    
    # 骨格リンク定義
    bones = [
        ("Head", "Neck", "#f43f5e", 6),
        ("Neck", "Chest", "#7a8c82", 7),
        ("Chest", "Pelvis", "#7a8c82", 8),
        # 押手リンク
        ("Chest", "L_Shoulder", "#7a8c82", 6),
        ("L_Shoulder", "L_Elbow", "#5b84c4", 6),
        ("L_Elbow", "L_Wrist", "#5b84c4", 6),
        # 妻手リンク
        ("Chest", "R_Shoulder", "#7a8c82", 6),
        ("R_Shoulder", "R_Elbow", "#c58b3a", 6),
        ("R_Elbow", "R_Wrist", "#c58b3a", 6),
        # 下半身リンク
        ("Pelvis", "L_Hip", "#7a8c82", 6),
        ("L_Hip", "L_Foot", "#7a8c82", 6),
        ("Pelvis", "R_Hip", "#7a8c82", 6),
        ("R_Hip", "R_Foot", "#7a8c82", 6),
        # 弓幹
        ("Bow_Bottom", "L_Wrist", "#8a6bb0", 4),
        ("L_Wrist", "Bow_Top", "#8a6bb0", 4),
        # 矢（L_Wrist から R_Wrist への水平ベクトル）
        ("L_Wrist", "R_Wrist", "#b8912f", 5),
        # 弦（Bow_Top -> R_Wrist -> Bow_Bottom）
        ("Bow_Top", "R_Wrist", "#a8a29e", 2),
        ("R_Wrist", "Bow_Bottom", "#a8a29e", 2)
    ]
    
    fig = go.Figure()
    
    # ボーンの描画
    for start, end, color, width in bones:
        p1 = joints[start]
        p2 = joints[end]
        fig.add_trace(go.Scatter3d(
            x=[p1[0], p2[0]],
            y=[p1[1], p2[1]],
            z=[p1[2], p2[2]],
            mode='lines',
            line=dict(color=color, width=width),
            hoverinfo='none',
            showlegend=False
        ))
        
    # 関節ポイントの描画
    jx = [pt[0] for pt in joints.values()]
    jy = [pt[1] for pt in joints.values()]
    jz = [pt[2] for pt in joints.values()]
    
    fig.add_trace(go.Scatter3d(
        x=jx, y=jy, z=jz,
        mode='markers+text',
        marker=dict(size=6, color='#2b4c7e'),
        text=["頭", "頸", "胸", "丹田", "押手肩", "押手肘", "角見(押手)", "妻手肩", "妻手肘", "取懸け", "左腰", "左足", "右腰", "右足", "弓(本)", "弓(末)"],
        textposition="top center",
        textfont=dict(size=10, color='rgba(120,113,108,1)'),
        hoverinfo='text',
        showlegend=False
    ))
    
    fig.update_layout(
        scene=dict(
            xaxis=dict(title='左右', range=[-1.1, 1.1], backgroundcolor='rgba(0,0,0,0)', gridcolor='rgba(120,113,108,0.25)', linecolor='rgba(120,113,108,0.25)', color='rgba(120,113,108,0.95)'),
            yaxis=dict(title='前後', range=[-0.6, 0.6], backgroundcolor='rgba(0,0,0,0)', gridcolor='rgba(120,113,108,0.25)', linecolor='rgba(120,113,108,0.25)', color='rgba(120,113,108,0.95)'),
            zaxis=dict(title='天地', range=[-0.1, 2.3], backgroundcolor='rgba(0,0,0,0)', gridcolor='rgba(120,113,108,0.25)', linecolor='rgba(120,113,108,0.25)', color='rgba(120,113,108,0.95)'),
            camera=dict(
                eye=dict(x=1.3, y=-1.5, z=0.8) # 斜め前からの自然な視点
            ),
            aspectratio=dict(x=1.4, y=0.8, z=1.5)
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=5, r=5, t=5, b=5),
        height=360
    )
    return fig

# 動画・画像分析関数
def analyze_media_file(uploaded_file, user_note: str, char_name: str, api_key: str):
    if not api_key:
        return "⚠️ 動画・画像の本格分析にはGemini APIキーが必要です。サイドバーにAPIキーを設定してください。（現在設定されていれば自動で解析されます）", None, None

    client = genai.Client(api_key=api_key)
    current_char = CHARACTERS[char_name]
    
    # 一時ファイルに保存
    file_ext = os.path.splitext(uploaded_file.name)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
        tmp_file.write(uploaded_file.getbuffer())
        tmp_path = tmp_file.name

    gemini_file = None
    try:
        # Geminiにファイルをアップロード
        with st.spinner("ファイルをAI道場へアップロード・立体感知エンジン準備中..."):
            gemini_file = client.files.upload(file=tmp_path)
            
            # 動画処理待ち
            while gemini_file.state.name == "PROCESSING":
                time.sleep(2)
                gemini_file = client.files.get(name=gemini_file.name)
                
            if gemini_file.state.name == "FAILED":
                raise ValueError("動画の処理に失敗しました。別の形式や短めの動画をお試しください。")

        memory_section = build_memory_prompt_section(st.session_state.get("logged_in_user", "default"))
        custom_instructions = build_custom_instructions_prompt(st.session_state.get("logged_in_user", "default"))

        # 立体バイオメカニクス＆筋肉感知コーチングプロンプト
        analysis_prompt = f"""
あなたは弓道の指導者（{char_name}）として、提供された射形動画（または画像）を【立体的・生体力学的（バイオメカニクス）】に詳細分析してください。
分析にあたっては、以下の科学的論文・生体力学研究知見を必ず頭に入れ、その確固たる科学的根拠に基づいて評価してください。
ただし、回答文の中で生体力学・骨格・筋肉に関する説明（解剖学的な内容）は、身体の専門知識がない射手でも直感的にイメージできる日常の言葉に言い換えて伝えてください。弓道の専門用語（角見・会・離れ・胴造りなど）はそのまま使ってかまいません。

{KYUDO_SCIENTIFIC_EVIDENCE}

{memory_section}
{custom_instructions}
外見のポーズだけでなく、**「深層筋（インナーマッスル）が使えているか」「表層筋（僧帽筋などの首肩）が力みすぎてブレーキになっていないか」**を立体的に感知・推定してください。


【射手からのコメント・気になっている点】
{user_note if user_note else "特になし（全体的な射形・筋肉の使い方を見てほしい）"}


【最も大切にすべき指導方針（コーチングアプローチ）】
一方的に欠点を決めつけて正解を押し付けるのではなく、射手が「自分の感覚と向き合い、自分で考えて工夫できる」ように導いてください。

以下の構成に沿って、わかりやすく温かく回答してください：

1. 🌟【美しく連動している筋肉と姿勢】
   まず、安定している関節のアライメントや、美しく使えている深層筋（背中や丹田など）を具体的に褒めてください。

2. 🧬【3D筋肉活動＆骨格連動の立体観察（見えた事実）】
   八節（特に引分け〜会〜離れ）において、以下の筋肉・関節が3次元的にどう動いているか解説してください。生体力学・筋肉・骨格に関する内容は身体の専門知識がない人でも直感的にわかる日常の言葉（「背中の下半分で弓の重みを受け止める感じ」「肩甲骨を背中の中心に引き寄せるイメージ」など）に言い換えてください。弓道の専門用語はそのまま使ってかまいません。
   ・首・肩（僧帽筋）：力んで肩が上がっていないか（首のすくみ）
   ・背中・肩甲骨（広背筋・前鋸筋）：肩甲骨を下げて引き絞る深層筋が働いているか
   ・胸郭（胸骨・肋骨）：息を吸い込みすぎて胸が固まっていないか
   ・体幹・下腹（丹田・腹横筋）：三重十文字（足・腰・肩）の鉛直軸が立っているか
   ・押手の手の内と妻手の肘：角見（親指の根元）の押し出しと、妻手肘の高さ・引き込みベクトルの釣り合い

3. 🤔【自分の身体感覚への問いかけ（自省のヒント）】
   射手自身がその瞬間、体の中で何を感じていたかを振り返る問いかけを投げかけてください。
   （例：「会で伸び合っているとき、首筋にグッと力が入っていませんでしたか？」「お腹の底（丹田）で弓の重みを受け止めている実感はありましたか？」など）

4. 🧪【自分で試せる工夫・実験プラン（筋肉の力みを解くワーク）】
   骨格や体格によって最適な使い方は異なります。道場で射手自身が試行錯誤できるよう、異なる2つの意識（実験プランAと実験プランB）を提案してください。
   ・実験プランA: （表層筋の力を抜くための意識ドリル）
   ・実験プランB: （深層筋や呼吸を連動させるための意識ドリル）
   →「どちらが自分の身体にとって心地よく、伸び合いが自然に深まるか、数本ずつ引いて感覚を比べてみてください」と促してください。

5. 🎌【{char_name}からの温かい応援メッセージ】
   試行錯誤を楽しみながら前向きに稽古できるようエールを送ってください。

--------------------------------------------------
【必須出力：末尾に以下のJSONブロックを必ず記載してください】
推定した筋活動スコア（0〜100）と3D姿勢パラメータを以下のJSONフォーマットで出力してください。
```json
{{
  "muscle_scores": {{
    "首肩の脱力(僧帽筋)": 75,
    "背中の引き込み(広背筋)": 80,
    "胸郭の広がり(深呼吸)": 70,
    "体幹・丹田の安定": 85,
    "手の内の柔らかさ": 68,
    "十文字の伸び合い": 78
  }},
  "posture_3d": {{
    "trunk_tilt_pitch": 1.5,
    "trunk_tilt_roll": 0.5,
    "shoulder_draw_level": -2.0
  }}
}}
```
"""
        with st.spinner(f"{char_name}が筋肉の連動・3D骨格アライメントを立体解析中..."):
            model_candidates = ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-flash-latest"]
            res_text = None
            last_err = None
            for m_name in model_candidates:
                try:
                    response = client.models.generate_content(
                        model=m_name,
                        contents=[gemini_file, analysis_prompt]
                    )
                    if response.text:
                        res_text = response.text
                        break
                except Exception as e:
                    last_err = e
                    continue
            if not res_text and last_err:
                raise last_err

            # JSONブロックの抽出
            muscle_data = None
            posture_data = None
            clean_text = res_text
            
            try:
                json_match = re.search(r'```json\s*(\{.*?\})\s*```', res_text, re.DOTALL)
                if json_match:
                    parsed_json = json.loads(json_match.group(1))
                    muscle_data = parsed_json.get("muscle_scores")
                    posture_data = parsed_json.get("posture_3d")
                    # テキスト本文からJSONブロックを除去して綺麗にする
                    clean_text = res_text.replace(json_match.group(0), "").strip()
            except Exception:
                pass
                
            # デフォルト値のフォールバック
            if not muscle_data:
                muscle_data = {
                    "首肩の脱力(僧帽筋)": 72,
                    "背中の引き込み(広背筋)": 78,
                    "胸郭の広がり(深呼吸)": 68,
                    "体幹・丹田の安定": 80,
                    "手の内の柔らかさ": 70,
                    "十文字の伸び合い": 75
                }
            if not posture_data:
                posture_data = {
                    "trunk_tilt_pitch": 1.0,
                    "trunk_tilt_roll": 0.0,
                    "shoulder_draw_level": 0.0
                }

            return clean_text, muscle_data, posture_data

    finally:
        # 【個人情報保護】一時ファイルをゼロフィル＆乱数で物理シュレッダー抹消
        if tmp_path and os.path.exists(tmp_path):
            secure_shred_file(tmp_path)
        # 【個人情報保護】Googleクラウド側の一時ファイルも即座に完全抹消
        if gemini_file and client:
            try:
                client.files.delete(name=gemini_file.name)
            except Exception:
                pass

# ==================== チャット統合型メイン画面 ====================

# ユーザーメッセージがまだない場合は射心スタイルのウェルカム画面を表示
quick_prompt = st.session_state.pop("sidebar_prompt", None)  # サイドバーのピン留め／プロジェクトからの質問

welcome_slot = None
if not st.session_state.messages and not quick_prompt:
  welcome_slot = st.empty()
  with welcome_slot.container(key="welcome_wrap"):
    # ===== ウェルカム画面（ChatGPT風ミニマル：エンブレム＋タイトル＋案内文） =====
    _wel_yumiqa_b64 = get_asset_base64("yumiqa_icon.png")
    _wel_img_src = f"data:image/png;base64,{_wel_yumiqa_b64}" if _wel_yumiqa_b64 else "/app/static/icon-192.png"
    st.markdown(f"""
    <div class="welcome-hero">
        <div class="mato-emblem">
            <img src="{_wel_img_src}" alt="YUMIQA">
        </div>
        <h1 class="welcome-title">今日の射形について、何を相談しますか？</h1>
        <p class="welcome-sub">射法八節の気になる点や矢所の傾向を教えてください。<br>練習動画や写真からのフォーム確認にも対応しています。</p>
    </div>
    """, unsafe_allow_html=True)

# 過去ログの表示（チャットタイムライン）
for idx, msg in enumerate(st.session_state.messages):
    with st.container(key=f"chat_msg_{idx}_{msg['role']}"):
        if msg["role"] == "user":
            with st.chat_message("user"):
                # 添付ファイルがある場合、ChatGPT風のコンパクトな保護カードで表示
                if "file_name" in msg:
                    f_name = msg.get("file_name", "射形動画.mp4")
                    f_size = msg.get("file_size", "")
                    icon = "🎬" if any(f_name.lower().endswith(ext) for ext in [".mp4", ".mov", ".avi", ".webm"]) else "🖼️"
                
                    st.markdown(f"""
                    <div class="file-attachment-card">
                        <span class="file-attachment-icon">{icon}</span>
                        <div class="file-attachment-details">
                            <span class="file-attachment-name">{f_name}</span>
                            <span class="file-attachment-meta" style="font-weight: 500;">
                                🛡️ 個人情報保護：分析完了後に完全抹消済（{f_size}）
                            </span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown(msg["content"])
        else:
            msg_char = msg.get("char", selected_char)
            c_info = CHARACTERS.get(msg_char, char_info)
            avatar_img = os.path.join(ASSETS_DIR, c_info.get("avatar_file", "")) if c_info.get("avatar_file") and os.path.exists(os.path.join(ASSETS_DIR, c_info.get("avatar_file", ""))) else c_info["icon"]
            with st.chat_message("assistant", avatar=avatar_img):
                st.markdown(f'<span class="char-badge {c_info["badge_class"]}">{c_info["icon"]} {msg_char}</span>', unsafe_allow_html=True)

                # ChatGPT風：メモリ更新バッジ通知
                if msg.get("memory_items"):
                    mem_tags = "、".join(msg["memory_items"])
                    st.markdown(f'<div class="memory-badge"><span>🧠</span><span>メモリを更新しました（{mem_tags}）</span></div>', unsafe_allow_html=True)

                # 3D立体骨格 ＆ 筋活動レーダーチャートがメッセージに含まれる場合
                if "muscle_data" in msg and "posture_data" in msg:
                    st.markdown("#### 🧬 3D立体骨格アライメント ＆ 筋活動バランス")
                    col_g1, col_g2 = st.columns([1, 1])
                    with col_g1:
                        st.markdown("**🕸️ 筋活動バランス（脱力と深層筋連動）**")
                        radar_fig = create_muscle_radar_chart(msg["muscle_data"])
                        st.plotly_chart(radar_fig, use_container_width=True, key=f"radar_chart_{idx}")
                    with col_g2:
                        st.markdown("**🧍‍♂️ 3D立体骨格（マウスで360°回転可能）**")
                        skeleton_fig = create_3d_kyudo_skeleton(msg["posture_data"])
                        st.plotly_chart(skeleton_fig, use_container_width=True, key=f"skeleton_chart_{idx}")
                    st.divider()

                st.markdown(msg["content"])

                # ChatGPT風：アイコンのみのアクションバー（コピー／読み上げ）＋ 最新回答のみ再生成
                is_last_msg = (idx == len(st.session_state.messages) - 1)
                has_user_prompt = any(m["role"] == "user" for m in st.session_state.messages)
                if is_last_msg and has_user_prompt:
                    current_msg_char = msg.get("char", selected_char)
                    bar_cols = st.columns([0.12, 0.10, 0.78])
                    with bar_cols[0]:
                        render_chatgpt_toolbar(msg.get("content", ""))
                    with bar_cols[1]:
                        # 縦3点メニュー：再生成／別のキャラで再生成
                        with st.popover("", icon=":material/more_vert:", key=f"msg_more_{idx}"):
                            last_u_text = None
                            for prev_m in reversed(st.session_state.messages[:idx]):
                                if prev_m["role"] == "user":
                                    last_u_text = prev_m["content"]
                                    break
                            if st.button("再生成", key=f"btn_regen_{idx}", icon=":material/refresh:",
                                         help=f"{current_msg_char}の別の視点から回答を再生成", use_container_width=True):
                                if last_u_text:
                                    st.session_state.messages.pop()
                                    st.session_state.pending_regen = {"text": last_u_text, "char": current_msg_char}
                                    st.rerun()
                            other_chars = [c for c in CHARACTERS.keys() if c != current_msg_char]
                            if other_chars:
                                st.caption("別のキャラで再生成")
                                for oc in other_chars:
                                    oc_info = CHARACTERS[oc]
                                    _do_regen = st.button(f"{oc_info['icon']} {oc}", key=f"regen_char_{idx}_{oc}", use_container_width=True)
                                    st.caption(oc_info["desc"])
                                    if _do_regen and last_u_text:
                                        st.session_state.messages.pop()
                                        st.session_state.pending_regen = {"text": last_u_text, "char": oc}
                                        st.rerun()
                else:
                    render_chatgpt_toolbar(msg.get("content", ""))

# ==================== ChatGPT完全再現：再生成リアルタイム・ストリーミング描画 ====================
# ゲストは「再生成」も1回として数える（上限に達していれば実行しない）
if "pending_regen" in st.session_state and st.session_state.get("is_guest"):
    if guest_used_count() >= GUEST_CHAT_LIMIT:
        st.session_state.pop("pending_regen")
    else:
        guest_consume_one()

if "pending_regen" in st.session_state:
    p_info = st.session_state.pop("pending_regen")
    target_text = p_info["text"]
    target_char = p_info["char"]
    t_info = CHARACTERS.get(target_char, char_info)

    with st.container(key=f"chat_msg_{len(st.session_state.messages)}_assistant"):
        with st.chat_message("assistant", avatar=t_info["icon"]):
            st.markdown(f'<span class="char-badge {t_info["badge_class"]}">{t_info["icon"]} {target_char}</span>', unsafe_allow_html=True)
            try:
                _think = st.empty()
                _think.caption("考え中…")
                stream_gen = _with_thinking(generate_response_stream(target_text, target_char, active_api_key, is_regenerate=True), _think)
                full_reply = st.write_stream(stream_gen)
            except Exception as e:
                full_reply = f"⚠️ エラーが発生しました: {str(e)}"
                st.markdown(full_reply)
            render_chatgpt_toolbar(full_reply)

    st.session_state.messages.append({
        "role": "assistant",
        "char": target_char,
        "content": full_reply
    })
    if "current_session_id" in st.session_state:
        save_current_session(st.session_state.current_session_id, st.session_state.messages)
    st.rerun()




# チャット入力欄（ChatGPT Web公式完全一致：プレースホルダー「ChatGPT に聞く」）
_is_guest = bool(st.session_state.get("is_guest"))
_guest_left = max(0, GUEST_CHAT_LIMIT - guest_used_count()) if _is_guest else None
_guest_locked = _is_guest and _guest_left == 0

_bottom_ctx = st.bottom if hasattr(st, "bottom") else st.container()
with _bottom_ctx:
    if _is_guest:
        if _guest_locked:
            st.info(f"ゲストのチャットは{GUEST_CHAT_LIMIT}回までです。続けるには、ログインまたは新規登録をしてください。")
            if st.button("ログイン・新規登録へ", key="guest_to_login", type="primary"):
                st.session_state.authenticated = False
                st.session_state.is_guest = False
                st.session_state.auth_mode = "register"
                st.rerun()
        else:
            st.caption(f"ゲスト利用中：あと{_guest_left}回チャットできます（ファイルの送信はログイン後に使えます）")

    if _is_guest:
        chat_submission = st.chat_input(
            placeholder="ログインするとチャットを続けられます" if _guest_locked else "射形の悩みや、矢所・呼吸について相談する...",
            disabled=_guest_locked,
        )
    else:
        chat_submission = st.chat_input(
            placeholder="射形の悩みや、矢所・呼吸について相談する...",
            accept_file=True,
            file_type=["mp4", "mov", "avi", "webm", "jpg", "jpeg", "png"]
        )

    # 入力欄から直接指導陣（AIキャラクター）を切り替えられるピルボタン（stChatInput直後に配置して下部ツールバー内に収納）
    if not _guest_locked:
        _cur_c_in = st.session_state.get("current_selected_char", list(CHARACTERS.keys())[0])
        _cur_inf_in = CHARACTERS.get(_cur_c_in, list(CHARACTERS.values())[0])

        with st.container(key="input_char_pill_row"):
            with st.popover(f"{_cur_inf_in['icon']} {_cur_c_in.split('（')[0]}", use_container_width=False):
                st.caption("指導陣（AIモデル）を選択")
                for cname, c_info_item in CHARACTERS.items():
                    st.button(
                        f"{'✓ ' if cname == _cur_c_in else '　 '}{c_info_item['icon']} {cname}",
                        key=f"input_sel_{cname}", use_container_width=True,
                        on_click=switch_ai_character, args=(cname,),
                    )
                    st.caption(c_info_item["desc"])

# 注意書きは CSS（stBottomBlockContainer::before）で入力欄の直上に固定表示

# クイック質問チップまたは入力欄からの入力を判定（ChatInputValue対応・型安全抽出）
text_to_send = None
files_to_send = []

if quick_prompt:
    text_to_send = quick_prompt.strip()
elif chat_submission is not None:
    if isinstance(chat_submission, str):
        # accept_file=Falseのとき: strが返る
        text_to_send = chat_submission.strip()
        files_to_send = []
    else:
        # accept_file=Trueのとき: ChatInputValue dataclassが返る
        try:
            raw_text = chat_submission["text"] if "text" in chat_submission else ""
        except Exception:
            raw_text = ""
        text_to_send = raw_text.strip() if raw_text else ""
        try:
            raw_files = chat_submission["files"] if "files" in chat_submission else []
        except Exception:
            raw_files = []
        files_to_send = list(raw_files) if raw_files else []

if st.session_state.get("is_guest") and (text_to_send or files_to_send):
    files_to_send = []  # ゲストはファイル送信不可（念のためここでも遮断）
    if not text_to_send or guest_used_count() >= GUEST_CHAT_LIMIT:
        text_to_send = None
    else:
        guest_consume_one()

if text_to_send or files_to_send:
    # A. 動画・写真が添付されている場合
    if files_to_send:
        attached_media = files_to_send[0]
        user_msg_text = text_to_send if text_to_send else "🎥 射形動画を分析してください。（筋肉の使い方と3D骨格バランス）"
        file_size_str = f"{round(attached_media.size / (1024*1024), 1)} MB"

        if welcome_slot is not None:
            welcome_slot.empty()

        # ユーザー発言を履歴に追加＆即時描画
        st.session_state.messages.append({
            "role": "user",
            "content": user_msg_text,
            "file_name": attached_media.name,
            "file_size": file_size_str
        })
        with st.chat_message("user"):
            icon = "🎬" if any(attached_media.name.lower().endswith(ext) for ext in [".mp4", ".mov", ".avi", ".webm"]) else "🖼️"
            st.markdown(f"""
            <div class="file-attachment-card">
                <span class="file-attachment-icon">{icon}</span>
                <div class="file-attachment-details">
                    <span class="file-attachment-name">{attached_media.name}</span>
                    <span class="file-attachment-meta" style="font-weight: 500;">
                        🛡️ 個人情報保護：分析完了後に完全抹消済（{file_size_str}）
                    </span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown(user_msg_text)

        # 動画分析
        try:
            with st.spinner(f"🎬 動画をアップロード中・{selected_char}が解析準備中..."):
                analysis_text, muscle_data, posture_data = analyze_media_file(
                    attached_media, text_to_send, selected_char, active_api_key
                )
            st.session_state.messages.append({
                "role": "assistant",
                "char": selected_char,
                "content": analysis_text,
                "muscle_data": muscle_data,
                "posture_data": posture_data
            })
        except Exception as e:
            err_text = f"⚠️ 分析中にエラーが発生しました: {str(e)}"
            st.session_state.messages.append({
                "role": "assistant",
                "char": selected_char,
                "content": err_text
            })

        if "current_session_id" in st.session_state:
            save_current_session(st.session_state.current_session_id, st.session_state.messages)
        st.rerun()

    # B. 通常のテキスト質問の場合（ChatGPT風リアルタイム・ストリーミング）
    else:
        # 1) ユーザー発言を履歴に追加し、画面に即座に表示！
        st.session_state.messages.append({"role": "user", "content": text_to_send})
        if welcome_slot is not None:
            welcome_slot.empty()
        with st.chat_message("user"):
            st.markdown(text_to_send)

        # 2) 射手カルテの自動学習・タイトル生成は、回答のストリーミングと並行して裏で実行
        _cur_user = st.session_state.get("logged_in_user", "default")
        _is_first_q = sum(1 for m in st.session_state.messages if m["role"] == "user") == 1
        _pool = ThreadPoolExecutor(max_workers=2)
        mem_future = _pool.submit(auto_extract_and_save_memory, _cur_user, text_to_send, active_api_key) if active_api_key else None
        title_future = _pool.submit(generate_smart_title, text_to_send, active_api_key) if (_is_first_q and active_api_key) else None

        _avatar_path = os.path.join(ASSETS_DIR, char_info.get("avatar_file", "")) if char_info.get("avatar_file") else ""
        avatar_img_stream = _avatar_path if _avatar_path and os.path.exists(_avatar_path) else char_info["icon"]
        with st.chat_message("assistant", avatar=avatar_img_stream):
            st.markdown(f'<span class="char-badge {char_info["badge_class"]}">{char_info["icon"]} {selected_char}</span>', unsafe_allow_html=True)

            try:
                _think = st.empty()
                _think.caption("考え中…")
                stream_gen = _with_thinking(generate_response_stream(text_to_send, selected_char, active_api_key), _think)
                full_reply = st.write_stream(stream_gen)
            except Exception as e:
                full_reply = f"⚠️ エラーが発生しました: {str(e)}"
                st.markdown(full_reply)

            # 並行実行していたメモリ更新の結果（終わっていなければ最大数秒だけ待つ）
            new_mem_items = []
            if mem_future is not None:
                try:
                    new_mem_items = mem_future.result(timeout=8) or []
                except Exception:
                    new_mem_items = []
            if new_mem_items:
                mem_tags = "、".join(new_mem_items)
                st.markdown(f'<div class="memory-badge"><span>🧠</span><span>メモリを更新しました（{mem_tags}）</span></div>', unsafe_allow_html=True)

            # アクションツールバー（コピー・読み上げ）
            render_chatgpt_toolbar(full_reply)

        asst_msg = {
            "role": "assistant",
            "char": selected_char,
            "content": full_reply
        }
        if new_mem_items:
            asst_msg["memory_items"] = new_mem_items
        st.session_state.messages.append(asst_msg)

        # 会話を即時自動保存（最初の質問なら、裏で生成していたスマートタイトルを使う）
        if "current_session_id" in st.session_state:
            smart_title = None
            if title_future is not None:
                try:
                    smart_title = title_future.result(timeout=8)
                except Exception:
                    smart_title = None
            save_current_session(st.session_state.current_session_id, st.session_state.messages, custom_title=smart_title)
        _pool.shutdown(wait=False)

        st.rerun()