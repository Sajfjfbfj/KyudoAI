"""開発者専用：Supabase / ローカル学習ログからフィードバック一覧を logs/developer_feedback_log.md に出力するスクリプト"""
import json
import os
import time
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SECRETS_PATH = os.path.join(BASE_DIR, ".streamlit", "secrets.toml")
LOCAL_LOGS_PATH = os.path.join(BASE_DIR, "data", "learning_logs.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "logs")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "developer_feedback_log.md")


def _load_supabase_config() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_KEY", "").strip()
    if (not url or not key) and os.path.exists(SECRETS_PATH):
        try:
            import tomllib
            with open(SECRETS_PATH, "rb") as fp:
                data = tomllib.load(fp)
            url = url or str(data.get("SUPABASE_URL", "") or "").strip()
            key = key or str(data.get("SUPABASE_KEY", "") or "").strip()
        except Exception:
            pass
    url = url.rstrip("/")
    if url.endswith("/rest/v1"):
        url = url[:-8].rstrip("/")
    return url, key


def _fetch_supabase_feedback_logs(url: str, key: str) -> list[dict] | None:
    if not url or not key:
        return None
    full_url = f"{url}/rest/v1/yumiqa_learning_logs?feedback=neq.&order=created_at.desc&limit=500"
    if not full_url.startswith("https://"):
        return None
    headers = {
        "apikey": key,
        "Content-Type": "application/json",
    }
    if not key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(full_url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310 – https:// に限定済み
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw else []
            return data if isinstance(data, list) else None
    except Exception:
        return None


def _load_local_feedback_logs() -> list[dict]:
    if not os.path.exists(LOCAL_LOGS_PATH):
        return []
    try:
        with open(LOCAL_LOGS_PATH, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        if not isinstance(data, list):
            return []
        return [r for r in reversed(data) if (r.get("feedback") or "").strip()]
    except Exception:
        return []


def _esc_md(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()


def write_developer_feedback_markdown(rows: list[dict], source_label: str) -> str:
    """フィードバック一覧を専用 Markdown ログファイルへ書き出す"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    good_rows = [r for r in rows if r.get("feedback") == "good"]
    bad_rows = [r for r in rows if r.get("feedback") == "bad"]
    noted_bad = [r for r in bad_rows if (r.get("feedback_note") or "").strip()]

    lines = [
        "# YUMIQA 開発者専用 フィードバック一覧ログ",
        "",
        f"- **最終更新**: {now_str}",
        f"- **取得元**: {source_label}",
        f"- **合計**: {len(rows)} 件（👍 高評価: {len(good_rows)} 件 / 👎 低評価: {len(bad_rows)} 件 / 📝 改善メモあり: {len(noted_bad)} 件）",
        "",
        "> ※ このファイルは `.gitignore` 対象のローカル専用ファイルです。ユーザーには表示されません。",
        "",
        "## 📝 改善要望・メモ一覧（👎 コメント付き）",
        "",
    ]

    if noted_bad:
        for r in noted_bad:
            dt = _esc_md(r.get("created_at", ""))
            ch = _esc_md(r.get("char_name", "")) or "-"
            q = _esc_md(r.get("query_summary", "")) or "（質問記録なし）"
            note = _esc_md(r.get("feedback_note", ""))
            lines.append(f"- **[{dt}]** ({ch}) **要望:** `{note}` ／ 質問: {q}")
    else:
        lines.append("- （現在、改善メモ付きのフィードバックはありません）")

    lines.extend([
        "",
        "## 📋 全フィードバック履歴",
        "",
        "| 日時 | 評価 | モード | キャラ | 質問概要 | 改善メモ | log_id |",
        "|---|---|---|---|---|---|---|",
    ])

    if rows:
        for r in rows:
            dt = _esc_md(r.get("created_at", ""))
            fb = "👍" if r.get("feedback") == "good" else ("👎" if r.get("feedback") == "bad" else _esc_md(r.get("feedback", "")))
            mode = _esc_md(r.get("mode", "")) or "-"
            ch = _esc_md(r.get("char_name", "")) or "-"
            q = _esc_md(r.get("query_summary", ""))[:80] or "-"
            note = _esc_md(r.get("feedback_note", "")) or "-"
            lid = _esc_md(r.get("log_id", ""))
            lines.append(f"| {dt} | {fb} | {mode} | {ch} | {q} | {note} | `{lid}` |")
    else:
        lines.append("| - | - | - | - | （フィードバックデータなし） | - | - |")

    content = "\n".join(lines) + "\n"
    with open(OUTPUT_FILE, "w", encoding="utf-8") as fp:
        fp.write(content)
    return OUTPUT_FILE


def main() -> int:
    url, key = _load_supabase_config()
    rows = _fetch_supabase_feedback_logs(url, key)
    if rows is not None:
        source_label = "Supabase (`yumiqa_learning_logs`)"
    else:
        rows = _load_local_feedback_logs()
        source_label = "ローカル (`data/learning_logs.json`)"
    out_path = write_developer_feedback_markdown(rows, source_label)
    print(f"✅ 出力完了: {out_path} ({len(rows)} 件, 取得元: {source_label})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
