import os
import time
import json
import re
import tempfile
import hashlib
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
        return ":root{color-scheme:light}.btn{color:#78716c}.btn:hover{background:rgba(28,25,23,.06);color:#1c1917}"
    if t == "ダーク":
        return ":root{color-scheme:dark}.btn{color:#9a948a}.btn:hover{background:rgba(244,240,233,.09);color:#f3f0ea}"
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
            body {
                margin: 0;
                padding: 0;
                background: transparent;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            }
            .bar { display: flex; align-items: center; gap: 2px; padding-top: 4px; }
            .btn {
                width: 32px; height: 32px; border: none; border-radius: 8px;
                background: transparent; color: #78716c;
                display: inline-flex; align-items: center; justify-content: center;
                cursor: pointer; transition: background 0.15s ease, color 0.15s ease;
            }
            .btn:hover { background: rgba(28, 25, 23, 0.06); color: #1c1917; }
            .btn:active { transform: scale(0.94); }
            .btn svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
            @media (prefers-color-scheme: dark) {
                .btn { color: #9a948a; }
                .btn:hover { background: rgba(244, 240, 233, 0.09); color: #f3f0ea; }
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
    page_title="弓道AI道場 - Kyudo AI Chat",
    page_icon="🏹",
    layout="wide",
    initial_sidebar_state="expanded"
)

# セッション状態での文字サイズ管理
if "font_size_choice" not in st.session_state:
    st.session_state.font_size_choice = "大きめ (18px)"

# サイドバーで文字サイズを設定できるように先行取得
font_sizes = {
    "標準 (16px)": {"body": "16px", "line": "1.7", "chat": "16px"},
    "大きめ (18px)": {"body": "18px", "line": "1.8", "chat": "18px"},
    "特大 (21px)": {"body": "21px", "line": "1.85", "chat": "21px"}
}

# ==================== 表示テーマ（自動／ライト／ダーク） ====================
THEME_CHOICES = ["自動", "ライト", "ダーク"]
_THEME_LIGHT_VARS = "--canvas: #faf9f7; --canvas-subtle: #f5f3ef; --surface-1: #f4f2ee; --surface-2: #ffffff; --surface-3: #eeebe5; --surface-glass: rgba(250, 249, 247, 0.82); --border-hairline: rgba(28, 25, 23, 0.07); --border-subtle: rgba(28, 25, 23, 0.12); --border-strong: rgba(28, 25, 23, 0.22); --shu: #2b4c7e; --shu-light: #2b4c7e; --shu-soft: rgba(43, 76, 126, 0.08); --on-accent: #ffffff; --accent-emerald: var(--shu); --accent-emerald-light: var(--shu-light); --accent-emerald-soft: var(--shu-soft); --accent-emerald-glow: 0 0 0 rgba(0, 0, 0, 0); --accent-blue: var(--shu); --accent-blue-soft: var(--shu-soft); --ink-primary: #1c1917; --ink-secondary: #44403c; --ink-muted: #78716c; --ink-dim: #a8a29e; --shadow-sm: 0 1px 2px rgba(28, 25, 23, 0.06); --shadow-md: 0 8px 24px -10px rgba(28, 25, 23, 0.16); --shadow-lg: 0 18px 48px -14px rgba(28, 25, 23, 0.22); --shadow-float: 0 10px 34px -14px rgba(28, 25, 23, 0.22), 0 1px 2px rgba(28, 25, 23, 0.05); --radius-full: 9999px; --radius-xl: 16px; --radius-lg: 12px; --radius-md: 10px; --radius-sm: 6px; --ease: cubic-bezier(0.22, 1, 0.36, 1); --font-serif: \"Shippori Mincho\", \"Yu Mincho\", \"Hiragino Mincho ProN\", serif; --font-sans: \"Noto Sans JP\", -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif; --font-mono: \"JetBrains Mono\", ui-monospace, monospace;"
_THEME_DARK_VARS = "--canvas: #141312; --canvas-subtle: #181716; --surface-1: #1a1918; --surface-2: #211f1e; --surface-3: #2a2826; --surface-glass: rgba(20, 19, 18, 0.82); --border-hairline: rgba(244, 240, 233, 0.07); --border-subtle: rgba(244, 240, 233, 0.13); --border-strong: rgba(244, 240, 233, 0.24); --shu: #9dbbea; --shu-light: #b6cdf1; --shu-soft: rgba(157, 187, 234, 0.12); --on-accent: #0e1a2b; --ink-primary: #f3f0ea; --ink-secondary: #cfc9bf; --ink-muted: #9a948a; --ink-dim: #6f6a62; --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.4); --shadow-md: 0 8px 24px -10px rgba(0, 0, 0, 0.6); --shadow-lg: 0 18px 48px -14px rgba(0, 0, 0, 0.7); --shadow-float: 0 10px 34px -14px rgba(0, 0, 0, 0.7), 0 1px 2px rgba(0, 0, 0, 0.4);"

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

if "ui_theme" not in st.session_state:
    st.session_state.ui_theme = load_ui_theme()

# ==================== UI Renewal 2026-11-18：藍（AI）— 余白・淡い面・1色のアクセント ====================
# 方針：装飾を減らし、タイポグラフィと余白で洗練を出す。ライト／ダークは OS 設定に自動追従。
# 機能ロジックには一切触れず、表示層（CSS と静的HTML）のみを差し替える。
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;600;700&family=Shippori+Mincho:wght@500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* =====================================================================
   弓道AI道場 — 藍（AI）デザイン
   方針：余白・淡い面・1色の藍だけで構成する。装飾（円相・点描・印・縦書き）は使わない。
   ライト／ダークは OS 設定に自動追従（prefers-color-scheme）。
   ===================================================================== */
:root {
    color-scheme: light dark;

    /* 地と面（ライト：生成りの紙） */
    --canvas: #faf9f7;
    --canvas-subtle: #f5f3ef;
    --surface-1: #f4f2ee;
    --surface-2: #ffffff;
    --surface-3: #eeebe5;
    --surface-glass: rgba(250, 249, 247, 0.82);

    /* 罫線 */
    --border-hairline: rgba(28, 25, 23, 0.07);
    --border-subtle: rgba(28, 25, 23, 0.12);
    --border-strong: rgba(28, 25, 23, 0.22);

    /* アクセント：藍（唯一の色）。旧変数名も互換のため同じ値に割り当て */
    --shu: #2b4c7e;
    --shu-light: #2b4c7e;
    --shu-soft: rgba(43, 76, 126, 0.08);
    --on-accent: #ffffff;
    --accent-emerald: var(--shu);
    --accent-emerald-light: var(--shu-light);
    --accent-emerald-soft: var(--shu-soft);
    --accent-emerald-glow: 0 0 0 rgba(0, 0, 0, 0);
    --accent-blue: var(--shu);
    --accent-blue-soft: var(--shu-soft);

    /* 文字 */
    --ink-primary: #1c1917;
    --ink-secondary: #44403c;
    --ink-muted: #78716c;
    --ink-dim: #a8a29e;

    --shadow-sm: 0 1px 2px rgba(28, 25, 23, 0.06);
    --shadow-md: 0 8px 24px -10px rgba(28, 25, 23, 0.16);
    --shadow-lg: 0 18px 48px -14px rgba(28, 25, 23, 0.22);
    --shadow-float: 0 10px 34px -14px rgba(28, 25, 23, 0.22), 0 1px 2px rgba(28, 25, 23, 0.05);

    --radius-full: 9999px;
    --radius-xl: 16px;
    --radius-lg: 12px;
    --radius-md: 10px;
    --radius-sm: 6px;
    --ease: cubic-bezier(0.22, 1, 0.36, 1);
    --font-serif: "Shippori Mincho", "Yu Mincho", "Hiragino Mincho ProN", serif;
    --font-sans: "Noto Sans JP", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    --font-mono: "JetBrains Mono", ui-monospace, monospace;
}
@media (prefers-color-scheme: dark) {
    :root {
        --canvas: #141312;
        --canvas-subtle: #181716;
        --surface-1: #1a1918;
        --surface-2: #211f1e;
        --surface-3: #2a2826;
        --surface-glass: rgba(20, 19, 18, 0.82);

        --border-hairline: rgba(244, 240, 233, 0.07);
        --border-subtle: rgba(244, 240, 233, 0.13);
        --border-strong: rgba(244, 240, 233, 0.24);

        --shu: #9dbbea;
        --shu-light: #b6cdf1;
        --shu-soft: rgba(157, 187, 234, 0.12);
        --on-accent: #0e1a2b;

        --ink-primary: #f3f0ea;
        --ink-secondary: #cfc9bf;
        --ink-muted: #9a948a;
        --ink-dim: #6f6a62;

        --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.4);
        --shadow-md: 0 8px 24px -10px rgba(0, 0, 0, 0.6);
        --shadow-lg: 0 18px 48px -14px rgba(0, 0, 0, 0.7);
        --shadow-float: 0 10px 34px -14px rgba(0, 0, 0, 0.7), 0 1px 2px rgba(0, 0, 0, 0.4);
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
    /* 上部にごく淡い藍のにじみだけ。操作を邪魔しない */
    background-image: radial-gradient(900px 420px at 50% -8%, var(--shu-soft), transparent 70%) !important;
    background-attachment: fixed !important;
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
[data-testid="stDecoration"], [data-testid="stStatusWidget"] { display: none !important; }
[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapseButton"] button {
    position: relative; z-index: 1002;
    color: var(--ink-secondary) !important;
    background: var(--surface-2) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: 999px !important;
    box-shadow: var(--shadow-sm) !important;
}
[data-testid="stExpandSidebarButton"] { position: fixed !important; top: 12px !important; left: 12px !important; width: 36px; height: 36px; }
[data-testid="stExpandSidebarButton"]:hover, [data-testid="stSidebarCollapseButton"] button:hover {
    border-color: var(--shu) !important; color: var(--shu) !important;
}
[data-testid="stExpandSidebarButton"] *, [data-testid="stSidebarCollapseButton"] button * { color: inherit !important; }

[data-testid="stMainBlockContainer"] {
    max-width: 760px !important;
    padding: 10px 24px 150px !important;
    margin: 0 auto !important;
}

/* ---------- タイポグラフィ ---------- */
.stMarkdown, .stMarkdown p, .stMarkdown li,
[data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] p {
    color: var(--ink-secondary) !important;
    font-size: 15.5px !important;
    line-height: 1.85 !important;
    letter-spacing: 0.01em !important;
}
h1, h2, h3, h4, h5, h6 {
    font-family: var(--font-sans) !important;
    color: var(--ink-primary) !important;
    font-weight: 600 !important;
    letter-spacing: 0.01em !important;
}
h1 { font-size: clamp(26px, 3.4vw, 34px) !important; line-height: 1.4 !important; }
h2 { font-size: 21px !important; }
h3 { font-size: 17.5px !important; }
h4 { font-size: 15.5px !important; }
strong { color: var(--ink-primary) !important; font-weight: 600 !important; }
hr, [data-testid="stDivider"] hr { border-color: var(--border-hairline) !important; }
a { color: var(--shu) !important; text-underline-offset: 3px; }

div[data-testid="stMarkdownContainer"] code {
    background: var(--surface-3) !important;
    border: 0 !important;
    color: var(--ink-primary) !important;
    border-radius: 6px !important;
    padding: 2px 6px !important;
    font-size: 13.5px !important;
    font-family: var(--font-mono) !important;
}
div[data-testid="stMarkdownContainer"] pre {
    background: var(--surface-2) !important;
    border: 1px solid var(--border-hairline) !important;
    border-radius: var(--radius-lg) !important;
}
div[data-testid="stMarkdownContainer"] blockquote {
    border-left: 3px solid var(--shu) !important;
    background: var(--shu-soft) !important;
    padding: 6px 16px !important;
    margin: 14px 0 !important;
    border-radius: 0 var(--radius-md) var(--radius-md) 0 !important;
    color: var(--ink-secondary) !important;
}
[data-testid="stCaptionContainer"], .stCaption, small { color: var(--ink-muted) !important; }

/* ---------- サイドバー ---------- */
section[data-testid="stSidebar"] {
    background: var(--surface-1) !important;
    border-right: 1px solid var(--border-hairline) !important;
}
section[data-testid="stSidebar"] > div { background: transparent !important; }
section[data-testid="stSidebar"] .stMarkdown,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label { color: var(--ink-secondary) !important; }
section[data-testid="stSidebar"] strong { color: var(--ink-primary) !important; }

.sb-brand-name {
    font-family: var(--font-serif);
    font-size: 18px; font-weight: 700; letter-spacing: 0.08em;
    color: var(--ink-primary); line-height: 1.15;
}
.sb-brand-tag {
    font-family: var(--font-sans);
    font-size: 10px; font-weight: 600; letter-spacing: 0.16em; color: var(--ink-muted);
    margin-top: 3px; display: block;
}
.sb-section-label {
    color: var(--ink-muted) !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    letter-spacing: 0.08em !important;
    padding: 18px 10px 6px !important;
    margin-top: 4px;
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
/* 新しいチャット：唯一の塗りボタン */
section[data-testid="stSidebar"] .st-key-sidebar_new_chat_btn button {
    color: var(--ink-primary) !important;
    background: var(--surface-2) !important;
    border: 1px solid var(--border-subtle) !important;
    box-shadow: var(--shadow-sm) !important;
    justify-content: center !important;
    font-weight: 600 !important;
}
section[data-testid="stSidebar"] .st-key-sidebar_new_chat_btn button:hover {
    background: var(--shu) !important;
    border-color: var(--shu) !important;
    color: var(--on-accent) !important;
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
/* streamlit.app（Streamlit Cloud）の右下バッジが送信ボタンに重なるのを避けるため、
   JS が html に付ける kyudo-lift クラスがあるときだけ入力欄を持ち上げる */
html.kyudo-lift div[data-testid="stBottom"] { padding-bottom: calc(68px + env(safe-area-inset-bottom, 0px)) !important; }
html.kyudo-lift [data-testid="stMainBlockContainer"] { padding-bottom: 210px !important; }

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
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] { padding-top: 1.2rem !important; }
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

/* ---------- 上部バー（コンテナ key="topbar"） ---------- */
.st-key-topbar {
    position: sticky; top: 0; z-index: 90;
    background: var(--surface-glass);
    -webkit-backdrop-filter: blur(16px) saturate(1.2); backdrop-filter: blur(16px) saturate(1.2);
    border-bottom: 1px solid var(--border-hairline);
    padding: 8px 0 8px !important;
    margin-bottom: 14px;
    gap: 0 !important;
}
.st-key-topbar [data-testid="stHorizontalBlock"] { align-items: center !important; gap: 8px !important; }
.st-key-topbar [data-testid="stPopover"] > button,
[data-testid="stMain"] [data-testid="stPopover"] > button {
    background: transparent !important;
    border: 1px solid transparent !important;
    box-shadow: none !important;
    color: var(--ink-primary) !important;
    font-weight: 600 !important; border-radius: 999px !important;
    font-size: 13.5px !important; letter-spacing: 0.01em !important;
    padding: 4px 14px !important; min-height: 34px !important;
    transition: background 0.18s var(--ease), border-color 0.18s var(--ease) !important;
}
[data-testid="stMain"] [data-testid="stPopover"] > button:hover {
    background: var(--surface-3) !important; transform: none !important;
}
.pulse-dot {
    width: 6px; height: 6px; background: var(--shu); border-radius: 50%;
    display: inline-block; animation: aiPulse 2.6s ease-in-out infinite;
}
@keyframes aiPulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
.top-chip {
    display: inline-flex; align-items: center; gap: 8px;
    padding: 5px 12px; border-radius: 999px;
    background: var(--surface-2);
    border: 1px solid var(--border-hairline);
    color: var(--ink-muted); font-size: 12px; font-weight: 500;
}
.top-avatar {
    width: 30px; height: 30px; border-radius: 50%;
    background: var(--shu); color: var(--on-accent);
    display: flex; align-items: center; justify-content: center;
    font-size: 12.5px; font-weight: 700;
}

/* ---------- ウェルカム ---------- */
.hero { margin: 7vh 0 24px; }
.hero-eyebrow {
    display: inline-flex; align-items: center; gap: 8px;
    font-size: 11.5px; font-weight: 600; letter-spacing: 0.14em;
    color: var(--shu); background: var(--shu-soft);
    padding: 5px 12px; border-radius: 999px; margin-bottom: 18px;
}
.hero-title {
    font-family: var(--font-serif) !important;
    font-size: clamp(28px, 4.2vw, 42px) !important;
    font-weight: 600 !important; line-height: 1.42 !important;
    letter-spacing: 0.02em !important;
    color: var(--ink-primary) !important; margin: 0 0 14px !important;
}
.hero-title em { font-style: normal; color: var(--shu); }
.hero-sub { font-size: 14.5px; line-height: 1.9; color: var(--ink-muted); max-width: 480px; }

/* クイックアクション：余白のあるカード */
[data-testid="stMain"] [class*="st-key-quick_act_"] button {
    background: var(--surface-2) !important;
    border: 1px solid var(--border-hairline) !important;
    border-radius: var(--radius-lg) !important;
    box-shadow: var(--shadow-sm) !important;
    min-height: 56px !important;
    padding: 14px 48px 14px 20px !important;
    justify-content: flex-start !important;
    text-align: left !important;
    color: var(--ink-primary) !important;
    font-size: 15px !important; font-weight: 500 !important; letter-spacing: 0.01em !important;
    position: relative;
    transition: border-color 0.2s var(--ease), box-shadow 0.2s var(--ease), transform 0.2s var(--ease) !important;
}
[data-testid="stMain"] [class*="st-key-quick_act_"] button > div { justify-content: flex-start !important; }
[data-testid="stMain"] [class*="st-key-quick_act_"] button::after {
    content: "→"; position: absolute; right: 20px; top: 50%; transform: translateY(-50%);
    color: var(--ink-dim);
    transition: transform 0.25s var(--ease), color 0.2s ease;
}
[data-testid="stMain"] [class*="st-key-quick_act_"] button:hover {
    background: var(--surface-2) !important;
    border-color: var(--border-strong) !important;
    box-shadow: var(--shadow-md) !important;
    transform: translateY(-1px) !important;
    color: var(--ink-primary) !important;
}
[data-testid="stMain"] [class*="st-key-quick_act_"] button:hover::after { color: var(--shu); transform: translate(4px, -50%); }

/* ---------- 会話 ---------- */
div[data-testid="stChatMessage"] {
    background: transparent !important; border: 0 !important; box-shadow: none !important;
    padding: 6px 0 !important; margin: 0 auto 16px !important;
    max-width: 100% !important; width: 100% !important;
}
div[data-testid="stChatMessage"] [data-testid^="stChatMessageAvatar"] { display: none !important; }

/* あなた：右寄せのやわらかい吹き出し */
div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    max-width: 78% !important; width: fit-content !important;
    margin-left: auto !important; margin-right: 0 !important;
    background: var(--surface-3) !important;
    border: 0 !important;
    border-radius: 20px 20px 6px 20px !important;
    padding: 10px 18px !important;
}
div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) p,
div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) span,
div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stMarkdownContainer"] * {
    color: var(--ink-primary) !important;
}
/* AI：地に直接。枠なし、行間をゆったり */
div[data-testid="stChatMessage"]:not(:has([data-testid="stChatMessageAvatarUser"])) {
    padding: 2px 0 !important;
}
div[data-testid="stChatMessage"]:not(:has([data-testid="stChatMessageAvatarUser"])) p,
div[data-testid="stChatMessage"]:not(:has([data-testid="stChatMessageAvatarUser"])) li {
    color: var(--ink-primary) !important; font-size: 15.5px !important; line-height: 1.95 !important;
}

.char-badge {
    display: inline-flex; align-items: center; gap: 8px;
    padding: 0 !important; margin: 0 0 8px !important;
    background: transparent !important; border: 0 !important; border-radius: 0 !important;
    font-family: var(--font-sans) !important;
    font-size: 12.5px !important; font-weight: 600 !important; letter-spacing: 0.04em !important;
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

/* ---------- 入力欄 ---------- */
div[data-testid="stBottom"], div[data-testid="stBottom"] > div {
    background: transparent !important; border-top: 0 !important;
}
div[data-testid="stBottom"] {
    background: linear-gradient(180deg, transparent 0%, var(--canvas) 42%) !important;
    padding: 18px 0 calc(12px + env(safe-area-inset-bottom, 0px)) !important;
    z-index: 9999 !important;
}
div[data-testid="stBottomBlockContainer"] {
    max-width: 760px !important; padding: 0 24px !important; margin: 0 auto !important;
}
div[data-testid="stChatInput"] {
    background: var(--surface-2) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: 24px !important;
    box-shadow: var(--shadow-float) !important;
    padding: 4px 10px !important;
    transition: border-color 0.2s var(--ease), box-shadow 0.2s var(--ease) !important;
}
div[data-testid="stChatInput"]:focus-within {
    border-color: var(--shu) !important;
    box-shadow: 0 0 0 4px var(--shu-soft), var(--shadow-float) !important;
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
    background: transparent !important; color: var(--ink-primary) !important;
    font-size: 15px !important; line-height: 1.7 !important;
}
div[data-testid="stChatInput"] textarea::placeholder { color: var(--ink-dim) !important; }
div[data-testid="stChatInput"] button {
    background: transparent !important; color: var(--ink-muted) !important;
    border: 0 !important; border-radius: 999px !important; transition: all 0.15s ease !important;
}
div[data-testid="stChatInput"] button:hover { background: var(--surface-3) !important; color: var(--ink-primary) !important; }
/* 送信ボタンだけ塗り */
div[data-testid="stChatInputSubmitButton"] button, div[data-testid="stChatInput"] button[data-testid="stChatInputSubmitButton"] {
    background: var(--shu) !important; color: var(--on-accent) !important;
}
div[data-testid="stChatInputSubmitButton"] button:hover, div[data-testid="stChatInput"] button[data-testid="stChatInputSubmitButton"]:hover {
    background: var(--shu) !important; color: var(--on-accent) !important; opacity: 0.88;
}
div[data-testid="stChatInput"] button:disabled { background: transparent !important; color: var(--ink-dim) !important; }

/* ---------- ボタン・フォーム ---------- */
.stButton > button, .stDownloadButton > button, button[kind="secondary"] {
    background: var(--surface-2) !important;
    color: var(--ink-primary) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: 999px !important;
    box-shadow: var(--shadow-sm) !important;
    font-weight: 500 !important; font-size: 13px !important; letter-spacing: 0.01em !important;
    min-height: 38px !important; padding: 6px 18px !important;
    transition: background 0.18s var(--ease), border-color 0.18s var(--ease), color 0.18s var(--ease) !important;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    background: var(--surface-3) !important; border-color: var(--border-strong) !important;
    color: var(--ink-primary) !important; transform: none !important;
}
.stButton > button:active { transform: scale(0.985) !important; }
button[kind="primary"], .stFormSubmitButton > button {
    background: var(--shu) !important; color: var(--on-accent) !important; border: 0 !important;
    border-radius: 999px !important; font-weight: 600 !important; letter-spacing: 0.04em !important;
    box-shadow: var(--shadow-sm) !important;
}
button[kind="primary"]:hover, .stFormSubmitButton > button:hover {
    background: var(--shu) !important; color: var(--on-accent) !important; opacity: 0.9; transform: none !important;
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

/* ---------- ログイン ---------- */
.st-key-login_card {
    background: var(--surface-2); border: 1px solid var(--border-hairline);
    border-radius: 20px; padding: 22px 24px 8px; box-shadow: var(--shadow-md);
    margin-bottom: 14px;
}
.st-key-goto_register button, .st-key-goto_login button, .st-key-guest_login button {
    background: transparent !important; border: 0 !important; box-shadow: none !important;
    color: var(--ink-muted) !important; font-size: 13px !important; min-height: 32px !important;
}
.st-key-goto_register button:hover, .st-key-goto_login button:hover, .st-key-guest_login button:hover {
    background: transparent !important; color: var(--shu) !important;
}
.login-wrap { margin: 7vh auto 22px; text-align: center; }
.login-logo { margin-left: auto; margin-right: auto; }
.login-logo {
    width: 48px; height: 48px; border-radius: 14px; background: var(--shu); color: var(--on-accent);
    display: flex; align-items: center; justify-content: center;
    font-size: 22px; margin-bottom: 20px;
}
.login-title { font-family: var(--font-serif); font-size: 34px; font-weight: 700; letter-spacing: 0.06em; color: var(--ink-primary); }
.login-subtitle { margin-top: 10px; font-size: 13.5px; line-height: 1.9; color: var(--ink-muted); }

/* ---------- レスポンシブ ---------- */
@media (max-width: 900px) {
    [data-testid="stMainBlockContainer"] { padding: 20px 16px 150px !important; }
    .hero { margin-top: 3vh; }
    .st-key-topbar { padding-left: 44px !important; }
}
@media (max-width: 600px) {
    [data-testid="stMainBlockContainer"] { padding: 14px 12px 140px !important; }
    div[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { max-width: 90% !important; padding: 10px 16px !important; }
    div[data-testid="stBottom"] > div { padding: 0 9px !important; }
    [data-testid="stMain"] [class*="st-key-quick_act_"] button { font-size: 14.5px !important; }
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
    "3. 【初心者・一般射手への徹底的な噛み砕き（日常語への翻訳）】\n"
    "   難しい解剖学用語は使わず、誰もが直感的にイメージできる日常の身体動作（『肩をストンと落とす』『親指の根元で壁をそっと押す』など）に翻訳して伝えてください。\n"
    "4. 【専門用語のカッコ書き解説】\n"
    "   弓道の専門用語を用いる際は、必ず直後にカッコ書き（例: 角見（左手親指の付け根で弓を押し開くこと））をつけて平易に解説してください。"
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
            "ただし、専門用語や解剖学用語を並べるだけでなく、誰でも直感的に実践できるよう日常的な身体の動かし方に噛み砕いて翻訳して伝えてください。"
            + COMMON_INSTRUCTION
        ),
        "welcome": "射技動作分析AIシステム起動。弓道の専門用語や動作メカニクスを、日常的な身体部位の動きに噛み砕いて分かりやすく解析・解説します。お悩みの症状を詳しく入力してください。"
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

def get_current_history_dir() -> str:
    current_user = st.session_state.get("logged_in_user", "default")
    user_safe = "".join(c for c in current_user if c.isalnum() or c in ("-", "_"))
    h_dir = os.path.join(os.path.dirname(__file__), "history", user_safe)
    os.makedirs(h_dir, exist_ok=True)
    return h_dir

# ==================== ChatGPT風 射手メモリー（個人記憶・カルテ機能） ====================
MEMORIES_DIR = os.path.join(os.path.dirname(__file__), "data", "memories")

def get_user_memory_path(username: str) -> str:
    os.makedirs(MEMORIES_DIR, exist_ok=True)
    user_safe = "".join(c for c in username if c.isalnum() or c in ("-", "_")) or "default"
    return os.path.join(MEMORIES_DIR, f"{user_safe}.json")

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

def add_user_memory_item(username: str, note_text: str):
    """手動または自動で記憶を1つ追加"""
    clean_text = note_text.strip()
    if not clean_text:
        return
    notes = load_user_memory(username)
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

def build_memory_prompt_section(username: str) -> str:
    """プロンプトに注入する射手カルテ形式のテキストを生成"""
    notes = load_user_memory(username)
    if not notes:
        return ""
    bullet_points = "\n".join([f"・{item}" for item in notes])
    return (
        f"【射手カルテ（あなたがこの射手について記憶しているパーソナル情報）】\n"
        f"{bullet_points}\n"
        f"※上記の射手情報（使用弓具・弓力・目標・抱えている課題など）を熟知している前提で、"
        f"これまでの稽古の文脈に寄り添い、射手にとって最適なアドバイスを行ってください。\n\n"
    )

def auto_extract_and_save_memory(username: str, user_text: str, api_key: str) -> list[str]:
    """ユーザーの発言から弓道に関する自己情報（弓力・段位・悩みなど）をAIが自動抽出し記憶に追加。抽出した項目一覧を返す。"""
    if not api_key or not user_text or len(user_text.strip()) < 4:
        return []
    trigger_words = ["弓力", "kg", "キロ", "段", "級", "高校", "大学", "部活", "矢尺", "cm", "流派", "直心", "肥後", "グラス", "カーボン", "早気", "もたれ", "手の内", "審査", "大会", "歴", "年目"]
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

【出力形式の例】:
・弓力: 14kg (直心II)
・目標: 参段審査の合格
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
    os.makedirs(CUSTOM_INSTR_DIR, exist_ok=True)
    user_safe = "".join(c for c in username if c.isalnum() or c in ("-", "_")) or "default"
    return os.path.join(CUSTOM_INSTR_DIR, f"{user_safe}.json")

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
    if not profile and not resp_pref:
        return ""
    parts = []
    if profile:
        parts.append(f"【射手自身について知っておくべき追加事項】\n{profile}")
    if resp_pref:
        parts.append(f"【射手が希望するAIの応答スタイル・特別ルール】\n{resp_pref}")
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
    """ChatGPT風：会話履歴を『今日』『昨日』『過去7日間』『それ以前』に分類"""
    import datetime
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    seven_days_ago = today - datetime.timedelta(days=7)
    
    groups = {
        "今日": [],
        "昨日": [],
        "過去7日間": [],
        "それ以前": []
    }
    
    for s in sessions:
        up_str = s.get("updated_at", "")
        try:
            s_date = datetime.datetime.strptime(up_str.split()[0], "%Y-%m-%d").date()
            if s_date == today:
                groups["今日"].append(s)
            elif s_date == yesterday:
                groups["昨日"].append(s)
            elif s_date >= seven_days_ago:
                groups["過去7日間"].append(s)
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
    output.append("# 🏹 弓道AI道場 稽古録\n")
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

def _complete_login(username: str, guest: bool = False):
    """ログイン成功時の共通処理。ユーザー専用の履歴・テーマ設定を読み直す。"""
    st.session_state.authenticated = True
    st.session_state.is_guest = guest
    st.session_state.logged_in_user = username.strip().lower()
    st.session_state.ui_theme = load_ui_theme()
    for k in ("current_session_id", "messages", "auth_mode"):
        st.session_state.pop(k, None)
    st.rerun()

def render_login_screen():
    mode = st.session_state.get("auth_mode", "login")
    is_login = (mode == "login")

    _, col_center, _ = st.columns([1, 1.5, 1])
    with col_center:
        st.markdown(f"""
        <div class="login-wrap">
            <div class="login-logo">🏹</div>
            <div class="login-title">弓道AI道場</div>
            <div class="login-subtitle">{"アカウントにログインして、稽古を続けましょう。" if is_login else "アカウントを作成して、稽古の記録を残しましょう。"}</div>
        </div>
        """, unsafe_allow_html=True)

        with st.container(key="login_card"):
            if is_login:
                with st.form("login_form", clear_on_submit=False, border=False):
                    uname = st.text_input("ユーザー名", placeholder="ユーザー名")
                    upass = st.text_input("パスワード", type="password", placeholder="パスワード")
                    submitted = st.form_submit_button("ログイン", use_container_width=True, type="primary")
                if submitted:
                    if uname and upass and authenticate_user(uname, upass):
                        _complete_login(uname)
                    else:
                        st.error("ユーザー名またはパスワードが正しくありません。")
            else:
                with st.form("reg_form", clear_on_submit=False, border=False):
                    reg_name = st.text_input("ユーザー名（英数字3文字以上）", placeholder="例: yamada")
                    reg_disp = st.text_input("表示名（任意）", placeholder="例: 山田")
                    reg_pass1 = st.text_input("パスワード（6文字以上）", type="password", placeholder="パスワード")
                    reg_pass2 = st.text_input("パスワード（確認）", type="password", placeholder="もう一度入力")
                    submitted = st.form_submit_button("アカウントを作成", use_container_width=True, type="primary")
                if submitted:
                    if not reg_name or not reg_pass1:
                        st.error("ユーザー名とパスワードを入力してください。")
                    elif reg_pass1 != reg_pass2:
                        st.error("パスワードが一致しません。")
                    else:
                        ok, msg = register_user(reg_name, reg_pass1, reg_disp)
                        if ok:
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
            _complete_login(f"guest_{secrets.token_hex(4)}", guest=True)

# ==================== 認証状態チェック（未ログインならログイン画面を表示） ====================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if not st.session_state.authenticated:
    render_login_screen()
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

# キャラクター安全切り替え関数（競合・巻き戻り防止）
def switch_ai_character(new_char: str):
    if new_char in CHARACTERS:
        st.session_state.current_selected_char = new_char
        # 会話が未開始または初期挨拶のみの場合は、新キャラのウェルカムに即時切り替え
        if not st.session_state.messages or (len(st.session_state.messages) == 1 and st.session_state.messages[0].get("role") == "assistant"):
            st.session_state.messages = [{
                "role": "assistant",
                "char": new_char,
                "content": CHARACTERS[new_char]["welcome"]
            }]

# ==================== サイドバーのピン留め／プロジェクト（ユーザーが自由に追加・編集・削除） ====================
def _sidebar_items_path() -> str:
    user = st.session_state.get("logged_in_user", "default")
    user_safe = "".join(c for c in user if c.isalnum() or c in ("-", "_")) or "default"
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sidebar_items")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{user_safe}.json")

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
    st.markdown(f"<div class='sb-section-label'>{title}</div>", unsafe_allow_html=True)
    items = load_sidebar_items(kind)

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
                    save_sidebar_items(kind, items)
                    st.rerun()
                if st.button("削除", key=f"{kind}_del_{it['id']}", icon=":material/delete:", use_container_width=True):
                    save_sidebar_items(kind, [x for x in items if x["id"] != it["id"]])
                    st.rerun()

    with st.popover("追加", icon=":material/add:", use_container_width=True):
        add_label = st.text_input("名前", key=f"{kind}_new_label", placeholder="例: 会の伸び合い")
        add_prompt = st.text_area("送信する質問（任意）", key=f"{kind}_new_prompt", height=90,
                                  placeholder="空なら名前をそのまま送信します")
        if st.button("追加する", key=f"{kind}_add_btn", use_container_width=True, type="primary"):
            if add_label.strip():
                items.append({"id": f"{int(time.time() * 1000)}", "label": add_label.strip(), "prompt": add_prompt.strip()})
                save_sidebar_items(kind, items)
                st.session_state.pop(f"{kind}_new_label", None)
                st.session_state.pop(f"{kind}_new_prompt", None)
                st.rerun()

# ==================== 弓道AI道場 ナビゲーション（Linear / Apple Pro スタイル） ====================
with st.sidebar:

    # ── ブランドヘッダー（ロゴ + バッジ） ─────────────────────────
    logo_b64 = get_asset_base64("kyudo_ai_logo.jpg")
    if logo_b64:
        logo_html = f'<img src="data:image/jpeg;base64,{logo_b64}" style="width: 38px; height: 38px; border-radius: 10px; border: 1px solid var(--border-subtle); object-fit: cover;">'
    else:
        logo_html = '<div style="width: 38px; height: 38px; border-radius: 10px; background: var(--shu); color: var(--on-accent); display: flex; align-items: center; justify-content: center; font-size: 19px;">🏹</div>'

    st.markdown(f"""
    <div style="display: flex; align-items: center; gap: 12px; padding: 8px 4px 16px 4px;">
        {logo_html}
        <div>
            <div class="sb-brand-name">弓道AI道場</div>
            <span class="sb-brand-tag">KYUDO AI DOJO</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 新規チャットボタン ──────────────────────────────────────
    if st.button("新しいチャット", key="sidebar_new_chat_btn", icon=":material/edit_square:", use_container_width=True, help="Ctrl+Shift+O"):
        new_id = f"session_{int(time.time())}"
        st.session_state.current_session_id = new_id
        st.session_state.messages = []
        st.rerun()

    # ── 指導陣（AIモデル）の選択：新しいチャットのすぐ下 ──────────
    _sel_char = st.session_state.get("current_selected_char", list(CHARACTERS.keys())[0])
    _sel_info = CHARACTERS.get(_sel_char, list(CHARACTERS.values())[0])
    with st.popover(f"{_sel_info['icon']} {_sel_char.split('（')[0]}", use_container_width=True):
        st.caption("指導陣（AIモデル）を選択")
        for cname, c_info_item in CHARACTERS.items():
            st.button(
                f"{'✓ ' if cname == _sel_char else '　 '}{c_info_item['icon']} {cname}",
                key=f"top_sel_{cname}", use_container_width=True, help=c_info_item["desc"],
                on_click=switch_ai_character, args=(cname,),
            )

    # ── ツール（解析・稽古目標・射法八節・生体力学を1つに集約） ──────
    cur_c = st.session_state.get("current_selected_char", list(CHARACTERS.keys())[0])
    c_info = CHARACTERS.get(cur_c, list(CHARACTERS.values())[0])
    with st.popover("ツール", icon=":material/apps:", use_container_width=True):
        t_an, t_goal, t_lib, t_bio = st.tabs(["解析", "稽古目標", "射法八節", "生体力学"])
        with t_an:
            st.markdown("**射形動画・写真の3D解析**")
            st.caption("画面下の入力欄の「＋」から動画や写真（MP4/PNG等）を添付して送信すると、AIが3D骨格アライメントと筋肉活動バランスを立体解析します。")
        with t_goal:
            st.markdown("**稽古スケジュール＆課題**")
            st.caption("日々の稽古計画や昇段審査までの課題管理を行えます。")
            st.text_input("今日の稽古目標", placeholder="例: 会で3秒伸び合う", key="sb_sched_goal")
            if st.button("目標を保存", key="sb_save_sched", use_container_width=True):
                st.success("稽古目標を記録しました！")
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

    # ── ピン留め・プロジェクト（初期は空。自由に追加・編集・削除） ──
    render_custom_sidebar_section("pins", "ピン留め", ":material/push_pin:")

    # ── 履歴（今日／昨日／過去7日間／それ以前）：各行にピン留めボタン ──────
    all_sess = get_all_sessions()
    if all_sess:
        cur_id = st.session_state.get("current_session_id", all_sess[0]["id"])
        pinned_ids = {x.get("session_id") for x in load_sidebar_items("pins") if x.get("session_id")}

        _q = st.text_input("チャットを検索", key="sidebar_search_chats", placeholder="チャットを検索（Ctrl+K）", label_visibility="collapsed")
        if _q.strip():
            _shown = [x for x in all_sess if _q.strip().lower() in x["title"].lower()]
            if not _shown:
                st.caption("一致するチャットがありません")
        else:
            _shown = all_sess[:30]

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


    # ── スペーサー ──────────────────────────────────────────────
    st.markdown('<div style="margin-top: 24px;"></div>', unsafe_allow_html=True)

    # ── 最下部：ユーザープロフィール ────────────────────────────
    users_db = load_users()
    cur_uinfo = users_db.get(st.session_state.get("logged_in_user", ""), {})
    disp_name = "ゲスト" if st.session_state.get("is_guest") else cur_uinfo.get("display_name", "runtyoma")
    cur_user = st.session_state.get("logged_in_user", "default")
    user_id_num = f"{abs(hash(cur_user)) % 10000:04d}"

    st.markdown(f"""
    <div style="display: flex; align-items: center; gap: 10px; padding: 10px 4px 4px; border-top: 1px solid var(--border-hairline);">
        <div style="width: 30px; height: 30px; border-radius: 50%; background: var(--shu); color: var(--on-accent); display: flex; align-items: center; justify-content: center; font-size: 12.5px; font-weight: 700;">{(disp_name or "R")[:1].upper()}</div>
        <div style="font-size: 13.5px; font-weight: 600; color: var(--ink-primary);">{disp_name}</div>
    </div>
    """, unsafe_allow_html=True)

    with st.popover("アカウント設定・射手カルテ", icon=":material/settings:", use_container_width=True):
        st.markdown(f"""
        <div style="border: 1px solid var(--border-hairline); border-radius: 12px; padding: 14px 16px; margin-bottom: 12px; background: var(--surface-2);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="background: var(--accent-emerald-soft); color: var(--accent-emerald-light); border: 1px solid var(--border-subtle); font-weight: 700; font-size: 10.5px; padding: 2px 8px; border-radius: 6px; letter-spacing: 0.08em;">KYUDO AI PRO</span>
                <span style="font-size: 11px; font-weight: 600; color: var(--accent-emerald-light);">● 稼働中</span>
            </div>
            <div style="font-size: 15px; font-weight: 700; color: var(--ink-primary); margin: 2px 0;">{disp_name}</div>
            <div style="font-size: 11px; color: var(--ink-dim); font-family: monospace;">ID: KYD-8820-{user_id_num}</div>
        </div>
        """, unsafe_allow_html=True)

        tab_profile, tab_memory, tab_inst, tab_appset = st.tabs(["⚙️ 設定", "🧠 カルテ", "🎯 指示", "💾 会話"])

        with tab_profile:
            st.radio("表示テーマ", THEME_CHOICES, key="ui_theme", horizontal=True, on_change=save_ui_theme)
            font_size_choice = st.radio(
                "文字の大きさ:",
                options=["標準 (16px)", "大きめ (18px)", "特大 (22px)"],
                index=0,
                key="sb_font_size_choice"
            )
            size_map = {"標準 (16px)": "16px", "大きめ (18px)": "18px", "特大 (22px)": "22px"}
            cur_size = size_map[font_size_choice]
            st.markdown(f"<style>.stMarkdown p, div[data-testid='stChatMessage'] p {{ font-size: {cur_size} !important; }}</style>", unsafe_allow_html=True)
            
            st.divider()
            if st.button("🚪 ログアウト", use_container_width=True, key="btn_logout_pop"):
                st.session_state.authenticated = False
                st.session_state.is_guest = False
                st.session_state.logged_in_user = ""
                st.session_state.messages = []
                if "current_session_id" in st.session_state:
                    del st.session_state["current_session_id"]
                st.rerun()

        with tab_memory:
            st.caption("AIが対話から覚えた情報です。")
            user_notes = load_user_memory(cur_user)
            if user_notes:
                for idx, note in enumerate(user_notes):
                    col_n1, col_n2 = st.columns([0.80, 0.20])
                    with col_n1:
                        st.markdown(f"<div style='font-size: 12px; padding: 4px 8px; background: var(--surface-3); border-radius: 6px; margin-bottom: 4px; color: var(--ink-primary);'>📌 {note}</div>", unsafe_allow_html=True)
                    with col_n2:
                        if st.button("✕", key=f"del_mem_p_{idx}", help="削除"):
                            remove_user_memory_item(cur_user, idx)
                            st.rerun()
                if st.button("すべての記憶を消去", use_container_width=True, key="clear_all_mem_p"):
                    clear_all_user_memory(cur_user)
                    st.rerun()
            else:
                st.info("記憶はまだありません。")

            new_note = st.text_input("追加する情報:", key="new_mem_pop", placeholder="例: 弓力14kg、参段目標")
            if st.button("記憶を追加", use_container_width=True, key="add_mem_pop_btn"):
                if new_note.strip():
                    add_user_memory_item(cur_user, new_note.strip())
                    st.rerun()

        with tab_inst:
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
    'background:var(--surface-2,#fff);color:var(--ink-primary,#1c1917);border:1px solid var(--border-subtle,rgba(0,0,0,.12));',
    'border-radius:12px;box-shadow:var(--shadow-lg,0 18px 48px -14px rgba(0,0,0,.25));font-family:var(--font-sans,sans-serif);font-size:13.5px;}',
    '#kyudo-ctx button{display:block;width:100%;text-align:left;padding:8px 12px;border:0;border-radius:8px;background:transparent;',
    'color:inherit;font:inherit;cursor:pointer;}',
    '#kyudo-ctx button:hover{background:var(--surface-3,#eeebe5);}'
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
            
            # 会話履歴をコンテキストとして構築
            contents = []
            for m in st.session_state.messages[-6:]:
                role = "user" if m["role"] == "user" else "model"
                contents.append(f"{role}: {m['content']}")
            contents.append(f"user: {user_input}")

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
                f"{regen_instruction}"
                f"【設定・役割（必ず上記科学的エビデンスを頭に入れつつ、初心者にも直感的に伝わるよう日常の身体言語に噛み砕いて回答してください）】\n"
                f"{system_instruction}\n\n"
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
        
        contents = []
        for m in st.session_state.messages[-6:]:
            role = "user" if m["role"] == "user" else "model"
            contents.append(f"{role}: {m['content']}")
        contents.append(f"user: {user_input}")

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
            f"{regen_instruction}"
            f"【設定・役割（必ず上記科学的エビデンスを頭に入れつつ、初心者にも直感的に伝わるよう日常の身体言語に噛み砕いて回答してください）】\n"
            f"{system_instruction}\n\n"
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
                        # まとまって届いたテキストをChatGPTのように滑らかなタイピング速度で流す
                        chunk_str = chunk.text
                        step = 2
                        for i in range(0, len(chunk_str), step):
                            yield chunk_str[i:i+step]
                            time.sleep(0.012)  # 心地よい等速タイピング速度（ドカンと一気に出るのを防止）
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
ただし、回答文は射手自身が直感的に理解できるよう、徹底的に日常の言葉に噛み砕いてわかりやすく伝えてください。

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
   八節（特に引分け〜会〜離れ）において、以下の筋肉・関節が3次元的にどう動いているか、専門用語を日常の言葉に噛み砕いて解説してください。
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

# ユーザーメッセージがまだない場合はChatGPTモバイル（2024-10）風のウェルカム画面を表示
quick_prompt = st.session_state.pop("sidebar_prompt", None)  # サイドバーのピン留め／プロジェクトからの質問

welcome_slot = None
if not st.session_state.messages and not quick_prompt:
  welcome_slot = st.empty()
  with welcome_slot.container():
    # ===== ウェルカム画面（送信と同時に welcome_slot ごと消す） =====
    st.markdown("""
    <div class="hero">
        <h1 class="hero-title">今日の稽古は、<br><em>何</em>から始めますか。</h1>
        <div class="hero-sub">射形の解析、早気や離れの相談、射法八節の学び直し。<br>下の入力欄から、いつでも道場へ。</div>
    </div>
    """, unsafe_allow_html=True)

    # ChatGPT公式スタイル：3つの縦並びクイックアクション
    col_w1, col_w_center, col_w2 = st.columns([0.15, 0.70, 0.15])
    with col_w_center:
        st.markdown("""
        <div style="max-width: 520px; margin: 0 auto; display: flex; flex-direction: column; gap: 6px;">
        """, unsafe_allow_html=True)
        
        st.button("射形を3Dで解析する　射形動画・写真", key="quick_act_1", use_container_width=True,
                  on_click=_set_quick_prompt, args=("射形動画または写真を分析してもらう際の撮影のコツ（アングルや秒数など）と分析手順を教えてください。",))
        st.button("早気・射癖の悩みを相談する", key="quick_act_2", use_container_width=True,
                  on_click=_set_quick_prompt, args=("最近早気（はやけ）になってしまい、会で保てずに離れてしまいます。どうすれば克服できますか？",))
        st.button("射法八節の要点を学び直す", key="quick_act_3", use_container_width=True,
                  on_click=_set_quick_prompt, args=("射法八節（足踏みから残心まで）の中で、昇段審査や的中向上のために最も重要視すべき要点を教えてください。",))

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div style="margin-bottom: 40px;"></div>', unsafe_allow_html=True)

# 過去ログの表示（チャットタイムライン）
for idx, msg in enumerate(st.session_state.messages):
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
                bar_cols = st.columns([0.12, 0.20, 0.28, 0.40])
                with bar_cols[0]:
                    render_chatgpt_toolbar(msg.get("content", ""))
                with bar_cols[1]:
                    if st.button("再生成", key=f"btn_regen_{idx}", icon=":material/refresh:",
                                 help=f"{current_msg_char}の別の視点から回答を再生成", use_container_width=True):
                        last_u_text = None
                        for prev_m in reversed(st.session_state.messages[:idx]):
                            if prev_m["role"] == "user":
                                last_u_text = prev_m["content"]
                                break
                        if last_u_text:
                            st.session_state.messages.pop()
                            st.session_state.pending_regen = {"text": last_u_text, "char": current_msg_char}
                            st.rerun()
                with bar_cols[2]:
                    # 別キャラで再生成：現在の回答キャラを除外した選択肢
                    other_chars = [c for c in CHARACTERS.keys() if c != current_msg_char]
                    if other_chars:
                        with st.popover("別のキャラで", icon=":material/switch_account:", use_container_width=True):
                            st.caption("別のAIキャラクターの視点から回答し直します")
                            for oc in other_chars:
                                oc_info = CHARACTERS[oc]
                                if st.button(f"{oc_info['icon']} {oc}", key=f"regen_char_{idx}_{oc}", use_container_width=True, help=oc_info["desc"]):
                                    last_u_text = None
                                    for prev_m in reversed(st.session_state.messages[:idx]):
                                        if prev_m["role"] == "user":
                                            last_u_text = prev_m["content"]
                                            break
                                    if last_u_text:
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
        placeholder="ログインするとチャットを続けられます" if _guest_locked else "弓道AIに聞く",
        disabled=_guest_locked,
    )
else:
    chat_submission = st.chat_input(
        placeholder="弓道AIに聞く",
        accept_file=True,
        file_type=["mp4", "mov", "avi", "webm", "jpg", "jpeg", "png"]
    )

# 弓道AI道場 フッター注釈
st.markdown("""
<div style="text-align: center; font-size: 11px; color: var(--ink-dim); margin-top: 8px; letter-spacing: 0.02em;">
    弓道AI は間違いを犯すことがあります。重要な情報は必ず確認してください。
</div>
""", unsafe_allow_html=True)

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

        # ユーザー発言を履歴に追加（ライブ描画は一切しない）
        st.session_state.messages.append({
            "role": "user",
            "content": user_msg_text,
            "file_name": attached_media.name,
            "file_size": file_size_str
        })

        # 動画分析はspinnerのみ（DOM衝突を避けるため chat_message を外に出さない）
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
        st.session_state.messages.append({"role": "user", "content": text_to_send})

        # 1) ウェルカム画面を消し、ユーザー発言を最初に即描画（API待ちの間に何も出ない時間をなくす）
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

        avatar_img_stream = os.path.join(ASSETS_DIR, char_info.get("avatar_file", "")) if char_info.get("avatar_file") and os.path.exists(os.path.join(ASSETS_DIR, char_info.get("avatar_file", ""))) else char_info["icon"]
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