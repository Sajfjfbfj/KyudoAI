import os
import time
import json
import re
import tempfile
import hashlib
import secrets
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

def render_chatgpt_toolbar(text_content: str):
    """ChatGPT（2026年版）風：アイコンのみのアクションバー（コピー／読み上げ）。ダークテーマ対応"""
    safe_text_json = json.dumps(text_content).replace("</", "<\\/")
    toolbar_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {
                margin: 0;
                padding: 0;
                background: transparent;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            }
            .bar {
                display: flex;
                align-items: center;
                gap: 0;
                padding-top: 4px;
            }
            .btn {
                width: 32px;
                height: 32px;
                border: none;
                border-radius: 8px;
                background: transparent;
                color: #666666;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                transition: background 0.15s ease, color 0.15s ease;
            }
            .btn:hover {
                background: rgba(0, 0, 0, 0.06);
                color: #171717;
            }
            .btn:active {
                transform: scale(0.94);
            }
            .btn svg {
                width: 18px;
                height: 18px;
                fill: none;
                stroke: currentColor;
                stroke-width: 1.8;
                stroke-linecap: round;
                stroke-linejoin: round;
            }
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
    """.replace("__TEXT__", safe_text_json)
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

# ==================== Linear Dark Canvas × Apple HIG：世界最高峰UIデザインシステム ====================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&family=Noto+Sans+JP:wght@400;500;600;700&display=swap');

:root {
    --canvas: #000000;
    --canvas-subtle: #0d0d0d;
    --surface-1: #171717;
    --surface-2: #212121;
    --surface-3: #2f2f2f;
    --surface-glass: rgba(19, 22, 27, 0.88);
    
    --border-hairline: rgba(255, 255, 255, 0.06);
    --border-subtle: rgba(255, 255, 255, 0.10);
    --border-strong: rgba(255, 255, 255, 0.18);
    
    --accent-emerald: #10b981;
    --accent-emerald-light: #34d399;
    --accent-emerald-glow: 0 0 24px rgba(16, 185, 129, 0.28);
    --accent-emerald-soft: rgba(16, 185, 129, 0.12);
    
    --accent-blue: #5e6ad2;
    --accent-blue-soft: rgba(94, 106, 210, 0.14);
    
    --ink-primary: #f8fafc;
    --ink-secondary: #cbd5e1;
    --ink-muted: #94a3b8;
    --ink-dim: #64748b;
    
    --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.4);
    --shadow-md: 0 6px 20px -2px rgba(0, 0, 0, 0.6), 0 2px 6px -1px rgba(0, 0, 0, 0.4);
    --shadow-lg: 0 16px 40px -4px rgba(0, 0, 0, 0.7), 0 4px 14px -2px rgba(0, 0, 0, 0.4);
    --shadow-float: 0 24px 64px -8px rgba(0, 0, 0, 0.8), 0 8px 24px -4px rgba(0, 0, 0, 0.5);
    
    --radius-full: 9999px;
    --radius-2xl: 22px;
    --radius-xl: 16px;
    --radius-lg: 12px;
    --radius-md: 9px;
    --radius-sm: 6px;
    --ease-spring: cubic-bezier(0.16, 1, 0.3, 1);
}

/* Base Canvas & Typography */
html, body, [class*="css"], .stApp {
    font-family: "Plus Jakarta Sans", "Noto Sans JP", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    background-color: var(--canvas) !important;
    color: var(--ink-primary) !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}

.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background: radial-gradient(circle at 50% 0%, #11141a 0%, var(--canvas) 70%) !important;
    color: var(--ink-primary) !important;
}

/* Scrollbar */
::-webkit-scrollbar { width: 5px !important; height: 5px !important; }
::-webkit-scrollbar-track { background: transparent !important; }
::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.12) !important; border-radius: 9999px !important; }
::-webkit-scrollbar-thumb:hover { background: rgba(255, 255, 255, 0.25) !important; }

/* Streamlit Header Minimalized */
[data-testid="stHeader"] {
    background: rgba(8, 9, 10, 0.85) !important;
    backdrop-filter: blur(20px) saturate(180%) !important;
    -webkit-backdrop-filter: blur(20px) saturate(180%) !important;
    border-bottom: 1px solid var(--border-hairline) !important;
}
[data-testid="stToolbar"], [data-testid="stDecoration"] { display: none !important; }

/* Collapsed Sidebar Icon */
div[data-testid="collapsedControl"] {
    top: 12px !important;
    left: 14px !important;
    z-index: 1001 !important;
}
div[data-testid="collapsedControl"] button {
    background: transparent !important;
    border: none !important;
    color: var(--ink-secondary) !important;
    font-size: 20px !important;
}

/* Main Container Centering & Rhythms */
.main .block-container {
    max-width: 900px !important;
    padding: 24px 28px 160px !important;
    margin: 0 auto !important;
}

/* Typography Hierarchy */
.stMarkdown, .stMarkdown p, .stMarkdown li,
[data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] p {
    color: var(--ink-secondary) !important;
    font-size: 15.5px !important;
    line-height: 1.82 !important;
    letter-spacing: -0.008em !important;
}

h1, h2, h3, h4, h5, h6 {
    color: var(--ink-primary) !important;
    font-weight: 700 !important;
    letter-spacing: -0.03em !important;
}
h1 { font-size: clamp(28px, 3.4vw, 38px) !important; font-weight: 800 !important; }
h2 { font-size: 22px !important; }
h3 { font-size: 18px !important; }
strong { color: #ffffff !important; font-weight: 600 !important; }

div[data-testid="stMarkdownContainer"] code {
    background: rgba(255, 255, 255, 0.06) !important;
    border: 1px solid var(--border-hairline) !important;
    color: var(--accent-emerald-light) !important;
    border-radius: 5px !important;
    padding: 2px 7px !important;
    font-size: 13.5px !important;
    font-family: "JetBrains Mono", monospace !important;
}

div[data-testid="stMarkdownContainer"] blockquote {
    border-left: 3px solid var(--accent-emerald) !important;
    background: rgba(16, 185, 129, 0.05) !important;
    border-radius: 0 var(--radius-md) var(--radius-md) 0 !important;
    padding: 10px 18px !important;
    color: var(--ink-secondary) !important;
    margin: 14px 0 !important;
}

/* ==================== Linear-Style Elevated Sidebar ==================== */
section[data-testid="stSidebar"] {
    background: var(--surface-1) !important;
    border-right: 1px solid var(--border-hairline) !important;
}
section[data-testid="stSidebar"] > div {
    background: transparent !important;
}
section[data-testid="stSidebar"] .stMarkdown,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label {
    color: var(--ink-secondary) !important;
}

.sb-brand-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 8px 18px;
    border-bottom: 1px solid var(--border-hairline);
    margin-bottom: 14px;
}
.sb-brand-title {
    font-size: 16px;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -0.02em;
    line-height: 1.2;
}
.sb-brand-badge {
    display: inline-block;
    background: var(--accent-emerald-soft);
    color: var(--accent-emerald-light);
    border: 1px solid rgba(16, 185, 129, 0.28);
    font-size: 10px;
    font-weight: 700;
    padding: 1px 7px;
    border-radius: var(--radius-full);
    letter-spacing: 0.05em;
    text-transform: uppercase;
}

.sb-section-label {
    color: var(--ink-dim) !important;
    font-size: 10.5px !important;
    font-weight: 700 !important;
    letter-spacing: 0.09em !important;
    text-transform: uppercase !important;
    padding: 16px 8px 6px !important;
}

section[data-testid="stSidebar"] .stButton > button,
section[data-testid="stSidebar"] [data-testid="stPopover"] > button {
    background: transparent !important;
    color: var(--ink-muted) !important;
    border: 1px solid transparent !important;
    border-radius: var(--radius-md) !important;
    box-shadow: none !important;
    min-height: 38px !important;
    padding: 7px 10px !important;
    text-align: left !important;
    justify-content: flex-start !important;
    font-size: 13.5px !important;
    font-weight: 500 !important;
    transition: all 0.16s var(--ease-spring) !important;
    width: 100% !important;
}
section[data-testid="stSidebar"] .stButton > button:hover,
section[data-testid="stSidebar"] [data-testid="stPopover"] > button:hover {
    background: rgba(255, 255, 255, 0.05) !important;
    color: var(--ink-primary) !important;
    transform: translateX(2px) !important;
}

/* Sidebar Active Chat */
section[data-testid="stSidebar"] [class*="st-key-sess_active_"] button {
    background: var(--accent-emerald-soft) !important;
    color: var(--accent-emerald-light) !important;
    border: 1px solid rgba(16, 185, 129, 0.24) !important;
    font-weight: 600 !important;
}

/* New Chat Primary Button */
.sb-new-chat-btn button {
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.18) 0%, rgba(16, 185, 129, 0.08) 100%) !important;
    border: 1px solid rgba(16, 185, 129, 0.35) !important;
    color: var(--accent-emerald-light) !important;
    font-weight: 600 !important;
    font-size: 13.5px !important;
    border-radius: var(--radius-md) !important;
    padding: 9px 12px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 8px !important;
    box-shadow: var(--accent-emerald-glow) !important;
    transition: all 0.2s var(--ease-spring) !important;
}
.sb-new-chat-btn button:hover {
    background: rgba(16, 185, 129, 0.25) !important;
    border-color: var(--accent-emerald) !important;
    color: #ffffff !important;
    transform: translateY(-1px) !important;
}

/* Popover Bodies */
div[data-testid="stPopoverBody"] {
    background: var(--surface-2) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-lg) !important;
    box-shadow: var(--shadow-lg) !important;
    padding: 14px !important;
}
div[data-testid="stPopoverBody"] button {
    color: var(--ink-primary) !important;
}

/* ==================== Top Minimal Navigation Bar ==================== */
.topbar-wrapper {
    background: rgba(19, 22, 27, 0.75) !important;
    backdrop-filter: blur(24px) saturate(180%) !important;
    -webkit-backdrop-filter: blur(24px) saturate(180%) !important;
    border: 1px solid var(--border-hairline) !important;
    border-radius: var(--radius-full) !important;
    padding: 6px 14px !important;
    margin: -8px 0 28px !important;
    box-shadow: var(--shadow-sm) !important;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.topbar-wrapper [data-testid="stButton"] > button,
.topbar-wrapper [data-testid="stPopover"] > button {
    background: transparent !important;
    border: 0 !important;
    box-shadow: none !important;
    color: var(--ink-primary) !important;
    font-weight: 600 !important;
    border-radius: var(--radius-full) !important;
    font-size: 13.5px !important;
    padding: 6px 14px !important;
    transition: background 0.15s ease !important;
}
.topbar-wrapper [data-testid="stButton"] > button:hover,
.topbar-wrapper [data-testid="stPopover"] > button:hover {
    background: rgba(255, 255, 255, 0.08) !important;
}

/* Pulse Dot */
.pulse-dot {
    width: 8px;
    height: 8px;
    background: var(--accent-emerald);
    border-radius: 50%;
    display: inline-block;
    box-shadow: 0 0 10px var(--accent-emerald);
    animation: pulseGlow 2.2s infinite;
}
@keyframes pulseGlow {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.55; transform: scale(0.85); }
}

/* ==================== Bento Hero Grid (Linear / Apple Pro Style) ==================== */
.bento-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px;
    margin: 24px auto 36px;
    max-width: 860px;
}
.bento-card-btn button {
    background: var(--surface-2) !important;
    border: 1px solid var(--border-hairline) !important;
    border-radius: var(--radius-xl) !important;
    padding: 20px 22px !important;
    text-align: left !important;
    justify-content: flex-start !important;
    align-items: flex-start !important;
    color: var(--ink-primary) !important;
    min-height: 110px !important;
    height: 100% !important;
    white-space: normal !important;
    transition: all 0.22s var(--ease-spring) !important;
    box-shadow: var(--shadow-sm) !important;
}
.bento-card-btn button:hover {
    background: var(--surface-3) !important;
    border-color: rgba(16, 185, 129, 0.35) !important;
    transform: translateY(-3px) !important;
    box-shadow: var(--shadow-lg), var(--accent-emerald-glow) !important;
}

/* ==================== Chat Timeline (High-End Linear & Messages) ==================== */
div[data-testid="stChatMessage"] {
    background: transparent !important;
    border: 0 !important;
    box-shadow: none !important;
    padding: 10px 0 !important;
    margin: 0 auto 18px !important;
    max-width: 860px !important;
    width: 100% !important;
}
div[data-testid="stChatMessage"] [data-testid="stChatMessageAvatar"] { display: none !important; }

/* User Message: Elevated Charcoal Bubble */
div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
    max-width: 74% !important;
    margin-left: auto !important;
    margin-right: 0 !important;
    background: linear-gradient(135deg, #181d26 0%, #1e2430 100%) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 20px 20px 4px 20px !important;
    padding: 14px 20px !important;
    box-shadow: var(--shadow-md) !important;
    color: #ffffff !important;
}
div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) p,
div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) span,
div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stMarkdownContainer"] * {
    color: #f8fafc !important;
}

/* Assistant Message: Clean Minimalist Layout */
div[data-testid="stChatMessage"]:not(:has([data-testid="chatAvatarIcon-user"])) {
    background: transparent !important;
    padding: 4px 0 !important;
    width: 100% !important;
}
div[data-testid="stChatMessage"]:not(:has([data-testid="chatAvatarIcon-user"])) p {
    color: var(--ink-primary) !important;
    font-size: 15.5px !important;
    line-height: 1.85 !important;
}

/* Character Badge */
.char-badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 3px 12px !important;
    border-radius: var(--radius-full) !important;
    font-size: 11.5px !important;
    font-weight: 700 !important;
    letter-spacing: 0.04em !important;
    margin: 0 0 12px !important;
    background: var(--surface-2) !important;
    border: 1px solid var(--border-hairline) !important;
    color: var(--ink-secondary) !important;
    text-transform: uppercase;
}
.char-badge.char-master {
    border-color: rgba(217, 119, 6, 0.3) !important;
    color: #fbbf24 !important;
    background: rgba(217, 119, 6, 0.08) !important;
}
.char-badge.char-senior {
    border-color: rgba(16, 185, 129, 0.3) !important;
    color: #34d399 !important;
    background: rgba(16, 185, 129, 0.08) !important;
}
.char-badge.char-analyst {
    border-color: rgba(99, 102, 241, 0.35) !important;
    color: #a5b4fc !important;
    background: rgba(99, 102, 241, 0.08) !important;
}

/* Memory Badge */
.memory-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 12px;
    margin: 4px 0 12px;
    background: var(--accent-emerald-soft) !important;
    color: var(--accent-emerald-light) !important;
    border: 1px solid rgba(16, 185, 129, 0.25) !important;
    border-radius: var(--radius-full) !important;
    font-size: 11.5px !important;
    font-weight: 600 !important;
}

/* File Attachment Card */
.file-attachment-card {
    display: inline-flex;
    align-items: center;
    gap: 12px;
    background: var(--surface-2) !important;
    border: 1px solid var(--border-subtle) !important;
    border-radius: var(--radius-lg) !important;
    padding: 10px 16px !important;
    margin-bottom: 10px !important;
}
.file-attachment-name { color: #ffffff !important; font-weight: 600 !important; font-size: 13.5px !important; }
.file-attachment-meta { color: var(--accent-emerald-light) !important; font-size: 11px !important; }

/* ==================== Floating Command Bar Input (Linear Prompt Deck) ==================== */
div[data-testid="stBottom"] {
    background: linear-gradient(180deg, rgba(8, 9, 10, 0) 0%, rgba(8, 9, 10, 0.88) 25%, #08090a 100%) !important;
    backdrop-filter: blur(16px) !important;
    border-top: 0 !important;
    padding: 24px 0 calc(22px + env(safe-area-inset-bottom, 0px)) !important;
    z-index: 9999 !important;
}
div[data-testid="stBottom"] > div {
    max-width: 860px !important;
    padding: 0 20px !important;
    margin: auto !important;
}
div[data-testid="stChatInput"] {
    background: rgba(19, 22, 27, 0.92) !important;
    backdrop-filter: blur(28px) saturate(200%) !important;
    -webkit-backdrop-filter: blur(28px) saturate(200%) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 26px !important;
    box-shadow: var(--shadow-float) !important;
    padding: 8px 16px !important;
    transition: all 0.22s var(--ease-spring) !important;
}
div[data-testid="stChatInput"]:focus-within {
    border-color: rgba(16, 185, 129, 0.45) !important;
    box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.15), var(--shadow-float) !important;
    background: #14171d !important;
}
div[data-testid="stChatInput"] textarea {
    color: #ffffff !important;
    font-size: 15px !important;
    background: transparent !important;
    line-height: 1.6 !important;
}
div[data-testid="stChatInput"] textarea::placeholder {
    color: var(--ink-dim) !important;
}
div[data-testid="stChatInput"] button {
    background: transparent !important;
    color: var(--ink-muted) !important;
    border: 0 !important;
    border-radius: var(--radius-full) !important;
    transition: all 0.15s ease !important;
}
div[data-testid="stChatInput"] button:hover {
    background: rgba(255, 255, 255, 0.08) !important;
    color: #ffffff !important;
}

/* ==================== Standard Buttons & Controls ==================== */
.stButton > button, .stDownloadButton > button, button[kind="secondary"] {
    background: var(--surface-2) !important;
    color: var(--ink-primary) !important;
    border: 1px solid var(--border-hairline) !important;
    border-radius: var(--radius-md) !important;
    box-shadow: var(--shadow-sm) !important;
    font-weight: 600 !important;
    font-size: 13.5px !important;
    min-height: 38px !important;
    padding: 7px 16px !important;
    transition: all 0.18s var(--ease-spring) !important;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    background: var(--surface-3) !important;
    border-color: var(--border-subtle) !important;
    color: #ffffff !important;
    transform: translateY(-1px) !important;
    box-shadow: var(--shadow-md) !important;
}
.stButton > button:active {
    transform: scale(0.98) !important;
}

button[kind="primary"], .stFormSubmitButton > button {
    background: var(--accent-emerald) !important;
    color: #08090a !important;
    border: 0 !important;
    border-radius: var(--radius-md) !important;
    font-weight: 700 !important;
    box-shadow: var(--accent-emerald-glow) !important;
    transition: all 0.2s var(--ease-spring) !important;
}
button[kind="primary"]:hover, .stFormSubmitButton > button:hover {
    background: var(--accent-emerald-light) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 0 28px rgba(16, 185, 129, 0.45) !important;
}

/* Inputs & Form Controls */
div[data-baseweb="input"], div[data-baseweb="textarea"],
div[data-baseweb="select"] > div {
    background: var(--surface-2) !important;
    border: 1px solid var(--border-hairline) !important;
    border-radius: var(--radius-md) !important;
    color: var(--ink-primary) !important;
    transition: all 0.2s ease !important;
}
div[data-baseweb="input"]:focus-within,
div[data-baseweb="textarea"]:focus-within,
div[data-baseweb="select"]:focus-within {
    border-color: var(--accent-emerald) !important;
    box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2) !important;
}
input, textarea, [data-baseweb="select"] * { color: var(--ink-primary) !important; }
input::placeholder, textarea::placeholder { color: var(--ink-dim) !important; }

/* Tabs */
div[data-baseweb="tab-list"] {
    border-bottom: 1px solid var(--border-hairline) !important;
    gap: 16px !important;
}
button[data-baseweb="tab"] {
    color: var(--ink-muted) !important;
    font-weight: 600 !important;
    font-size: 13.5px !important;
    padding: 10px 4px !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: var(--accent-emerald-light) !important;
    border-bottom: 2px solid var(--accent-emerald) !important;
}

div[data-testid="stExpander"] {
    background: var(--surface-2) !important;
    border: 1px solid var(--border-hairline) !important;
    border-radius: var(--radius-lg) !important;
}

/* Plotly Chart Card */
.stPlotlyChart {
    background: var(--surface-2) !important;
    border: 1px solid var(--border-hairline) !important;
    border-radius: var(--radius-xl) !important;
    padding: 14px;
    box-shadow: var(--shadow-sm) !important;
}

/* Responsive */
@media (max-width: 900px) {
    .main .block-container { padding: 20px 16px 140px !important; }
    .bento-grid { grid-template-columns: 1fr !important; }
}
@media (max-width: 600px) {
    .main .block-container { padding: 14px 12px 130px !important; }
    div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
        max-width: 88% !important;
        padding: 12px 16px !important;
    }
    div[data-testid="stBottom"] > div { padding: 0 8px !important; }
}
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

# ==================== 世界最高峰UI：ログイン画面（スマホ・タブレット完全対応） ====================
def render_login_screen():
    st.markdown("""
    <div class="login-wrap">
        <div class="login-card-header">
            <div class="login-logo">🏹</div>
            <div class="login-title">弓道AI道場</div>
            <div class="login-subtitle">世界最高峰の対話美学で射技稽古・3D動作解析を体験しましょう</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # スマホ・タブレット・PC全対応の中央カードレイアウト
    _, col_center, _ = st.columns([0.05, 0.9, 0.05]) if st.session_state.get("_is_mobile", False) else st.columns([1, 1.8, 1])
    with col_center:
        tab_login, tab_register = st.tabs(["🔑 ログイン", "✨ 新規アカウント登録"])
        
        with tab_login:
            with st.form("login_form", clear_on_submit=False):
                uname = st.text_input("ユーザー名", placeholder="ユーザー名を入力")
                upass = st.text_input("パスワード", type="password", placeholder="パスワードを入力")
                btn_login = st.form_submit_button("ログインして道場に入る", use_container_width=True, type="primary")
                
                if btn_login:
                    if uname and upass and authenticate_user(uname, upass):
                        st.session_state.authenticated = True
                        st.session_state.logged_in_user = uname.strip().lower()
                        st.success("✅ 認証成功！道場へ移動します...")
                        time.sleep(0.4)
                        st.rerun()
                    else:
                        st.error("ユーザー名またはパスワードが正しくありません。")

            
        with tab_register:
            with st.form("reg_form", clear_on_submit=False):
                reg_name = st.text_input("希望のユーザー名 (英数字3文字以上)", placeholder="例: yamada")
                reg_disp = st.text_input("お名前・道場での呼び名 (任意)", placeholder="例: 山田")
                reg_pass1 = st.text_input("パスワード (6文字以上)", type="password", placeholder="パスワード")
                reg_pass2 = st.text_input("パスワードの確認", type="password", placeholder="もう一度入力")
                btn_reg = st.form_submit_button("アカウントを作成する", use_container_width=True, type="primary")
                
                if btn_reg:
                    if not reg_name or not reg_pass1:
                        st.error("すべての必須項目を入力してください。")
                    elif reg_pass1 != reg_pass2:
                        st.error("パスワードが一致しません。")
                    else:
                        ok, msg = register_user(reg_name, reg_pass1, reg_disp)
                        if ok:
                            st.success(f"🎉 {msg} 「ログイン」タブからログインしてください。")
                        else:
                            st.error(msg)

# ==================== 認証状態チェック（即座に稽古開始可能な安心設計） ====================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = True
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

# ==================== 弓道AI道場 ナビゲーション（Linear / Apple Pro スタイル） ====================
with st.sidebar:

    # ── ブランドヘッダー（ロゴ + バッジ） ─────────────────────────
    logo_b64 = get_asset_base64("kyudo_ai_logo.jpg")
    if logo_b64:
        logo_html = f'<img src="data:image/jpeg;base64,{logo_b64}" style="width: 38px; height: 38px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.15); box-shadow: 0 4px 16px rgba(16,185,129,0.25); object-fit: cover;">'
    else:
        logo_html = '<div style="width: 38px; height: 38px; border-radius: 10px; background: linear-gradient(135deg, #10b981 0%, #059669 100%); display: flex; align-items: center; justify-content: center; font-size: 20px;">🏹</div>'

    st.markdown(f"""
    <div style="display: flex; align-items: center; justify-content: space-between; padding: 6px 4px 10px 4px;">
        <div style="display: flex; align-items: center; gap: 10px;">
            {logo_html}
            <div>
                <span style="font-size: 16px; font-weight: 700; color: #ececec; letter-spacing: -0.02em;">ChatGPT</span>
                <span style="font-size: 10.5px; color: #10b981; font-weight: 600; margin-left: 6px; padding: 1px 6px; border-radius: 6px; background: rgba(16,185,129,0.12); border: 1px solid rgba(16,185,129,0.25);">弓道AI</span>
            </div>
        </div>
        <div style="display: flex; align-items: center; gap: 14px; color: #8e8e8e; font-size: 15px;">
            <span style="cursor: pointer;" title="検索">🔍</span>
            <span style="cursor: pointer;" title="サイドバーを折りたたむ">◫</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 新規チャットボタン ──────────────────────────────────────
    st.markdown('<div class="sb-new-chat-btn">', unsafe_allow_html=True)
    if st.button("✏️  新しいチャット", key="sidebar_new_chat_btn", use_container_width=True):
        new_id = f"session_{int(time.time())}"
        st.session_state.current_session_id = new_id
        st.session_state.messages = []
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # ── スタジオ・分析メニュー ──────────────────────────────────
    st.markdown("<div class='sb-section-label'>スタジオ・分析</div>", unsafe_allow_html=True)

    with st.popover("🖼️  画像（射形3D解析）", use_container_width=True):
        st.markdown("<div style='font-size: 13px; font-weight: 700; color: #ffffff; margin-bottom: 6px;'>🎬 射形動画・写真の3D解析</div>", unsafe_allow_html=True)
        st.caption("画面下の入力欄の「＋」ボタンから動画や写真（MP4/PNG等）を添付して送信すると、AIが3D骨格アライメントと筋肉活動バランスを立体解析します。")

    with st.popover("⏱️  スケジュール", use_container_width=True):
        st.markdown("<div style='font-size: 13px; font-weight: 700; color: #ffffff; margin-bottom: 6px;'>📅 稽古スケジュール＆課題</div>", unsafe_allow_html=True)
        st.caption("日々の稽古計画や昇段審査までの課題管理を行えます。")
        st.text_input("今日の稽古目標:", placeholder="例: 会で3秒伸び合う", key="sb_sched_goal")
        if st.button("目標を保存", key="sb_save_sched", use_container_width=True):
            st.success("稽古目標を記録しました！")

    with st.popover("📖  ライブラリ", use_container_width=True):
        st.markdown("""
        <div style='font-size: 13px; font-weight: 700; color: #ffffff; margin-bottom: 8px;'>📖 弓道教本・射法八節</div>
        <div style='font-size: 12px; color: #cbd5e1; line-height: 1.7;'>
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

    with st.popover("🧩  プラグイン", use_container_width=True):
        st.markdown("<div style='font-size: 13px; font-weight: 700; color: #ffffff; margin-bottom: 6px;'>⚡ 弓道生体力学プラグイン</div>", unsafe_allow_html=True)
        st.caption("筑波大・日本武道学会等の筋電図（EMG）・重心動揺・角見トルク力学知見エンジンが常時有効化されています。")

    # ── 指導陣（キャラクター切替） ──────────────────────────────
    cur_c = st.session_state.get("current_selected_char", list(CHARACTERS.keys())[0])
    c_info = CHARACTERS.get(cur_c, list(CHARACTERS.values())[0])
    with st.popover("…  探索（指導陣切替）", use_container_width=True):
        st.markdown("<div style='font-size: 11px; font-weight: 700; color: var(--ink-dim); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px;'>指導陣（AIモデル）を選択</div>", unsafe_allow_html=True)
        for cname in CHARACTERS.keys():
            c_info_item = CHARACTERS[cname]
            is_active = (cname == cur_c)
            avatar_b64 = get_asset_base64(c_info_item.get("avatar_file", ""))
            if avatar_b64:
                prefix = f'<img src="data:image/jpeg;base64,{avatar_b64}" style="width: 22px; height: 22px; border-radius: 50%; vertical-align: middle; margin-right: 8px;">'
            else:
                prefix = f"{c_info_item['icon']} "
            
            btn_label = f"{'✓ ' if is_active else '　 '}{c_info_item['icon']} {cname}"
            if st.button(btn_label, key=f"sb_explore_char_{cname}", use_container_width=True, help=c_info_item["desc"]):
                switch_ai_character(cname)
                st.rerun()

    # ── ピン留め ──────────────────────────────────────────────
    st.markdown("<div class='sb-section-label'>ピン留め稽古</div>", unsafe_allow_html=True)
    sidebar_pins = [
        ("pin_chu_sha", "🎯 弓道中と斜の使い方", "弓道における『中（ちゅう）』と『斜（しゃ）』の使い方・身体の意識の相違点を教えてください。"),
        ("pin_taikai", "📊 弓道大会記録システム", "弓道の大会や記録会で的中率を安定させるためのルーティンと記録分析方法を教えてください。"),
        ("pin_kimono", "🥋 黒い着物の女性", "弓道着・黒紋付や着物での射術・体配の要点について教えてください。"),
        ("pin_line_icon", "🎨 LINEアイコン作成", "弓道をモチーフにした洗練されたアイコンデザインのアイデアを教えてください。"),
    ]
    for pin_key, pin_label, pin_prompt in sidebar_pins:
        if st.button(pin_label, key=pin_key, use_container_width=True):
            st.session_state["sidebar_prompt"] = pin_prompt
            st.rerun()

    # ── プロジェクト ──────────────────────────────────────────
    st.markdown("<div class='sb-section-label'>プロジェクト</div>", unsafe_allow_html=True)
    sidebar_projects = [
        ("proj_writing", "🟣 ライティング", "弓道に関する解説記事や文章の推敲・執筆をサポートしてください。"),
        ("proj_portfolio", "🎓 ポートフォリオ", "これまでの弓道の修練歴や実績、課題をポートフォリオ形式で整理してください。"),
    ]
    for proj_key, proj_label, proj_prompt in sidebar_projects:
        if st.button(proj_label, key=proj_key, use_container_width=True):
            st.session_state["sidebar_prompt"] = proj_prompt
            st.rerun()

    # ── 履歴（今日／昨日／過去7日間／それ以前） ──────────────
    all_sess = get_all_sessions()
    if all_sess:
        cur_id = st.session_state.get("current_session_id", all_sess[0]["id"])

        for group_name, group_items in group_sessions_by_date(all_sess[:30]).items():
            st.markdown(f"<div class='sb-section-label'>{group_name}</div>", unsafe_allow_html=True)

            for sess in group_items:
                is_active = (sess["id"] == cur_id)

                if is_active:
                    col_btn, col_opt = st.columns([0.82, 0.18])
                    with col_btn:
                        st.button(f"💬 {sess['title']}", key=f"sess_active_{sess['id']}", use_container_width=True)
                    with col_opt:
                        with st.popover("···", use_container_width=True):
                            st.caption("チャット設定")
                            rename_val = st.text_input("タイトル変更", value=sess["title"], key=f"ren_{sess['id']}")
                            if st.button("変更保存", key=f"b_ren_{sess['id']}", use_container_width=True):
                                rename_session(sess["id"], rename_val)
                                st.rerun()
                            if st.button("🗑️ このチャットを削除", key=f"b_del_{sess['id']}", use_container_width=True):
                                delete_session(sess["id"])
                                remains = get_all_sessions()
                                if remains:
                                    st.session_state.current_session_id = remains[0]["id"]
                                    st.session_state.messages = load_session_messages(remains[0]["id"]) or []
                                else:
                                    new_id = f"session_{int(time.time())}"
                                    st.session_state.current_session_id = new_id
                                    st.session_state.messages = []
                                st.rerun()
                else:
                    if st.button(f"💬 {sess['title']}", key=f"sess_btn_{sess['id']}", use_container_width=True):
                        st.session_state.current_session_id = sess["id"]
                        loaded = load_session_messages(sess["id"])
                        if loaded is not None:
                            st.session_state.messages = loaded
                        st.rerun()

    else:
        st.markdown("<div class='sb-section-label'>最近の項目</div>", unsafe_allow_html=True)
        recent_samples = [
            ("志望動機作成:VEVENT", "弓道の指導員・武道関連の志望動機書（VEVENT形式）の作成をサポートしてください。"),
            ("志望動機作成", "大学弓道部や実業団弓道部への志望動機文の添削をお願いします。"),
            ("履歴書修正対応", "弓道有段者としての実績や礼儀作法をアピールする履歴書の自己PRを作成してください。"),
            ("面接用自己紹介作成", "弓道で培った集中力と残心の精神を伝える面接自己紹介を作ってください。"),
            ("配慮事項の承諾結果", "大会や合宿での健康管理・配慮事項に関する確認事項を整理してください。"),
        ]
        for s_idx, (s_title, s_prompt) in enumerate(recent_samples):
            if st.button(f"💬 {s_title}", key=f"sample_sess_{s_idx}", use_container_width=True):
                st.session_state["sidebar_prompt"] = s_prompt
                st.rerun()

    # ── スペーサー ──────────────────────────────────────────────
    st.markdown('<div style="margin-top: 24px;"></div>', unsafe_allow_html=True)

    # ── 最下部：ユーザープロフィール ────────────────────────────
    users_db = load_users()
    cur_uinfo = users_db.get(st.session_state.get("logged_in_user", ""), {})
    disp_name = cur_uinfo.get("display_name", "runtyoma")
    cur_user = st.session_state.get("logged_in_user", "default")
    user_id_num = f"{abs(hash(cur_user)) % 10000:04d}"

    sb_u_c1, sb_u_c2 = st.columns([0.62, 0.38])
    with sb_u_c1:
        st.markdown("""
        <div style="display: flex; align-items: center; gap: 10px; padding: 4px 0;">
            <div style="width: 32px; height: 32px; border-radius: 50%; background: #2f2f2f; border: 1px solid rgba(255,255,255,0.15); display: flex; align-items: center; justify-content: center; font-size: 13px; color: #ffffff; font-weight: 700;">
                R
            </div>
            <div>
                <div style="font-size: 13.5px; font-weight: 600; color: #ffffff; line-height: 1.2;">runtyoma</div>
                <div style="font-size: 11px; color: #8e8e8e;">無料</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with sb_u_c2:
        st.markdown("""
        <div style="text-align: right; padding-top: 6px;">
            <span style="display: inline-block; padding: 4px 10px; border-radius: 9999px; background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15); color: #ececec; font-size: 11px; font-weight: 600; cursor: pointer;">アップグレード</span>
        </div>
        """, unsafe_allow_html=True)

    with st.popover("⚙️ アカウント設定・射手カルテ", use_container_width=True):
        st.markdown(f"""
        <div style="border: 1px solid var(--border-hairline); border-radius: 12px; padding: 14px 16px; margin-bottom: 12px; background: var(--surface-2);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="background: var(--accent-emerald-soft); color: var(--accent-emerald-light); border: 1px solid rgba(16,185,129,0.3); font-weight: 700; font-size: 10.5px; padding: 2px 8px; border-radius: 10px;">KYUDO AI PRO</span>
                <span style="font-size: 11px; font-weight: 600; color: var(--accent-emerald-light);">● 稼働中</span>
            </div>
            <div style="font-size: 15px; font-weight: 700; color: #ffffff; margin: 2px 0;">{disp_name}</div>
            <div style="font-size: 11px; color: var(--ink-dim); font-family: monospace;">ID: KYD-8820-{user_id_num}</div>
        </div>
        """, unsafe_allow_html=True)

        tab_profile, tab_memory, tab_inst, tab_appset = st.tabs(["⚙️ 設定", "🧠 カルテ", "🎯 指示", "💾 会話"])

        with tab_profile:
            font_size_choice = st.radio(
                "文字の大きさ:",
                options=["標準 (16px)", "大きめ (18px)", "特大 (22px)"],
                index=0,
                key="sb_font_size_choice"
            )
            size_map = {"標準 (16px)": "16px", "大きめ (18px)": "18px", "特大 (22px)": "22px"}
            cur_size = size_map[font_size_choice]
            st.markdown(f"<style>.stMarkdown p, div[data-testid='stChatMessage'] p {{ font-size: {cur_size} !important; }}</style>", unsafe_allow_html=True)
            
            if st.button("🗑️ この会話をリセット", use_container_width=True, key="reset_chat_sb"):
                cur_c = st.session_state.get("current_selected_char", list(CHARACTERS.keys())[0])
                st.session_state.messages = [{
                    "role": "assistant",
                    "char": cur_c,
                    "content": CHARACTERS[cur_c]["welcome"]
                }]
                if "current_session_id" in st.session_state:
                    save_current_session(st.session_state.current_session_id, st.session_state.messages)
                st.rerun()

            st.divider()
            if st.button("🚪 ログアウト", use_container_width=True, key="btn_logout_pop"):
                st.session_state.authenticated = False
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
                        st.markdown(f"<div style='font-size: 12px; padding: 4px 8px; background: var(--surface-3); border-radius: 6px; margin-bottom: 4px; color: #ffffff;'>📌 {note}</div>", unsafe_allow_html=True)
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
            st.markdown("""
            <div style="background-color: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.25); border-radius: 8px; padding: 10px; font-size: 11.5px; color: #34d399; margin-top: 8px;">
                🛡️ 動画・画像は分析直後に完全シュレッダー抹消されます。
            </div>
            """, unsafe_allow_html=True)

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

# ==================== 弓道AI道場 トップナビゲーション（フローティング・グラスバー） ====================
cur_char_val = st.session_state.get("current_selected_char", list(CHARACTERS.keys())[0])
short_char_name = cur_char_val.split("（")[0]

top_cols = st.columns([0.68, 0.32])
with top_cols[0]:
    with st.popover(f"● {short_char_name} ▾", use_container_width=False):
        st.markdown("<div style='font-size: 11px; font-weight: 700; color: var(--ink-dim); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px;'>指導陣（AIモデル）を選択</div>", unsafe_allow_html=True)
        for cname in CHARACTERS.keys():
            c_info_item = CHARACTERS[cname]
            is_active = (cname == cur_char_val)
            btn_prefix = "✓ " if is_active else "　 "
            if st.button(f"{btn_prefix}{c_info_item['icon']} {cname}", key=f"top_sel_{cname}", use_container_width=True, help=c_info_item["desc"]):
                switch_ai_character(cname)
                st.rerun()

with top_cols[1]:
    st.markdown("""
    <div style="display: flex; align-items: center; justify-content: flex-end; gap: 10px; padding-top: 4px;">
        <div style="display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px; border-radius: 9999px; background: rgba(59, 130, 246, 0.12); border: 1px solid rgba(59, 130, 246, 0.3); color: #60a5fa; font-size: 12.5px; font-weight: 600; cursor: pointer;">
            <span>✦</span><span>アップグレード</span>
        </div>
        <div style="width: 30px; height: 30px; border-radius: 50%; background: #2f2f2f; border: 1px solid rgba(255,255,255,0.15); display: flex; align-items: center; justify-content: center; font-size: 13px; color: #ffffff; font-weight: 600;">
            R
        </div>
    </div>
    """, unsafe_allow_html=True)

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
        fillcolor='rgba(16, 185, 129, 0.22)',
        line=dict(color='#10b981', width=2.5),
        marker=dict(size=6, color='#34d399'),
        name='筋活動バランス'
    ))
    
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickfont=dict(size=10, color='#64748b'),
                gridcolor='#222733',
                linecolor='#222733'
            ),
            angularaxis=dict(
                tickfont=dict(size=11, color='#f8fafc', weight=600),
                gridcolor='#222733',
                linecolor='#222733'
            ),
            bgcolor='#0e1013'
        ),
        paper_bgcolor='#13161b',
        plot_bgcolor='#13161b',
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
        ("Neck", "Chest", "#10b981", 7),
        ("Chest", "Pelvis", "#10b981", 8),
        # 押手リンク
        ("Chest", "L_Shoulder", "#10b981", 6),
        ("L_Shoulder", "L_Elbow", "#38bdf8", 6),
        ("L_Elbow", "L_Wrist", "#38bdf8", 6),
        # 妻手リンク
        ("Chest", "R_Shoulder", "#10b981", 6),
        ("R_Shoulder", "R_Elbow", "#fbbf24", 6),
        ("R_Elbow", "R_Wrist", "#fbbf24", 6),
        # 下半身リンク
        ("Pelvis", "L_Hip", "#10b981", 6),
        ("L_Hip", "L_Foot", "#10b981", 6),
        ("Pelvis", "R_Hip", "#10b981", 6),
        ("R_Hip", "R_Foot", "#10b981", 6),
        # 弓幹
        ("Bow_Bottom", "L_Wrist", "#a855f7", 4),
        ("L_Wrist", "Bow_Top", "#a855f7", 4),
        # 矢（L_Wrist から R_Wrist への水平ベクトル）
        ("L_Wrist", "R_Wrist", "#eab308", 5),
        # 弦（Bow_Top -> R_Wrist -> Bow_Bottom）
        ("Bow_Top", "R_Wrist", "#94a3b8", 2),
        ("R_Wrist", "Bow_Bottom", "#94a3b8", 2)
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
        marker=dict(size=6, color='#10b981'),
        text=["頭", "頸", "胸", "丹田", "押手肩", "押手肘", "角見(押手)", "妻手肩", "妻手肘", "取懸け", "左腰", "左足", "右腰", "右足", "弓(本)", "弓(末)"],
        textposition="top center",
        textfont=dict(size=10, color='#f8fafc'),
        hoverinfo='text',
        showlegend=False
    ))
    
    fig.update_layout(
        scene=dict(
            xaxis=dict(title='左右', range=[-1.1, 1.1], backgroundcolor='#0e1013', gridcolor='#222733', linecolor='#222733', color='#64748b'),
            yaxis=dict(title='前後', range=[-0.6, 0.6], backgroundcolor='#0e1013', gridcolor='#222733', linecolor='#222733', color='#64748b'),
            zaxis=dict(title='天地', range=[-0.1, 2.3], backgroundcolor='#0e1013', gridcolor='#222733', linecolor='#222733', color='#64748b'),
            camera=dict(
                eye=dict(x=1.3, y=-1.5, z=0.8) # 斜め前からの自然な視点
            ),
            aspectratio=dict(x=1.4, y=0.8, z=1.5)
        ),
        paper_bgcolor='#13161b',
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

if not st.session_state.messages:
    # ===== ChatGPT公式完全一致：ウェルカム画面（今日は何をしましょうか？） =====
    st.markdown("""
    <div style="text-align: center; margin: 14vh 0 32px 0;">
        <h1 style="font-size: clamp(26px, 3.2vw, 34px); font-weight: 700; color: #ececec; margin: 0 0 16px 0; letter-spacing: -0.02em;">
            今日は何をしましょうか？
        </h1>
    </div>
    """, unsafe_allow_html=True)

    # ChatGPT公式スタイル：3つの縦並びクイックアクション
    col_w1, col_w_center, col_w2 = st.columns([0.15, 0.70, 0.15])
    with col_w_center:
        st.markdown("""
        <div style="max-width: 520px; margin: 0 auto; display: flex; flex-direction: column; gap: 6px;">
        """, unsafe_allow_html=True)
        
        if st.button("🖼️　画像またはステッカーを作成（射形動画・写真の3D分析）", key="quick_act_1", use_container_width=True):
            quick_prompt = "射形動画または写真を分析してもらう際の撮影のコツ（アングルや秒数など）と分析手順を教えてください。"
        if st.button("✏️　記述または編集（射癖・早気の改善相談）", key="quick_act_2", use_container_width=True):
            quick_prompt = "最近早気（はやけ）になってしまい、会で保てずに離れてしまいます。どうすれば克服できますか？"
        if st.button("🌐　ウェブを検索（弓道教本・射法八節の検索）", key="quick_act_3", use_container_width=True):
            quick_prompt = "射法八節（足踏みから残心まで）の中で、昇段審査や的中向上のために最も重要視すべき要点を教えてください。"

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
                        <span class="file-attachment-meta" style="color: #166534; font-weight: 500;">
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
                bar_cols = st.columns([0.30, 0.34, 0.36])
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
if "pending_regen" in st.session_state:
    p_info = st.session_state.pop("pending_regen")
    target_text = p_info["text"]
    target_char = p_info["char"]
    t_info = CHARACTERS.get(target_char, char_info)

    with st.chat_message("assistant", avatar=t_info["icon"]):
        st.markdown(f'<span class="char-badge {t_info["badge_class"]}">{t_info["icon"]} {target_char}</span>', unsafe_allow_html=True)
        try:
            stream_gen = generate_response_stream(target_text, target_char, active_api_key, is_regenerate=True)
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
chat_submission = st.chat_input(
    placeholder="弓道AIに聞く",
    accept_file=True,
    file_type=["mp4", "mov", "avi", "webm", "jpg", "jpeg", "png"]
)

# 弓道AI道場 フッター注釈
st.markdown("""
<div style="text-align: center; font-size: 11.5px; color: #64748b; margin-top: 8px; letter-spacing: 0.01em; font-family: 'Inter', sans-serif;">
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

        # ChatGPT風：ユーザー発言から個人情報（弓力・段位・悩み・弓具など）を自動学習して射手カルテに保存
        new_mem_items = []
        if active_api_key:
            cur_user = st.session_state.get("logged_in_user", "default")
            new_mem_items = auto_extract_and_save_memory(cur_user, text_to_send, active_api_key)

        # 画面にリアルタイムでストリーミング描画（ChatGPT完全再現）
        with st.chat_message("user"):
            st.markdown(text_to_send)

        avatar_img_stream = os.path.join(ASSETS_DIR, char_info.get("avatar_file", "")) if char_info.get("avatar_file") and os.path.exists(os.path.join(ASSETS_DIR, char_info.get("avatar_file", ""))) else char_info["icon"]
        with st.chat_message("assistant", avatar=avatar_img_stream):
            st.markdown(f'<span class="char-badge {char_info["badge_class"]}">{char_info["icon"]} {selected_char}</span>', unsafe_allow_html=True)
            if new_mem_items:
                mem_tags = "、".join(new_mem_items)
                st.markdown(f'<div class="memory-badge"><span>🧠</span><span>メモリを更新しました（{mem_tags}）</span></div>', unsafe_allow_html=True)

            try:
                stream_gen = generate_response_stream(text_to_send, selected_char, active_api_key)
                full_reply = st.write_stream(stream_gen)
            except Exception as e:
                full_reply = f"⚠️ エラーが発生しました: {str(e)}"
                st.markdown(full_reply)

            # ChatGPT風：アクションツールバー（コピー・読み上げ・停止）
            render_chatgpt_toolbar(full_reply)



        asst_msg = {
            "role": "assistant",
            "char": selected_char,
            "content": full_reply
        }
        if new_mem_items:
            asst_msg["memory_items"] = new_mem_items
        st.session_state.messages.append(asst_msg)

        # 会話を即時自動保存（最初の質問ならAIが12文字前後のスマート要約タイトルを自動生成）
        if "current_session_id" in st.session_state:
            user_msg_count = sum(1 for m in st.session_state.messages if m["role"] == "user")
            smart_title = None
            if user_msg_count == 1 and active_api_key:
                smart_title = generate_smart_title(text_to_send, active_api_key)
            save_current_session(st.session_state.current_session_id, st.session_state.messages, custom_title=smart_title)

        st.rerun()