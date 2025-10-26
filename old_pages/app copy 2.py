# auth_portal_app/app.py  — 修正版
from __future__ import annotations
import json, time, datetime as dt
from pathlib import Path
from typing import Dict, Any, List

import streamlit as st
import extra_streamlit_components as stx
import jwt
from werkzeug.security import check_password_hash, generate_password_hash

# ======================
# 設定
# ======================
APP_ROOT = Path(__file__).resolve().parent
DATA_DIR  = APP_ROOT / "data"
USERS_FILE = DATA_DIR / "users.json"
LOGIN_LOG  = DATA_DIR / "login_users.jsonl"  # 任意

COOKIE_NAME     = "prec_sso"
JWT_ALGO        = "HS256"
JWT_TTL_SECONDS = 60 * 60  # 1h
JWT_ISS         = "prec-auth"
JWT_AUD         = "prec-internal"
JWT_SECRET      = st.secrets.get("AUTH_SECRET", "CHANGE_ME")

PUBLIC_APPS = {
    "📢 Public Docs": "/public_docs",
    "🎨 Slide Viewer": "/slide_viewer",
}
PROTECTED_APPS = {
    "📝 Minutes": "/minutes",
    "🎨 Image Maker": "/image_maker",
    "🔒 Login Test": "/login_test",
}

# ======================
# ユーティリティ
# ======================
def load_users(path: Path = USERS_FILE) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) and "users" in d else {"users": {}}
    except FileNotFoundError:
        return {"users": {}}

def atomic_write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    tmp.replace(path)

def append_login_log(event: Dict[str, Any]) -> None:
    try:
        LOGIN_LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOGIN_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass

def safe_next(value: str | None, default: str = "/") -> str:
    if not value:
        return default
    v = value.strip()
    if v.startswith("/") and not v.startswith("//"):
        return v
    return default

def issue_jwt(sub: str, apps: List[str]) -> tuple[str, int]:
    now = int(time.time())
    exp = now + JWT_TTL_SECONDS
    payload = {"sub": sub, "apps": apps, "iss": JWT_ISS, "aud": JWT_AUD, "iat": now, "exp": exp}
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)
    return token, exp

# def verify_jwt(token: str | None):
#     if not token:
#         return None
#     try:
#         return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO], options={"require": ["exp","sub"]})
#     except Exception:
#         return None
    
# def verify_jwt(token: str | None):
#     if not token:
#         return None
#     try:
#         # iss/aud の厳格チェックをいったんオフにする（トラブルシュート用）
#         return jwt.decode(
#             token,
#             JWT_SECRET,
#             algorithms=[JWT_ALGO],
#             options={
#                 "require": ["exp", "sub"],
#                 "verify_aud": False,
#                 "verify_iss": False
#             }
#         )
#     except Exception as e:
#         print("JWT decode error:", e)
#         return None

def verify_jwt(token: str | None):
    if not token:
        return None
    try:
        return jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGO],
            audience="prec-internal",   # ← payloadのaudと一致
            issuer="prec-auth",          # ← payloadのissと一致
            options={"require": ["exp", "sub"]}
        )
    except Exception as e:
        print("JWT decode error:", e)
        return None
    
# ======================
# ページ本体
# ======================
st.set_page_config(page_title="Auth Portal", page_icon="🔐", layout="wide")
st.title("🔐 ポータル")

# ✅ CookieManager は1回だけ & 固有キーを付ける
cm = stx.CookieManager(key="cm_portal")

# next の取得
try:
    next_param = st.query_params.get("next", "/")  # Streamlit ≥1.32
except Exception:
    next_param = st.experimental_get_query_params().get("next", ["/"])[0]
next_url = safe_next(next_param, "/")

# 既存Cookie→ユーザー復元（1回だけ）
token_existing = cm.get(COOKIE_NAME)
payload_existing = verify_jwt(token_existing)

if payload_existing and "current_user" not in st.session_state:
    st.session_state["current_user"] = payload_existing.get("sub")

# --- 🔍 デバッグ出力ブロック ---
with st.expander("🔎 Cookie / JWT デバッグ情報", expanded=False):
    st.write({
        "cookie_present": bool(token_existing),
        "cookie_value": token_existing or "(なし)",
        "jwt_valid": bool(payload_existing),
        "jwt_payload": payload_existing or {},
    })

    # 署名検証なしでも中身を覗いてみる（破損・期限切れ確認用）
    import jwt as _jwt
    try:
        weak_decoded = _jwt.decode(token_existing, options={"verify_signature": False})
    except Exception as e:
        weak_decoded = {"error": str(e)}

    st.caption("🔧 署名検証なしのJWTペイロード（参考）")
    st.json(weak_decoded)


#####################




#####################

# ===== サインインUI =====
# 「別のユーザーでサインイン」表示制御
if "show_login_form" not in st.session_state:
    st.session_state["show_login_form"] = not bool(st.session_state.get("current_user"))

col_status, col_actions = st.columns([2, 1])

with col_status:
    if st.session_state.get("current_user"):
        st.success(f"✅ ログイン中: **{st.session_state['current_user']}**")
    else:
        st.info("未ログインです。サインインしてください。")

with col_actions:
    if st.session_state.get("current_user"):
        if st.button("別のユーザーでサインイン", key="btn_switch_user"):
            st.session_state["show_login_form"] = True
    else:
        # 未ログインなら確実にフォームを出す
        st.session_state["show_login_form"] = True

# --- サインインフォーム（必要に応じて表示） ---
if st.session_state["show_login_form"]:
    st.divider()
    st.subheader("🔑 サインイン（ログイン）")

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        username = st.text_input("ユーザー名", key="login_username")
    with col2:
        password = st.text_input("パスワード", type="password", key="login_password")
    with col3:
        st.markdown("&nbsp;")
        do_login = st.button("ログイン", use_container_width=True, key="btn_do_login")

    if do_login:
        users = load_users().get("users", {})
        rec = users.get((username or "").strip())
        if not rec or not check_password_hash(rec.get("pw", ""), password or ""):
            st.error("ユーザー名またはパスワードが違います。")
        else:
            apps = rec.get("apps", [])
            token, exp = issue_jwt(username, apps if isinstance(apps, list) else [])
            # cm.set(COOKIE_NAME, token, expires_at=dt.datetime.fromtimestamp(exp))
            cm.set(
                COOKIE_NAME,
                token,
                expires_at=dt.datetime.fromtimestamp(exp),
                path="/",   # ← これが超重要：ドメイン配下すべてで送信される
)

            st.session_state["current_user"] = username
            st.session_state["show_login_form"] = False  # サインイン完了で畳む
            append_login_log({
                "ts": dt.datetime.now().isoformat(timespec="seconds"),
                "user": username, "event": "login", "next": next_url, "exp": exp
            })
            st.success("✅ ログインしました")

# --- ログアウト / 切替 ---
st.divider()
st.subheader("ログアウト / アカウント切替")
cols = st.columns(3)
with cols[0]:
    if st.button("ログアウト", key="btn_logout"):
        cm.delete(COOKIE_NAME)
        st.session_state.pop("current_user", None)
        st.success("ログアウトしました。")
with cols[1]:
    if st.button("Cookieだけ削除（強制再サインイン用）", key="btn_clear_cookie"):
        cm.delete(COOKIE_NAME)
        st.session_state["show_login_form"] = True
        st.info("Cookieを削除しました。サインインフォームを開きます。")
with cols[2]:
    if st.button("サインインフォームを開く", key="btn_open_form"):
        st.session_state["show_login_form"] = True

# ===== ランチャー =====
# 公開アプリ
st.divider()
st.subheader("🌐 ログイン不要アプリ")
if PUBLIC_APPS:
    cols_pub = st.columns(len(PUBLIC_APPS))
    for i, (label, path) in enumerate(PUBLIC_APPS.items()):
        if cols_pub[i].button(label, use_container_width=True, key=f"pub_{i}"):
            if st.session_state.get("current_user"):
                path = path.rstrip("/") + f"/?user={st.session_state['current_user']}"
            else:
                path = path.rstrip("/") + "/"
            st.markdown(f'<meta http-equiv="refresh" content="0; url={path}"/>', unsafe_allow_html=True)
else:
    st.caption("（公開アプリはありません）")

# 保護アプリ
st.divider()
st.subheader("🔐 ログインが必要なアプリ")
if not st.session_state.get("current_user"):
    st.warning("ログインしてください。")
else:
    users_db = load_users().get("users", {})
    user_rec = users_db.get(st.session_state["current_user"], {})
    allowed_apps = set(user_rec.get("apps", [])) if isinstance(user_rec.get("apps", []), list) else set()

    show: Dict[str, str] = {}
    for label, path in PROTECTED_APPS.items():
        name = path.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
        if name in allowed_apps:
            show[label] = path

    if not show:
        st.info("このユーザーに許可されたアプリはありません。")
    else:
        cols_prot = st.columns(len(show))
        for i, (label, path) in enumerate(show.items()):
            if cols_prot[i].button(label, use_container_width=True, key=f"prot_{i}"):
                user = st.session_state["current_user"]
                next_jump = path.rstrip("/") + f"/?user={user}"
                st.markdown(f'<meta http-equiv="refresh" content="0; url={next_jump}"/>', unsafe_allow_html=True)

# ===== サインアップ（任意）=====
with st.expander("🆕 サインアップ（新規登録・任意）", expanded=False):
    st.caption("運用で不要ならこのブロックを削除してください。")
    n1, n2, n3 = st.columns([1,1,1])
    with n1:
        new_user = st.text_input("新しいユーザー名", key="signup_user")
    with n2:
        new_pw = st.text_input("パスワード（8文字以上推奨）", type="password", key="signup_pw1")
    with n3:
        new_pw2 = st.text_input("パスワード再入力", type="password", key="signup_pw2")
    apps_default = ["minutes", "image_maker", "login_test"]
    new_apps = st.multiselect("初期アクセス許可（apps）", options=apps_default, default=["minutes"], key="signup_apps")
    if st.button("登録する", key="btn_signup"):
        if not new_user or not new_pw or new_pw != new_pw2:
            st.error("入力を確認してください。")
        else:
            db = load_users()
            users = db.get("users", {})
            if new_user in users:
                st.error("そのユーザー名は既に存在します。")
            else:
                users[new_user] = {"pw": generate_password_hash(new_pw), "apps": list(new_apps)}
                db["users"] = users
                atomic_write_json(USERS_FILE, db)
                st.success("登録しました。ログインしてください。")


# =========================================
# 🧪 JWT / Cookie 診断（app.py 直埋め込み）
# =========================================
import hashlib, time, datetime as _dt
import jwt as _jwt

EXPECTED_ISS = JWT_ISS         # "prec-auth"
EXPECTED_AUD = JWT_AUD         # "prec-internal"
secret = JWT_SECRET
secret_fp = hashlib.sha256(secret.encode()).hexdigest()[:16]

def _human(epoch):
    if not epoch: return "-"
    try: return _dt.datetime.fromtimestamp(int(epoch)).isoformat(sep=" ", timespec="seconds")
    except Exception: return str(epoch)

def _decode_no_verify(tok: str | None):
    if not tok: return {}, None
    try:
        d = _jwt.decode(tok, options={"verify_signature": False, "verify_exp": False})
        return (d if isinstance(d, dict) else {}), None
    except Exception as e:
        return {}, f"{type(e).__name__}: {e}"

# ---- 署名検証（厳格）
strict_payload, strict_ok, strict_err = {}, False, None
if token_existing:
    try:
        strict_payload = _jwt.decode(
            token_existing,
            secret,
            algorithms=[JWT_ALGO],
            issuer=EXPECTED_ISS,
            audience=EXPECTED_AUD,
            options={"require": ["exp","sub"]},
        )
        strict_ok = True
    except Exception as e:
        strict_err = f"{type(e).__name__}: {e}"

# ---- 署名検証（緩和：iss/aud 検証なし）
relaxed_payload, relaxed_ok, relaxed_err = {}, False, None
if token_existing:
    try:
        relaxed_payload = _jwt.decode(
            token_existing,
            secret,
            algorithms=[JWT_ALGO],
            options={"require": ["exp","sub"], "verify_aud": False, "verify_iss": False},
        )
        relaxed_ok = True
    except Exception as e:
        relaxed_err = f"{type(e).__name__}: {e}"

# ---- 未検証（中身だけ）
raw_payload, raw_err = _decode_no_verify(token_existing)
exp = (raw_payload or {}).get("exp")
now = int(time.time())

with st.expander("🧪 JWT / Cookie 診断", expanded=False):
    # 概要カード
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Cookie present", "Yes" if token_existing else "No")
    with c2: st.metric("JWT valid (strict)", "True" if strict_ok else "False")
    with c3: st.metric("JWT valid (relaxed)", "True" if relaxed_ok else "False")
    with c4: st.metric("Secret FP", secret_fp)

    st.caption("※ Secret は表示しません。指紋(FP)が各アプリで一致していれば同じ鍵を読んでいます。")

    # 厳格
    with st.expander("🧾 厳格モードの結果（issuer/audience 検証あり）", expanded=not strict_ok):
        st.write({"ok": strict_ok, "error": strict_err})
        if strict_ok: st.json(strict_payload)

    # 緩和
    with st.expander("🧾 緩和モードの結果（issuer/audience 検証なし）", expanded=False):
        st.write({"ok": relaxed_ok, "error": relaxed_err})
        if relaxed_ok: st.json(relaxed_payload)

    # 未検証
    with st.expander("🧾 署名未検証デコード（参考：中身だけ）", expanded=False):
        st.write({"error": raw_err})
        st.json(raw_payload or {})
        st.write({
            "exp_human": _human(exp), "now_human": _human(now),
            "seconds_until_expire": (exp - now) if isinstance(exp, int) else None
        })

    # 一致チェック
    if raw_payload:
        m1, m2 = st.columns(2)
        with m1:
            st.write({"token.iss": raw_payload.get("iss"),
                      "equals_iss": raw_payload.get("iss") == EXPECTED_ISS})
        with m2:
            st.write({"token.aud": raw_payload.get("aud"),
                      "equals_aud": raw_payload.get("aud") == EXPECTED_AUD})

    # 操作ボタン
    st.divider()
    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("🔐 ポータルを開き直す", key="diag_portal"):
            # 自分自身を next にして開き直し（必要なら書き換え）
            st.markdown(
                f'<meta http-equiv="refresh" content="0; url={"/auth_portal"}?next={st.request.base_url if hasattr(st,"request") else "/"}"/>',
                unsafe_allow_html=True,
            )
    with b2:
        if st.button("🗑 Cookieだけ削除（prec_sso, path=/）", key="diag_delcookie"):
            cm.delete(COOKIE_NAME, path="/")
            st.success("Cookie を削除しました。ページを再読み込みしてください。")
    with b3:
        if st.button("🔁 再読込み", key="diag_rerun"):
            st.rerun()

