import os
import re

def update_menus():
    with open('app.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. サイドバー（メニューバー）の置き換え
    pos_sb = content.find('with st.sidebar:')
    pos_env = content.find('# APIキーの安全な読み込み')

    if pos_sb == -1 or pos_env == -1:
        print("Error: Sidebar markers not found.")
        return

    new_sidebar = '''with st.sidebar:
    # ── ブランドロゴ（Gemini / ChatGPT風ヘッダー） ───────────────
    st.markdown("""
    <div class="sb-brand">
        <span>🏹</span>
        <div>
            <div style="font-size: 16px; font-weight: 800; line-height: 1.2; color: #0f172a;">弓道AI道場</div>
            <div style="font-size: 11px; font-weight: 500; color: #64748b;">Gemini & ChatGPT スタイル</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── 1. 新しいチャット（最重要・最優先アクション） ───────────
    if st.button("＋ 新しい会話", key="sidebar_new_chat_btn", use_container_width=True, type="primary"):
        new_id = f"session_{int(time.time())}"
        st.session_state.current_session_id = new_id
        st.session_state.messages = []
        st.rerun()

    st.markdown("<div style='margin-top: 14px;'></div>", unsafe_allow_html=True)

    # ── 2. キャラクター（指導陣 / モデル）切り替え ─────────────
    cur_c = st.session_state.get("current_selected_char", list(CHARACTERS.keys())[0])
    char_names = list(CHARACTERS.keys())
    cur_idx = char_names.index(cur_c) if cur_c in char_names else 0

    st.markdown("<div class='sb-section-label'>キャラクター（指導陣）</div>", unsafe_allow_html=True)
    selected_char_sb = st.selectbox(
        "キャラクター選択",
        options=char_names,
        index=cur_idx,
        key="sb_char_select",
        label_visibility="collapsed"
    )
    if selected_char_sb != cur_c:
        switch_ai_character(selected_char_sb)
        st.rerun()

    # 選択中キャラクターのガイドカード
    c_info = CHARACTERS[cur_c]
    st.markdown(f"""
    <div style="background: rgba(15,23,42,0.03); border: 1px solid rgba(15,23,42,0.06); border-radius: 12px; padding: 10px 12px; margin-bottom: 12px;">
        <div style="font-size: 13px; font-weight: 700; color: #0f172a; display: flex; align-items: center; gap: 6px;">
            <span>{c_info['icon']}</span><span>{cur_c}</span>
        </div>
        <div style="font-size: 11.5px; color: #64748b; line-height: 1.5; margin-top: 4px;">
            {c_info['desc']}
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # ── 3. 過去の会話（Chat History） ─────────────────────────
    st.markdown("<div class='sb-section-label'>過去の会話</div>", unsafe_allow_html=True)
    all_sess = get_all_sessions()
    if all_sess:
        cur_id = st.session_state.get("current_session_id", all_sess[0]["id"])

        for group_name, group_items in group_sessions_by_date(all_sess[:30]).items():
            st.caption(f"📅 {group_name}")

            for sess in group_items:
                is_active = (sess["id"] == cur_id)

                if is_active:
                    col_btn, col_opt = st.columns([0.80, 0.20])
                    with col_btn:
                        st.button(sess["title"], key=f"sess_active_{sess['id']}", use_container_width=True)
                    with col_opt:
                        with st.popover("···", use_container_width=True):
                            st.caption("チャット設定")
                            rename_val = st.text_input("タイトル変更", value=sess["title"], key=f"ren_{sess['id']}")
                            if st.button("変更保存", key=f"b_ren_{sess['id']}", use_container_width=True):
                                rename_session(sess["id"], rename_val)
                                st.rerun()
                            if st.button("🗑️ 削除", key=f"b_del_{sess['id']}", use_container_width=True):
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
                    if st.button(sess["title"], key=f"sess_btn_{sess['id']}", use_container_width=True):
                        st.session_state.current_session_id = sess["id"]
                        loaded = load_session_messages(sess["id"])
                        if loaded is not None:
                            st.session_state.messages = loaded
                        st.rerun()
    else:
        st.markdown("<div style='font-size: 12px; color: #94a3b8; padding: 8px 10px;'>会話履歴はまだありません</div>", unsafe_allow_html=True)

    # ── 4. 便利な弓道ツール（折りたたみ） ─────────────────────
    with st.expander("📚 弓道教本・参考ツール", expanded=False):
        st.markdown("""
        <div style='font-size: 11.5px; color: #475569; line-height: 1.6;'>
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

    # ── 5. フッター：設定 ＆ アカウントメニュー ───────────────
    st.markdown('<div style="margin-top: auto; padding-top: 18px;"></div>', unsafe_allow_html=True)
    st.divider()

    col_sb_set, col_sb_user = st.columns([1, 1])
    with col_sb_set:
        with st.popover("⚙️ 設定", use_container_width=True):
            st.markdown("<div style='font-size: 14px; font-weight: 700; color: #0f172a; margin-bottom: 8px;'>⚙️ 設定メニュー</div>", unsafe_allow_html=True)
            tab_st_gen, tab_st_mem, tab_st_inst, tab_st_data = st.tabs(["基本", "🧠 カルテ", "🎯 指示", "💾 保存"])

            with tab_st_gen:
                font_size_choice = st.radio(
                    "文字サイズ:",
                    options=["標準 (16px)", "大きめ (18px)", "特大 (22px)"],
                    index=0,
                    key="sb_font_size_choice"
                )
                size_map = {"標準 (16px)": "16px", "大きめ (18px)": "18px", "特大 (22px)": "22px"}
                cur_size = size_map[font_size_choice]
                st.markdown(f"<style>.stMarkdown p, div[data-testid='stChatMessage'] p {{ font-size: {cur_size} !important; }}</style>", unsafe_allow_html=True)

                st.markdown("---")
                if st.button("🗑️ この会話をリセット", use_container_width=True, key="reset_chat_sb"):
                    st.session_state.messages = [{
                        "role": "assistant",
                        "char": cur_c,
                        "content": CHARACTERS[cur_c]["welcome"]
                    }]
                    if "current_session_id" in st.session_state:
                        save_current_session(st.session_state.current_session_id, st.session_state.messages)
                    st.rerun()

            with tab_st_mem:
                cur_user = st.session_state.get("logged_in_user", "default")
                st.caption("AIが対話から覚えた情報です。")
                user_notes = load_user_memory(cur_user)
                if user_notes:
                    for idx, note in enumerate(user_notes):
                        col_n1, col_n2 = st.columns([0.80, 0.20])
                        with col_n1:
                            st.markdown(f"<div style='font-size: 12px; padding: 3px 6px; background: rgba(15,23,42,0.04); border-radius: 4px; margin-bottom: 3px; color: #0f172a;'>📌 {note}</div>", unsafe_allow_html=True)
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

            with tab_st_inst:
                cur_user = st.session_state.get("logged_in_user", "default")
                st.caption("AIへの前提知識や希望スタイル")
                cur_ci = load_custom_instructions(cur_user)
                ci_prof = st.text_area("あなた自身について:", value=cur_ci.get("profile", ""), height=65, key="ci_p_pop")
                ci_p = st.text_area("AIの応答スタイル:", value=cur_ci.get("response_pref", ""), height=65, key="ci_r_pop")
                if st.button("指示を保存", use_container_width=True, key="save_ci_pop"):
                    save_custom_instructions(cur_user, ci_prof, ci_p)
                    st.success("保存しました！")
                    time.sleep(0.3)
                    st.rerun()

            with tab_st_data:
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
                <div style="background-color: rgba(37,99,235,0.08); border: 1px solid rgba(37,99,235,0.2); border-radius: 8px; padding: 10px; font-size: 11px; color: #2563eb; margin-top: 8px;">
                    🛡️ 動画・画像は分析直後に完全シュレッダー抹消されます。
                </div>
                """, unsafe_allow_html=True)

    with col_sb_user:
        users_db = load_users()
        cur_uinfo = users_db.get(st.session_state.get("logged_in_user", ""), {})
        disp_name = cur_uinfo.get("display_name", "runtyoma")
        with st.popover(f"👤 {disp_name}", use_container_width=True):
            st.markdown(f"""
            <div style="border: 1px solid rgba(15,23,42,0.08); border-radius: 12px; padding: 12px; margin-bottom: 10px; background: rgba(15,23,42,0.03);">
                <div style="font-size: 14px; font-weight: 700; color: #0f172a;">{disp_name}</div>
                <div style="font-size: 11px; color: #64748b;">弓道AI Pro 有効</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("🚪 ログアウト", use_container_width=True, key="btn_logout_sb"):
                st.session_state.authenticated = False
                st.session_state.logged_in_user = ""
                st.session_state.messages = []
                if "current_session_id" in st.session_state:
                    del st.session_state["current_session_id"]
                st.rerun()

'''

    content = content[:pos_sb] + new_sidebar + '\n' + content[pos_env:]

    # 2. メイン画面 トップバー（メニューバー）の置き換え
    pos_top = content.find('# ==================== 弓道AI道場 トップナビゲーション ====================')
    pos_gen = content.find('# 応答生成関数（テキスト用）')

    if pos_top == -1 or pos_gen == -1:
        print("Error: Topbar markers not found.")
        return

    new_topbar = '''# ==================== メイン画面 トップメニューバー（Gemini / ChatGPT スタイル） ====================
cur_char_val = st.session_state.get("current_selected_char", list(CHARACTERS.keys())[0])

with st.container(key="topbar"):
    top_c1, top_c2, top_c3 = st.columns([0.52, 0.28, 0.20])
    with top_c1:
        # キャラクター / モデル切り替えポップオーバー（ChatGPTの「GPT-4o ▾」、Geminiの「Gemini ▾」）
        with st.popover(f"{CHARACTERS[cur_char_val]['icon']} {cur_char_val} ▾", use_container_width=True):
            st.markdown("<div style='font-size: 13px; font-weight: 700; color: #0f172a; margin-bottom: 8px;'>AIキャラクター（指導陣）を選択</div>", unsafe_allow_html=True)
            for cname in CHARACTERS.keys():
                c_info_item = CHARACTERS[cname]
                is_active = (cname == cur_char_val)
                btn_prefix = "✓ " if is_active else "　 "
                if st.button(f"{btn_prefix}{c_info_item['icon']} {cname}", key=f"top_sel_{cname}", use_container_width=True, help=c_info_item["desc"]):
                    switch_ai_character(cname)
                    st.rerun()
    with top_c2:
        if st.button("＋ 新しい会話", key="top_new_chat_btn", icon=":material/edit_square:", use_container_width=True, help="新しいチャットを開始"):
            st.session_state.messages = []
            st.session_state.current_session_id = f"session_{int(time.time())}"
            st.rerun()
    with top_c3:
        with st.popover("⚙️ 設定", icon=":material/settings:", use_container_width=True):
            st.caption("クイック設定")
            top_font_choice = st.radio(
                "文字サイズ",
                options=["標準 (16px)", "大きめ (18px)", "特大 (22px)"],
                index=0,
                key="top_font_size_choice"
            )
            top_size_map = {"標準 (16px)": "16px", "大きめ (18px)": "18px", "特大 (22px)": "22px"}
            st.markdown(f"<style>.stMarkdown p, div[data-testid='stChatMessage'] p {{ font-size: {top_size_map[top_font_choice]} !important; }}</style>", unsafe_allow_html=True)
            if st.button("🗑️ 会話をクリア", key="top_clear_chat", use_container_width=True):
                st.session_state.messages = [{
                    "role": "assistant",
                    "char": cur_char_val,
                    "content": CHARACTERS[cur_char_val]["welcome"]
                }]
                if "current_session_id" in st.session_state:
                    save_current_session(st.session_state.current_session_id, st.session_state.messages)
                st.rerun()

selected_char = st.session_state.get("current_selected_char", list(CHARACTERS.keys())[0])
char_info = CHARACTERS[selected_char]
st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

'''

    content = content[:pos_top] + new_topbar + '\n' + content[pos_gen:]

    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)

    print("SUCCESS: Sidebar and Topbar menus have been updated to Gemini & ChatGPT standard!")

if __name__ == '__main__':
    update_menus()
