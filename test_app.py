import streamlit as st

st.set_page_config(page_title="Test", page_icon="🏹")

st.title("🏹 起動テスト")

try:
    import plotly.graph_objects as go
    st.success("✅ plotly OK")
except Exception as e:
    st.error(f"❌ plotly ERROR: {e}")

try:
    from google import genai
    st.success("✅ google-genai OK")
except Exception as e:
    st.error(f"❌ google-genai ERROR: {e}")

try:
    api_key = st.secrets["GEMINI_API_KEY"]
    st.success(f"✅ API Key 取得OK（先頭5文字: {api_key[:5]}...）")
except Exception as e:
    st.error(f"❌ Secrets ERROR: {e}")

st.info("テスト完了！本番appに戻します。")
