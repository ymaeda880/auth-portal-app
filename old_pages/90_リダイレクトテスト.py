# ============================================================
# 🌐 リダイレクトテストページ
# ============================================================
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Redirect Test", page_icon="🌐", layout="centered")
st.title("🌐 リダイレクトテスト")

target = "http://localhost/login_test/"

st.info(f"このページを開くと、自動的に以下のURLへ遷移します：\n\n👉 **{target}**")

# --- HTMLベースの自動遷移（2重保険） ---
redirect_html = f"""
<meta http-equiv="refresh" content="0.5; url={target}">
<script>
  // JavaScriptによる遷移（iframe対策）
  setTimeout(function() {{
    if (window.top !== window.self) {{
      window.top.location.href = "{target}";
    }} else {{
      window.location.href = "{target}";
    }}
  }}, 500);
</script>
"""

st.markdown(redirect_html, unsafe_allow_html=True)

# --- 手動リンク（フォールバック） ---
st.markdown(f"🔗 手動で移動 → [ここをクリック]({target})")
