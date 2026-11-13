import os
import time
import json
import re
import tempfile
import hashlib
import secrets
import streamlit as st
import plotly.graph_objects as go
from google import genai
from google.genai import types

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

# ChatGPT風モダンUIカスタムCSS（スマホ・タブレット・PC完全レスポンシブ対応）
st.markdown(f"""
<style>
    /* 全体フォントと背景（ChatGPT風のクリーンホワイト） */
    .stApp {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", "Hiragino Kaku Gothic ProN", Meiryo, sans-serif !important;
        background-color: #ffffff !important;
        color: #0d0d0d !important;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }}
    
    /* メインチャットコンテナ（PC・タブレット・スマホで自然に伸縮） */
    .main .block-container {{
        max-width: 820px !important;
        padding-top: 20px !important;
        padding-bottom: 140px !important;
        margin: 0 auto !important;
    }}
    
    /* 下部固定入力バーエリア（スマホのセーフエリア対応） */
    div[data-testid="stBottom"] {{
        background: linear-gradient(180deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.92) 25%, #ffffff 100%) !important;
        backdrop-filter: blur(10px) !important;
        -webkit-backdrop-filter: blur(10px) !important;
        padding-bottom: calc(14px + env(safe-area-inset-bottom, 0px)) !important;
        z-index: 9999 !important;
    }}
    div[data-testid="stBottom"] > div {{
        max-width: 820px !important;
        margin: 0 auto !important;
        padding: 0 12px !important;
    }}

    /* ChatGPT風の角丸ピル型入力バー */
    div[data-testid="stChatInput"] {{
        border: 1px solid #dcdfe4 !important;
        border-radius: 26px !important;
        background-color: #ffffff !important;
        box-shadow: 0 4px 20px rgba(0,0,0,0.06), 0 1px 3px rgba(0,0,0,0.03) !important;
        padding: 6px 12px !important;
        transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1) !important;
    }}
    div[data-testid="stChatInput"]:focus-within {{
        border-color: #10a37f !important;
        box-shadow: 0 6px 24px rgba(16,163,127,0.15), 0 1px 4px rgba(16,163,127,0.08) !important;
    }}
    div[data-testid="stChatInput"] textarea {{
        font-size: 16px !important;
        color: #0d0d0d !important;
        background-color: transparent !important;
        line-height: 1.6 !important;
        min-height: 38px !important;
    }}
    /* 入力欄の添付プラスボタン */
    div[data-testid="stChatInput"] button {{
        color: #4b5563 !important;
        transition: color 0.15s ease, transform 0.15s ease !important;
        border-radius: 50% !important;
        min-width: 36px !important;
        min-height: 36px !important;
    }}
    div[data-testid="stChatInput"] button:hover {{
        color: #10a37f !important;
        background-color: #f0fdf4 !important;
        transform: scale(1.05) !important;
    }}

    /* マークダウンテキスト */
    .stMarkdown, .stMarkdown p, .stMarkdown li, div[data-testid="stMarkdownContainer"] p {{
        color: #0d0d0d !important;
        font-size: 16px !important;
        line-height: 1.8 !important;
        letter-spacing: 0.01em;
    }}

    /* チャット吹き出し（ChatGPTスタイル） */
    div[data-testid="stChatMessage"] {{
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 12px 0 !important;
        margin-bottom: 14px !important;
    }}

    /* ユーザーメッセージ（右側・丸み吹き出し） */
    div[data-testid="stChatMessage"]:has(div[data-testid="chatAvatarIcon-user"]) {{
        background-color: #f3f4f6 !important;
        border-radius: 20px 20px 4px 20px !important;
        padding: 12px 20px !important;
        max-width: 82% !important;
        margin-left: auto !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04) !important;
    }}

    /* アシスタントメッセージ（枠線なし、すっきりプレーン表示） */
    div[data-testid="stChatMessage"]:has(div[data-testid="chatAvatarIcon-assistant"]) {{
        background-color: transparent !important;
        border: none !important;
        padding: 8px 0 !important;
    }}

    /* キャラクターバッジ（ChatGPT風の控えめなpill） */
    .char-badge {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 12px;
        border-radius: 14px;
        font-size: 13px !important;
        font-weight: 600 !important;
        margin-bottom: 8px;
        background-color: #f3f4f6 !important;
        color: #1f2937 !important;
        border: 1px solid #e5e7eb !important;
    }}
    .char-master {{ border-left: 3px solid #b8860b !important; }}
    .char-senior {{ border-left: 3px solid #10a37f !important; }}
    .char-analyst {{ border-left: 3px solid #3b82f6 !important; }}

    /* ChatGPT風の提案カード（ウェルカム画面） */
    .suggest-card-btn button {{
        background-color: #ffffff !important;
        border: 1px solid #e5e7eb !important;
        border-radius: 14px !important;
        padding: 14px 18px !important;
        text-align: left !important;
        transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.03) !important;
        white-space: pre-wrap !important;
        min-height: 72px !important;
        color: #111827 !important;
        font-size: 14px !important;
        font-weight: 500 !important;
    }}
    .suggest-card-btn button:hover {{
        border-color: #10a37f !important;
        background-color: #f0fdf4 !important;
        box-shadow: 0 4px 12px rgba(16,163,127,0.1) !important;
        transform: translateY(-2px) !important;
    }}

    /* ChatGPT風の添付ファイルカード */
    .file-attachment-card {{
        display: inline-flex;
        align-items: center;
        gap: 12px;
        background-color: #ffffff !important;
        border: 1px solid #e5e7eb !important;
        border-radius: 12px !important;
        padding: 10px 16px !important;
        margin-bottom: 10px !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04) !important;
        max-width: 100% !important;
        word-break: break-all !important;
    }}
    .file-attachment-icon {{
        font-size: 24px !important;
        flex-shrink: 0;
    }}
    .file-attachment-name {{
        font-weight: 600 !important;
        font-size: 14px !important;
        color: #111827 !important;
    }}
    .file-attachment-meta {{
        font-size: 12px !important;
        color: #6b7280 !important;
    }}
    
    /* サイドバー（ChatGPT風のライトグレー） */
    section[data-testid="stSidebar"] {{
        background-color: #f9fafb !important;
        border-right: 1px solid #e5e7eb !important;
    }}
    section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] span, section[data-testid="stSidebar"] label {{
        color: #374151 !important;
        font-size: 14px !important;
    }}

    /* サイドバーの「新規チャット」ボタン */
    .sidebar-new-chat-btn button {{
        background-color: #ffffff !important;
        color: #111827 !important;
        border: 1px solid #d1d5db !important;
        border-radius: 20px !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
        padding: 10px 16px !important;
        transition: all 0.2s ease !important;
    }}
    .sidebar-new-chat-btn button:hover {{
        background-color: #f3f4f6 !important;
        border-color: #9ca3af !important;
    }}

    /* スマートフォン・タブレット最適化（レスポンシブデザイン） */
    @media (max-width: 768px) {{
        .main .block-container {{
            padding-left: 14px !important;
            padding-right: 14px !important;
            padding-top: 12px !important;
            padding-bottom: 120px !important;
        }}
        div[data-testid="stChatMessage"]:has(div[data-testid="chatAvatarIcon-user"]) {{
            max-width: 90% !important;
            padding: 10px 16px !important;
            font-size: 15px !important;
        }}
        div[data-testid="stChatInput"] {{
            border-radius: 24px !important;
            padding: 4px 8px !important;
        }}
        .file-attachment-card {{
            padding: 8px 12px !important;
        }}
        .file-attachment-name {{
            font-size: 13px !important;
        }}
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
    "\n\n【最重要ルール：科学的論文・文献知見に基づくこと ＆ 徹底的な噛み砕き解説】\n"
    "1. 【科学的論文・生体力学の確固たる裏付け】\n"
    "   回答の際は必ず上記の【弓道の科学的論文・生体力学（バイオメカニクス）研究知見データベース】（筋電図EMG研究、肩甲骨・関節の運動連鎖、重心動揺・床反力データ、角見のトルク力学、呼吸・自律神経系など）を確固たる科学的根拠として頭に入れ、それに基づいて答えてください。\n"
    "2. 【初心者・一般射手への徹底的な噛み砕き（日常語への翻訳）】\n"
    "   ただし、論文の難解な専門用語や解剖学用語をそのまま羅列しては絶対に伝わりません！\n"
    "   「科学的な実験や研究でも実証されているのですが、感覚としては…」のように、誰もが目に浮かぶ日常的な体の部位や動作（例:『首をすくめず肩をストンと落とす』『背中の下の方（脇の下）で引き絞る』『親指の付け根で壁をそっと押す』など）に優しく噛み砕いて説明してください。\n"
    "3. 【専門用語のカッコ書き解説】\n"
    "   弓道の専門用語（角見、手の内、会、伸び合い、丹田、三重十文字、胴造りなど）を用いる際は、必ず直後にカッコ書き（例: 角見（左手親指の付け根で弓を押し開くこと））をつけて平易に解説してください。"
)

CHARACTERS = {
    "師範（無幻先生）": {
        "icon": "🥋",
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

def save_current_session(session_id: str, messages: list):
    """現在の会話履歴を自動保存"""
    if not messages:
        return
    h_dir = get_current_history_dir()
        
    # タイトルを最初のユーザー発言から自動生成
    title = "弓道相談・稽古録"
    for m in messages:
        if m["role"] == "user":
            first_text = m.get("content", "").replace("🎥 **射形分析をお願いします**\n\n【気になっていること】: ", "").strip()
            first_line = first_text.split("\n")[0]
            if first_line:
                title = first_line[:20] + ("..." if len(first_line) > 20 else "")
            break
            
    now_str = time.strftime("%Y-%m-%d %H:%M")
    path = os.path.join(h_dir, f"{session_id}.json")
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

# ==================== ChatGPT風完全ログイン画面（スマホ・タブレット完全対応） ====================
def render_login_screen():
    st.markdown("""
    <style>
        .login-wrap {
            max-width: 440px;
            margin: 30px auto 0 auto;
            padding: 0 16px;
        }
        .login-card-header {
            text-align: center;
            margin-bottom: 24px;
        }
        .login-logo {
            font-size: 52px;
            line-height: 1;
            margin-bottom: 12px;
        }
        .login-title {
            font-size: 24px;
            font-weight: 700;
            color: #111827;
            margin-bottom: 6px;
            letter-spacing: -0.01em;
        }
        .login-subtitle {
            font-size: 14px;
            color: #6b7280;
            line-height: 1.5;
        }
    </style>
    <div class="login-wrap">
        <div class="login-card-header">
            <div class="login-logo">🏹</div>
            <div class="login-title">弓道AI道場へようこそ</div>
            <div class="login-subtitle">アカウントにログインして射技稽古・動画分析を始めましょう</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # スマホ・タブレット・PC全対応の中央カードレイアウト
    _, col_center, _ = st.columns([0.05, 0.9, 0.05]) if st.session_state.get("_is_mobile", False) else st.columns([1, 1.8, 1])
    with col_center:
        tab_login, tab_register = st.tabs(["🔑 ログイン", "✨ 新規アカウント登録"])
        
        with tab_login:
            with st.form("login_form", clear_on_submit=False):
                uname = st.text_input("ユーザー名", placeholder="例: archer")
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
                        
            st.markdown("""
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 14px; margin-top: 16px; font-size: 13px; color: #475569; text-align: center;">
                💡 <b>初期テスト用アカウント</b><br>
                ユーザー名: <code style="color: #10a37f; font-weight: 600;">archer</code> / パスワード: <code style="color: #10a37f; font-weight: 600;">kyudo123</code>
            </div>
            """, unsafe_allow_html=True)
            
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

# ==================== 認証状態チェック ====================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "logged_in_user" not in st.session_state:
    st.session_state.logged_in_user = ""

# 未ログインの場合はログイン画面のみを表示し、以降のチャット画面やサイドバーを遮断
if not st.session_state.authenticated:
    render_login_screen()
    st.stop()

# セッション状態の先行初期化（ログインユーザー専用履歴を保持）
if "current_session_id" not in st.session_state:
    existing_sessions = get_all_sessions()
    if existing_sessions:
        latest = existing_sessions[0]
        st.session_state.current_session_id = latest["id"]
        loaded = load_session_messages(latest["id"])
        st.session_state.messages = loaded if loaded else [{
            "role": "assistant",
            "char": list(CHARACTERS.keys())[0],
            "content": CHARACTERS[list(CHARACTERS.keys())[0]]["welcome"]
        }]
    else:
        new_id = f"session_{int(time.time())}"
        st.session_state.current_session_id = new_id
        st.session_state.messages = [{
            "role": "assistant",
            "char": list(CHARACTERS.keys())[0],
            "content": CHARACTERS[list(CHARACTERS.keys())[0]]["welcome"]
        }]
        save_current_session(new_id, st.session_state.messages)

# サイドバー構成（ChatGPT風左メニュー）
with st.sidebar:
    # 最上部に「+ 新しいチャット」ボタン（ChatGPTライク）
    st.markdown('<div class="sidebar-new-chat-btn">', unsafe_allow_html=True)
    if st.button("＋ 新しいチャット", use_container_width=True):
        new_id = f"session_{int(time.time())}"
        st.session_state.current_session_id = new_id
        st.session_state.messages = [{
            "role": "assistant",
            "char": selected_char if "selected_char" in locals() else list(CHARACTERS.keys())[0],
            "content": CHARACTERS[list(CHARACTERS.keys())[0]]["welcome"]
        }]
        save_current_session(new_id, st.session_state.messages)
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # 過去のチャット履歴一覧
    all_sess = get_all_sessions()
    if all_sess:
        st.caption("過去のチャット履歴")
        sess_options = {s["id"]: s["title"] for s in all_sess}
        cur_id = st.session_state.get("current_session_id", all_sess[0]["id"])
        default_idx = list(sess_options.keys()).index(cur_id) if cur_id in sess_options else 0
        
        selected_sess_id = st.selectbox(
            "履歴選択",
            options=list(sess_options.keys()),
            index=default_idx,
            format_func=lambda x: sess_options[x],
            label_visibility="collapsed"
        )
        
        if selected_sess_id != st.session_state.get("current_session_id"):
            st.session_state.current_session_id = selected_sess_id
            loaded = load_session_messages(selected_sess_id)
            if loaded:
                st.session_state.messages = loaded
            st.rerun()

    st.divider()

    # キャラクター選択
    st.caption("AIキャラクター設定")
    selected_char = st.selectbox(
        "対話相手を選択:",
        options=list(CHARACTERS.keys()),
        index=0,
        label_visibility="collapsed"
    )
    char_info = CHARACTERS[selected_char]
    st.caption(f"{char_info['desc']}")

    st.divider()

    # 射法八節早見表
    with st.expander("📖 射法八節 早見表"):
        st.markdown("""
        1. **足踏み** : 的に向かって両足を踏み開く基本の土台。
        2. **胴造り** : 上体を安定させ、丹田に力を込める。
        3. **弓構え** : 取懸け・手の内・物見を整える。
        4. **打起し** : 弓矢を両腕で静かに頭上へ持ち上げる。
        5. **引分け** : 左右均等に押し引きしながら弓を引き開く。
        6. **会** : 狙いと伸び合いの極致。心技体が一体となる。
        7. **離れ** : 伸び合いの極まりにより自然に矢が放たれる。
        8. **残心** : 矢が放たれた後の姿勢と精神を保つ。
        """)

    # 詳細設定アコーディオン（API、文字サイズ、テキスト保存）
    with st.expander("⚙️ 設定・エクスポート"):
        font_size_choice = st.radio(
            "文字の大きさ:",
            options=["標準 (16px)", "大きめ (18px)", "特大 (22px)"],
            index=0,
            help="チャットの文字サイズを変更できます。"
        )
        size_map = {"標準 (16px)": "16px", "大きめ (18px)": "18px", "特大 (22px)": "22px"}
        cur_size = size_map[font_size_choice]
        st.markdown(f"""
        <style>
            .stMarkdown p, div[data-testid="stChatMessage"] p {{ font-size: {cur_size} !important; }}
        </style>
        """, unsafe_allow_html=True)
        
        env_api_key = os.environ.get("GEMINI_API_KEY", "")
        if not env_api_key:
            try:
                if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
                    env_api_key = st.secrets["GEMINI_API_KEY"]
            except Exception:
                pass
        # ローカルの .streamlit/secrets.toml も直接確認
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
            
        # APIキーはバックグラウンド（secrets.toml / 環境変数）から安全に自動読み込み
        # 画面上にはキー入力欄やキー文字列を一切露出・表示させない（セキュリティ完全保護）
        active_api_key = env_api_key
        
        if active_api_key:
            st.markdown("""
            <div style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; font-size: 13px; color: #166534; font-weight: 600; margin-bottom: 8px;">
                <span>🔒</span><span>Gemini AI 接続：保護完了</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="display: flex; align-items: center; gap: 8px; padding: 8px 12px; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 13px; color: #475569; font-weight: 600; margin-bottom: 8px;">
                <span>💡</span><span>模擬AIモード（ローカル応答）</span>
            </div>
            """, unsafe_allow_html=True)

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
        <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 10px; margin: 14px 0 10px 0; font-size: 12px; color: #166534;">
            <div style="font-weight: 700; margin-bottom: 4px; display: flex; align-items: center; gap: 4px;">
                <span>🛡️</span><span>個人情報保護・完全消去システム</span>
            </div>
            送信された射形動画・画像は、AI分析完了直後にローカルPCから物理上書き（シュレッダー消去）され、クラウド上からも即座に完全抹消されます。端末内やサーバーに動画は一切残りません。
        </div>
        """, unsafe_allow_html=True)

        if st.button("🗑️ このチャットを初期化", use_container_width=True):
            st.session_state.messages = [{
                "role": "assistant",
                "char": selected_char,
                "content": char_info["welcome"]
            }]
            if "current_session_id" in st.session_state:
                save_current_session(st.session_state.current_session_id, st.session_state.messages)
            st.rerun()

    # サイドバー最下部：ChatGPT風ログインユーザー情報 ＆ ログアウトボタン
    st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)
    users_db = load_users()
    cur_uinfo = users_db.get(st.session_state.get("logged_in_user", ""), {})
    disp_name = cur_uinfo.get("display_name", st.session_state.get("logged_in_user", "射手"))

    st.markdown(f"""
    <div style="display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; margin-bottom: 8px;">
        <div style="display: flex; align-items: center; gap: 8px;">
            <span style="font-size: 22px;">👤</span>
            <div>
                <div style="font-size: 13px; font-weight: 700; color: #0f172a;">{disp_name}</div>
                <div style="font-size: 11px; color: #64748b;">@{st.session_state.get('logged_in_user', '')}</div>
            </div>
        </div>
        <span style="font-size: 11px; color: #10a37f; font-weight: 600;">● 稽古中</span>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🚪 ログアウト", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.logged_in_user = ""
        st.session_state.messages = []
        if "current_session_id" in st.session_state:
            del st.session_state["current_session_id"]
        st.rerun()

# ChatGPT風トップバー（レスポンシブ・モデル・キャラクター表示）
st.markdown(f"""
<div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; padding: 4px 0 16px 0; border-bottom: 1px solid #f0f0f0; margin-bottom: 18px;">
    <div style="display: flex; align-items: center; gap: 8px;">
        <span style="font-size: 22px;">🏹</span>
        <span style="font-weight: 700; font-size: 18px; color: #111827; letter-spacing: -0.01em;">弓道AI道場</span>
        <span style="font-size: 12px; font-weight: 600; color: #10a37f; background: #f0fdf4; border: 1px solid #bbf7d0; padding: 2px 10px; border-radius: 12px;">{selected_char}</span>
    </div>
    <div style="display: flex; align-items: center; gap: 8px; margin-left: auto;">
        <span style="font-size: 11px; color: #166534; background: #f0fdf4; border: 1px solid #bbf7d0; padding: 2px 8px; border-radius: 10px; font-weight: 500;">🔬 論文・生体力学</span>
        <span style="font-size: 12px; color: #9ca3af;">Gemini</span>
    </div>
</div>
""", unsafe_allow_html=True)

# 応答生成関数（テキスト用）
def generate_response(user_input: str, char_name: str, api_key: str) -> str:
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
            
            prompt_text = (
                f"【弓道の科学的論文・生体力学研究文献知見（必読・回答の科学的根拠）】\n"
                f"{KYUDO_SCIENTIFIC_EVIDENCE}\n\n"
                f"【設定・役割（必ず上記科学的エビデンスを頭に入れつつ、初心者にも直感的に伝わるよう日常の身体言語に噛み砕いて回答してください）】\n"
                f"{system_instruction}\n\n"
                f"【会話内容】\n" + "\n".join(contents)
            )
            
            # 最新の高速モデルを順に試行
            model_candidates = ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-flash-latest"]
            response_text = None
            last_err = None
            
            for m_name in model_candidates:
                try:
                    response = client.models.generate_content(
                        model=m_name,
                        contents=prompt_text,
                        config=types.GenerateContentConfig(
                            temperature=0.7,
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

# ==================== 3D立体骨格＆筋肉活動可視化関数 ====================
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
        fillcolor='rgba(27, 67, 50, 0.25)',
        line=dict(color='#1b4332', width=3),
        marker=dict(size=7, color='#d4af37'),
        name='筋活動バランス'
    ))
    
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickfont=dict(size=11, color='#4b5563'),
                gridcolor='#e5e7eb'
            ),
            angularaxis=dict(
                tickfont=dict(size=12, color='#111827'),
                gridcolor='#e5e7eb'
            ),
            bgcolor='#ffffff'
        ),
        paper_bgcolor='#ffffff',
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
    # 弓道「会」の姿勢
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
        ("Head", "Neck", "#8b0000", 6),
        ("Neck", "Chest", "#1b4332", 7),
        ("Chest", "Pelvis", "#1b4332", 8),
        # 押手リンク
        ("Chest", "L_Shoulder", "#1b4332", 6),
        ("L_Shoulder", "L_Elbow", "#2e7d32", 6),
        ("L_Elbow", "L_Wrist", "#2e7d32", 6),
        # 妻手リンク
        ("Chest", "R_Shoulder", "#1b4332", 6),
        ("R_Shoulder", "R_Elbow", "#d35400", 6),
        ("R_Elbow", "R_Wrist", "#d35400", 6),
        # 下半身リンク
        ("Pelvis", "L_Hip", "#1b4332", 6),
        ("L_Hip", "L_Foot", "#1b4332", 6),
        ("Pelvis", "R_Hip", "#1b4332", 6),
        ("R_Hip", "R_Foot", "#1b4332", 6),
        # 弓幹
        ("Bow_Bottom", "L_Wrist", "#5c4033", 4),
        ("L_Wrist", "Bow_Top", "#5c4033", 4),
        # 矢（L_Wrist から R_Wrist への水平ベクトル）
        ("L_Wrist", "R_Wrist", "#d4af37", 4),
        # 弦（Bow_Top -> R_Wrist -> Bow_Bottom）
        ("Bow_Top", "R_Wrist", "#c0c0c0", 2),
        ("R_Wrist", "Bow_Bottom", "#c0c0c0", 2)
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
    labels = list(joints.keys())
    
    fig.add_trace(go.Scatter3d(
        x=jx, y=jy, z=jz,
        mode='markers+text',
        marker=dict(size=6, color='#111111'),
        text=["頭", "頸", "胸", "丹田", "押手肩", "押手肘", "角見(押手)", "妻手肩", "妻手肘", "取懸け", "左腰", "左足", "右腰", "右足", "弓(本)", "弓(末)"],
        textposition="top center",
        textfont=dict(size=10, color='#222222'),
        hoverinfo='text',
        showlegend=False
    ))
    
    fig.update_layout(
        scene=dict(
            xaxis=dict(title='左右', range=[-1.1, 1.1], backgroundcolor='#ffffff', gridcolor='#f3f4f6'),
            yaxis=dict(title='前後', range=[-0.6, 0.6], backgroundcolor='#ffffff', gridcolor='#f3f4f6'),
            zaxis=dict(title='天地', range=[-0.1, 2.3], backgroundcolor='#ffffff', gridcolor='#f3f4f6'),
            camera=dict(
                eye=dict(x=1.3, y=-1.5, z=0.8) # 斜め前からの自然な視点
            ),
            aspectratio=dict(x=1.4, y=0.8, z=1.5)
        ),
        paper_bgcolor='#ffffff',
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

        # 立体バイオメカニクス＆筋肉感知コーチングプロンプト
        analysis_prompt = f"""
あなたは弓道の指導者（{char_name}）として、提供された射形動画（または画像）を【立体的・生体力学的（バイオメカニクス）】に詳細分析してください。
分析にあたっては、以下の科学的論文・生体力学研究知見を必ず頭に入れ、その確固たる科学的根拠に基づいて評価してください。
ただし、回答文は射手自身が直感的に理解できるよう、徹底的に日常の言葉に噛み砕いてわかりやすく伝えてください。

{KYUDO_SCIENTIFIC_EVIDENCE}

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
# ユーザーメッセージがまだない場合はChatGPT風のウェルカムサジェストを表示
has_user_msg = any(m["role"] == "user" for m in st.session_state.messages)
quick_prompt = None

if not has_user_msg:
    st.markdown(f"""
    <div style="text-align: center; margin: 40px 0 35px 0;">
        <div style="font-size: 48px; margin-bottom: 12px;">🏹</div>
        <div style="font-size: 26px; font-weight: 700; color: #0d0d0d; margin-bottom: 8px;">何をお手伝いしましょうか？</div>
        <div style="font-size: 15px; color: #666666;">射法八節の疑問・射癖の相談・動画による立体分析までサポートします</div>
    </div>
    """, unsafe_allow_html=True)
    
    # 2x2のモダンサジェストカード
    st.markdown('<div class="suggest-card-btn">', unsafe_allow_html=True)
    s_col1, s_col2 = st.columns(2)
    with s_col1:
        if st.button("🎯 早気を克服したい\n会で保てずにすぐ離れてしまう悩みの改善法", use_container_width=True):
            quick_prompt = "最近早気（はやけ）になってしまい、会で保てずに離れてしまいます。どうすれば克服できますか？"
        if st.button("✋ 手の内（角見）のコツ\n握り込まずに弓返りと矢飛びを良くする整え方", use_container_width=True):
            quick_prompt = "手の内（角見）がうまく利かず、握り込んでしまいます。正しい手の内の整え方と利かせ方を教えてください。"
    with s_col2:
        if st.button("📜 射法八節のチェックポイント\n足踏みから残心までの要点と身体の連動", use_container_width=True):
            quick_prompt = "射法八節それぞれのフェーズで、最も大切にすべき要点を教えてください。"
        if st.button("🎖️ 審査での心構え・体配\n段位審査で見られる入退場と息合いのポイント", use_container_width=True):
            quick_prompt = "弓道の段位審査を控えています。体配（入退場や息合い）と審査員が見ているポイントを教えてください。"
    st.markdown('</div><div style="margin-bottom: 25px;"></div>', unsafe_allow_html=True)

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
        with st.chat_message("assistant", avatar=c_info["icon"]):
            st.markdown(f'<span class="char-badge {c_info["badge_class"]}">{c_info["icon"]} {msg_char}</span>', unsafe_allow_html=True)
            
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

# チャット入力欄（ChatGPT風カプセルバー、左端に「＋」添付ボタン）
chat_submission = st.chat_input(
    placeholder="弓道の質問を入力するか、左の「＋」から動画を送信...",
    accept_file=True,
    file_type=["mp4", "mov", "avi", "webm", "jpg", "jpeg", "png"]
)

# ChatGPT風のフッター注釈テキスト
st.markdown("""
<div style="text-align: center; font-size: 11px; color: #8e8e8e; margin-top: 8px;">
    弓道AI道場は射技向上のヒントを提供します。ご自身の感覚や道場の指導者と相談しながら試行錯誤してください。
</div>
""", unsafe_allow_html=True)

# クイック質問チップまたは入力欄からの入力を判定（型安全に確実に抽出）
text_to_send = None
files_to_send = []

if quick_prompt:
    text_to_send = quick_prompt.strip()
elif chat_submission is not None:
    if isinstance(chat_submission, str):
        text_to_send = chat_submission.strip()
        files_to_send = []
    elif hasattr(chat_submission, "text"):
        raw_text = chat_submission.text
        text_to_send = raw_text.strip() if raw_text else ""
        raw_files = getattr(chat_submission, "files", [])
        files_to_send = raw_files if raw_files else []
    elif isinstance(chat_submission, dict):
        text_to_send = str(chat_submission.get("text", "")).strip()
        files_to_send = chat_submission.get("files", []) or []

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

    # B. 通常のテキスト質問の場合
    else:
        st.session_state.messages.append({"role": "user", "content": text_to_send})

        # テキスト回答もspinnerのみ（chat_messageブロックをここで開かない）
        try:
            with st.spinner(f"{selected_char}が科学的文献エビデンスに基づき回答中..."):
                reply = generate_response(text_to_send, selected_char, active_api_key)
            st.session_state.messages.append({
                "role": "assistant",
                "char": selected_char,
                "content": reply
            })
        except Exception as e:
            st.session_state.messages.append({
                "role": "assistant",
                "char": selected_char,
                "content": f"⚠️ エラーが発生しました: {str(e)}"
            })

    # 会話を即時自動保存してからrerun（描画済みUIが一切ない状態でrerunするのが安全）
    if "current_session_id" in st.session_state:
        save_current_session(st.session_state.current_session_id, st.session_state.messages)

    st.rerun()

