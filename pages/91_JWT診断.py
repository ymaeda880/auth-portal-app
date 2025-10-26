# pages/90_JWT診断.py
from __future__ import annotations
import time, hashlib, datetime as dt
import streamlit as st
import extra_streamlit_components as stx
import jwt

# ====== 設定（必要に応じて編集）======
COOKIE_NAME = "prec_sso"
JWT_ALGO    = "HS256"

# 期待値（発行側と合わせてください）
EXPECTED_ISS = "prec-auth"
EXPECTED_AUD = "prec-internal"

# ポータルURL（戻りリンク用・任意）
PORTAL_URL   = "/auth_portal"

st.set_page_config(page_title="JWT / Cookie 診断", page_icon="🧪", layout="wide")
st.title("🧪 JWT / Cookie 診断ページ")

# ====== ヘルパ ======
def human_time(epoch: int | float | None) -> str:
    if not epoch: return "-"
    try: return dt.datetime.fromtimestamp(int(epoch)).isoformat(sep=" ", timespec="seconds")
    except Exception: return str(epoch)

def decode_no_verify(token: str | None) -> tuple[dict, str | None]:
    if not token: return {}, None
    try:
        d = jwt.decode(token, options={"verify_signature": False, "verify_exp": False})
        return (d if isinstance(d, dict) else {}), None
    except Exception as e:
        return {}, f"{type(e).__name__}: {e}"

# ====== Cookie 取得 ======
cm = stx.CookieManager(key="cm_diag")
token = cm.get(COOKIE_NAME)

# ====== secrets の指紋表示（キーそのものは出さない）======
secret = st.secrets.get("AUTH_SECRET", "CHANGE_ME")
secret_fp = hashlib.sha256(secret.encode()).hexdigest()[:16]
st.caption(f"AUTH_SECRET fingerprint: `{secret_fp}`（両アプリで一致すること）")

# ====== 署名検証（厳格モード）======
strict_payload, strict_ok, strict_err = {}, False, None
if token:
    try:
        strict_payload = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGO],
            issuer=EXPECTED_ISS,
            audience=EXPECTED_AUD,
            options={"require": ["exp", "sub"]},
        )
        strict_ok = True
    except Exception as e:
        strict_ok, strict_err = False, f"{type(e).__name__}: {e}"

# ====== 署名検証（緩和モード：iss/aud 無効化）======
relaxed_payload, relaxed_ok, relaxed_err = {}, False, None
if token:
    try:
        relaxed_payload = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGO],
            options={"require": ["exp", "sub"], "verify_aud": False, "verify_iss": False},
        )
        relaxed_ok = True
    except Exception as e:
        relaxed_ok, relaxed_err = False, f"{type(e).__name__}: {e}"

# ====== 署名未検証デコード（中身だけ確認）======
raw, raw_err = decode_no_verify(token)
exp = raw.get("exp") if isinstance(raw, dict) else None
now = int(time.time())

# ====== 概要カード ======
cols = st.columns(3)
with cols[0]:
    st.metric("Cookie present", "Yes" if token else "No")
with cols[1]:
    st.metric("JWT valid (strict)", "True" if strict_ok else "False")
with cols[2]:
    st.metric("JWT valid (relaxed)", "True" if relaxed_ok else "False")

# ====== 詳細出力 ======
with st.expander("🔎 Cookie / JWT 概要", expanded=True):
    st.write({
        "cookie_name": COOKIE_NAME,
        "cookie_present": bool(token),
        "expected_iss": EXPECTED_ISS,
        "expected_aud": EXPECTED_AUD,
    })

with st.expander("🧾 厳格モードの結果（issuer/audience 検証あり）", expanded=not strict_ok):
    st.write({"ok": strict_ok, "error": strict_err})
    if strict_ok:
        st.json(strict_payload)

with st.expander("🧾 緩和モードの結果（issuer/audience 検証なし）", expanded=False):
    st.write({"ok": relaxed_ok, "error": relaxed_err})
    if relaxed_ok:
        st.json(relaxed_payload)

with st.expander("🧾 署名未検証デコード（参考：中身だけ）", expanded=False):
    st.write({"error": raw_err})
    st.json(raw or {})
    st.write({"exp_human": human_time(exp), "now_human": human_time(now),
              "seconds_until_expire": (exp - now) if isinstance(exp, int) else None})

# ====== 一致チェック（見える化）======
if raw:
    eq_cols = st.columns(2)
    with eq_cols[0]:
        st.write({
            "token.iss": raw.get("iss"),
            "equals_iss": (raw.get("iss") == EXPECTED_ISS)
        })
    with eq_cols[1]:
        st.write({
            "token.aud": raw.get("aud"),
            "equals_aud": (raw.get("aud") == EXPECTED_AUD)
        })

# ====== 操作ボタン ======
st.divider()
bcols = st.columns(3)
with bcols[0]:
    if st.button("🔐 ポータルを開く", key="btn_portal"):
        next_url = st.query_params.get("next") or st.experimental_get_query_params().get("next", [None])[0]
        if not next_url:
            # 自分自身に戻るのが自然
            next_url = st.request.base_url if hasattr(st, "request") else "/"
        st.markdown(
            f'<meta http-equiv="refresh" content="0; url={PORTAL_URL}?next={next_url}"/>',
            unsafe_allow_html=True,
        )
with bcols[1]:
    if st.button("🗑 Cookieだけ削除（prec_sso）", key="btn_del_cookie"):
        cm.delete(COOKIE_NAME, path="/")
        st.success("Cookie を削除しました。ページを再読み込みしてください。")
with bcols[2]:
    if st.button("🔁 再読込み", key="btn_rerun"):
        st.rerun()
