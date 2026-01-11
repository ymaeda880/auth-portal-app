# pages/51_ログイン_最小.py
"""
🔐 最小ログイン/ログアウトページ（app.py から抽出）

概要
----
- users.json に保存されているパスワードハッシュを照合し、OK なら JWT を発行。
- JWT は Cookie に保存（全パス `/`）し、即時 UI 切替のため session_state にも反映。
- ログアウトは Cookie の無効化（複数パス/属性に対して念のため）と session_state の削除のみ。

セキュリティ/実装メモ
-------------------
- 本ページは **最小構成**です（CSRF・レート制限・ロックアウト等は未実装）。
- Cookie の `secure` は開発時 HTTP を考慮して `None`（＝ブラウザ任せ）。本番 HTTPS では `True` 推奨。
- JWT の妥当性確認はページ表示ごとに行い、**失効/改ざん検出時は Cookie を掃除**します。
- 成功/失敗に関わらず、UI の即時反映が必要な箇所は `st.rerun()` を使います。
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys
from typing import Optional

import streamlit as st
import extra_streamlit_components as stx
from werkzeug.security import check_password_hash

# ========= プロジェクト共通ライブラリへのパス設定 =========
#   - このファイルは `pages/` 配下想定。共通ライブラリはプロジェクト直下にあるため
#     2 つ上のディレクトリを sys.path へ追加して import を通す。
PROJECTS_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

# ========= 共有ユーティリティ =========
from common_lib.auth.config import COOKIE_NAME
from common_lib.auth.jwt_utils import issue_jwt, verify_jwt   # JWT の発行/検証（失効時は None を返す想定）
from lib.users import load_users  # users.json を読む小さなヘルパ


# =============================================================================
# ページ初期化
# =============================================================================
st.set_page_config(page_title="ログイン（最小）", page_icon="🔐", layout="centered")
st.title("🔐 ログイン（最小）")

# Cookie の読み書き用（extra_streamlit_components）
# - key を固定して CookieManager インスタンスを保持
cm = stx.CookieManager(key="cm_login_min")


def _clear_cookie_everywhere(name: str) -> None:
    """
    Cookie を可能な限り無効化/削除する小さなヘルパ。

    ブラウザの仕様により、`path` や `domain` が一致していないと
    消し切れない場合があるため、以下の二段構えを採用:
      1) `path="/"` を明示して過去時刻で上書き
      2) 現在パスでも上書き
      3) CookieManager.delete() での削除トライ

    Parameters
    ----------
    name : str
        クッキー名（例: COOKIE_NAME）
    """
    epoch = dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)
    # 1) ルートパスで潰す
    cm.set(name, "", expires_at=epoch, path="/")
    # 2) カレントパスで潰す（path を省略）
    cm.set(name, "", expires_at=epoch)
    # 3) delete が実装されていれば実削除
    cm.delete(name)


def _set_auth_cookie(name: str, token: str, exp_ts: int) -> None:
    """
    認証用 Cookie を設定する。

    Parameters
    ----------
    name : str
        Cookie 名（例: COOKIE_NAME）
    token : str
        発行済みの JWT（文字列）
    exp_ts : int
        有効期限の UNIX タイムスタンプ（秒）

    Notes
    -----
    - `path="/"` を指定してアプリ全体で送信されるようにする。
    - `same_site="Lax"` は通常のフォーム/リンク遷移には送信されるが、
      クロスサイトのサブリクエスト等では送られない。CSRF 低減目的。
    - `secure` はデフォルト None（開発時の HTTP を許容）。
      **本番の HTTPS 配下では True を設定することを強く推奨。**
    """
    cm.set(
        name,
        token,
        expires_at=dt.datetime.fromtimestamp(exp_ts),
        path="/",
        same_site="Lax",
        secure=None,  # ← 本番 HTTPS では True を推奨
    )


# =============================================================================
# 起動時：Cookie → JWT 検証し、必要なら session_state を補完 / 失効時は掃除
# =============================================================================
token: Optional[str] = cm.get(COOKIE_NAME)
payload = verify_jwt(token) if token else None

if payload:
    # Cookie が有効で session_state にまだユーザーがいなければ補完する
    if "current_user" not in st.session_state:
        st.session_state["current_user"] = payload.get("sub")
else:
    # 失効（期限切れ）や改ざんで verify 失敗した場合、古い Cookie を掃除して状態不整合を避ける
    if token:
        _clear_cookie_everywhere(COOKIE_NAME)

# 以降の表示/分岐で使う現在ユーザー
user: Optional[str] = st.session_state.get("current_user")

# =============================================================================
# ログイン状態の表示
# =============================================================================
if user:
    st.success(f"✅ ログイン中: **{user}**")
else:
    st.info("未ログインです。ユーザー名とパスワードでサインインしてください。")

st.divider()

# =============================================================================
# 未ログイン：ログインフォーム
# =============================================================================
if not user:
    c1, c2, c3 = st.columns([1, 1, 1])

    with c1:
        # key を固定するとブラウザのオートフィルが効きやすい
        u = st.text_input("ユーザー名", key="login_username_min")

    with c2:
        p = st.text_input("パスワード", type="password", key="login_password_min")

    with c3:
        # ログインボタンの余白を詰める軽い CSS
        st.markdown(
            """
            <style>
            div[data-testid="stButton"] button {
                margin-top: 0.8em;  /* ボタン位置の微調整 */
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        if st.button("ログイン", use_container_width=True, key="btn_login_min"):
            # 入力の前後空白は除去（ユーザー名の意図しない空白混入対策）
            username = (u or "").strip()
            password = p or ""

            # users.json の読み込み＆対象ユーザー行を取得
            rec = load_users().get("users", {}).get(username)

            # ユーザーが存在し、ハッシュ照合が OK かを確認
            if not rec or not check_password_hash(rec.get("pw", ""), password):
                st.error("ユーザー名またはパスワードが違います。")
            else:
                # apps クレーム（権限など）を付けた JWT を発行
                apps = rec.get("apps", []) if isinstance(rec.get("apps", []), list) else []
                token, exp = issue_jwt(username, apps)

                # 1) Cookie に JWT を保存（全パス、SameSite=Lax）
                _set_auth_cookie(COOKIE_NAME, token, exp)

                # 2) 直ちに UI を切り替えるため session_state も更新
                st.session_state["current_user"] = username

                # 3) ユーザーへの通知（rerun で消えるので情報系は軽めに）
                st.success("✅ ログインしました。")

                # 4) rerun で「未ログインフォーム」を消し、ログイン状態表示へ切り替え
                st.rerun()

# =============================================================================
# ログイン中：ログアウトボタン
# =============================================================================
else:
    lcol, _ = st.columns([1, 2])
    with lcol:
        if st.button("ログアウト", use_container_width=True, key="btn_logout_min"):
            # クッキー無効化（できるだけ広く/確実に）
            _clear_cookie_everywhere(COOKIE_NAME)

            # session_state 側もクリア
            st.session_state.pop("current_user", None)

            # 通知ののち即 rerun（ログイン中ビュー→未ログインビューへ）
            st.success("ログアウトしました。")
            st.rerun()

st.divider()
st.caption(
    f"Cookie 名: `{COOKIE_NAME}` / このページはログインとログアウトのみの最小構成です。"
    " 本番運用では CSRF 対策・多要素認証・レート制限・監査ログ等の実装をご検討ください。"
)
