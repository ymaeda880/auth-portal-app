# pages/50_シンプルログイン.py
"""
🔐 Auth Portal (Simple) — Streamlit minimal login page
======================================================

本モジュールは、Cookie（JSON Web Token; JWT）ベースの最小ログイン UI を提供する
Streamlit ページである。ユーザー名とパスワード（ハッシュ照合）で認証し、
成功時に JWT を発行して Cookie に保存する。ログアウト時は Cookie を削除する。

主な機能（features）:
- CookieManager（extra_streamlit_components）を用いた Cookie の取得/設定/削除
- JWT（json web token）発行・検証（issue_jwt / verify_jwt）
- users.json（load_users）に保存されたユーザー情報の参照とパスワード照合
- ログイン状態（current_user）の判定と UI 出し分け
- デバッグ用途の Cookie 全体ダンプ表示

設計方針（design policy）:
- 本ページは **認証の最小実装** に徹する（リダイレクトや ACL は未実装）
- 可読性と保守性向上のため、画面ロジックを小さな関数へ分割
- 例外処理は簡潔にし、UI 側でユーザーに分かりやすく通知

依存モジュール（dependencies）:
- streamlit, extra_streamlit_components (CookieManager)
- werkzeug.security.check_password_hash
- common_lib.auth.jwt_utils: issue_jwt, verify_jwt
- common_lib.auth.config: COOKIE_NAME
- lib.users: load_users

注意点（notes）:
- Cookie の path/domain/secure 等の詳細制御は CookieManager 実装依存
- 本ページは **単純な学習/社内利用** を想定。運用では HTTPS・Cookie 属性・CSRF・
  エラーログなどの強化が必要

"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys
from typing import Any, Dict, Optional, Tuple
import time

import streamlit as st
import extra_streamlit_components as stx
from werkzeug.security import check_password_hash

# ===== 共有ライブラリへのパス追加（projects ルートまで遡る想定） =====
PROJECTS_ROOT = Path(__file__).resolve().parents[2]  # .../auth_portal_project
if str(PROJECTS_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECTS_ROOT))

# ===== 自作共通ライブラリ =====
from common_lib.auth.config import COOKIE_NAME
from common_lib.auth.jwt_utils import issue_jwt, verify_jwt
from lib.users import load_users






# ---------------------------------------------------------------------
# ユーティリティ関数群（UI/状態判定/処理）
# ---------------------------------------------------------------------
def get_current_user_from_cookie(cm: stx.CookieManager) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str]]:
    """
    Cookie から JWT を取得・検証し、現在のユーザー（current_user）を返す。

    Parameters
    ----------
    cm : stx.CookieManager
        Cookie の取得に使用する CookieManager インスタンス。

    Returns
    -------
    (current_user, payload, token) : Tuple[Optional[str], Optional[dict], Optional[str]]
        - current_user: `sub` クレームを文字列で返す。無効/未ログインなら None。
        - payload: JWT のペイロード辞書。検証不可なら None。
        - token: Cookie に保存されていたトークンそのもの。存在しなければ None。

    Notes
    -----
    - JWT は verify_jwt(...) で署名・期限を検証する（common_lib.auth.jwt_utils）。
    - Cookie 名は common_lib.auth.config.COOKIE_NAME によって管理する。
    """
    token = cm.get(COOKIE_NAME)
    payload = verify_jwt(token) if token else None
    current_user = payload.get("sub") if payload else None
    return current_user, payload, token


def render_cookie_dump(cm: stx.CookieManager) -> None:
    """
    デバッグ用に、取得できる全 Cookie を JSON 表示する。

    Parameters
    ----------
    cm : stx.CookieManager
        Cookie の取得に使用する CookieManager インスタンス。

    Side Effects
    ------------
    - Streamlit の UI に JSON（Cookie 一覧）を表示する。
    """
    st.subheader("🍪 現在の Cookie")
    # Cookie は環境やブラウザの仕様により取得できない場合もあるため空 dict を既定
    cookies = cm.get_all() or {}
    st.json(cookies)


def render_login_status(current_user: Optional[str]) -> None:
    """
    現在のログイン状態を UI に表示する。

    Parameters
    ----------
    current_user : Optional[str]
        ログイン済みであればユーザー名、未ログインなら None。
    """
    if current_user:
        st.success(f"✅ ログイン中: **{current_user}**")
    else:
        st.info("未ログインです。ユーザー名とパスワードでサインインしてください。")


def try_login_and_set_cookie(cm: stx.CookieManager, username: str, password: str) -> bool:
    """
    users.json のユーザー情報を用いてパスワード照合し、成功したら JWT を発行して Cookie を設定する。

    Parameters
    ----------
    cm : stx.CookieManager
        Cookie の設定に使用する CookieManager。
    username : str
        入力されたユーザー名（前後空白は呼び出し元で strip を推奨）。
    password : str
        入力されたパスワード（平文）。

    Returns
    -------
    bool
        True: ログイン成功（Cookie 設定済み）
        False: ログイン失敗

    Notes
    -----
    - パスワード照合は werkzeug.security.check_password_hash を使用。
    - JWT の `payload["apps"]` は将来の権限制御拡張に備えて保存するが、本ページでは未使用。
    - Cookie の expires_at は JWT の exp と同じ epoch に揃える。
    """
    # users.json から該当ユーザー情報を取得
    users_root = load_users()  # 期待: {"users": {"alice": {"pw": "<hash>", "apps": [...]}, ...}}
    rec = users_root.get("users", {}).get((username or "").strip())

    # ユーザー不存在 or ハッシュ照合失敗なら認証失敗
    if not rec or not check_password_hash(rec.get("pw", ""), password or ""):
        return False

    # apps は JWT ペイロードへ保存（未使用だが将来の拡張に備える）
    apps = rec.get("apps", []) if isinstance(rec.get("apps", []), list) else []
    token, exp = issue_jwt(username, apps)

    # ✅ Cookie 設定（CookieManager 実装によっては path 等を受け取らないため expires のみ）
    cm.set(COOKIE_NAME, token, expires_at=dt.datetime.fromtimestamp(exp),path="/" )
    return True


def render_login_form_and_handle(cm: stx.CookieManager) -> None:
    """
    未ログイン時にログインフォームを表示し、ログインボタン押下で認証→Cookie 設定→rerun を行う。

    Parameters
    ----------
    cm : stx.CookieManager
        Cookie 設定に使用する CookieManager。

    Side Effects
    ------------
    - Streamlit UI にフォームを描画。
    - 認証成功時は Cookie 設定後に st.rerun() を呼び出す。
    - 認証失敗時は st.error(...) を表示。
    """
    st.markdown("### 🔐 ログイン")

    # 3 カラムで入力欄＋ボタンを横並びにする（見栄え目的）
    c1, c2, c3 = st.columns([1, 1, 1])

    # --- 入力欄（ユーザー名 / パスワード）
    with c1:
        username = st.text_input("ユーザー名", key="login_username_simple")
    with c2:
        password = st.text_input("パスワード", type="password", key="login_password_simple")

    # --- 送信ボタン（右カラム）
    with c3:
        st.markdown("&nbsp;")  # ボタンの垂直位置を調整（1行分の空白）
        if st.button("ログイン", use_container_width=True, key="btn_login_simple"):
            ok = try_login_and_set_cookie(cm, username=username, password=password)
            if not ok:
                # 認証失敗：ユーザーまたはパスワードの不一致
                st.error("ユーザー名またはパスワードが違います。")
            else:
                # 認証成功：Cookie 設定済み → 画面更新して状態反映
                st.success("✅ ログインしました。")
                ###
                ## DEBUG ##
                ###
                #st.session_state["current_user"] = (username or "").strip()   # ← 追加
                print(f"✅ login success: {username}")
                #time.sleep(0.5)
                ###
                #st.rerun()
                st.rerun()


def render_logout_and_handle(cm: stx.CookieManager) -> None:
    """
    ログイン中のみ表示するログアウト UI を描画し、ボタン押下で Cookie を削除して rerun する。

    Parameters
    ----------
    cm : stx.CookieManager
        Cookie 削除に使用する CookieManager。

    Side Effects
    ------------
    - Cookie を削除（cm.delete(COOKIE_NAME)）
    - st.rerun() により画面を更新
    """
    st.markdown("### 🚪 ログアウト")
    lcol, _ = st.columns([1, 2])
    with lcol:
        # if st.button("ログアウト", key="btn_logout_simple", use_container_width=True):
        #     # Cookie 名は COOKIE_NAME に統一管理（path は実装依存のため渡さない）
        #     cm.delete(COOKIE_NAME, path="/")
        #     st.success("ログアウトしました。")
        #     st.rerun()

        if st.button("ログアウト", key="btn_logout_simple", use_container_width=True):
            # ==============================
            # Cookie 削除（path 非対応の実装向け）
            # ==============================

            # 1. ルートスコープ("/") にある Cookie を期限切れで上書き（Max-Age=0 相当）
            # epoch = dt.datetime.utcfromtimestamp(0)
            # cm.set(COOKIE_NAME, "", expires_at=epoch, path="/")

            # 1. ルートスコープ("/") にある Cookie を期限切れで上書き（Max-Age=0 相当）
            epoch = dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)
            cm.set(COOKIE_NAME, "", expires_at=epoch, path="/")

            # 2. カレントパスに残っている Cookie も同様に上書き削除
            cm.set(COOKIE_NAME, "", expires_at=epoch)

            # 3. 最後に delete() 呼び出し（実装が対応していれば補完的に効く）
            cm.delete(COOKIE_NAME)

            # セッション情報をリセット
            st.session_state.pop("current_user", None)

            # メッセージ表示 → rerun
            st.success("ログアウトしました。")
            st.rerun()


def setup_page() -> stx.CookieManager:
    """
    ページ初期化（set_page_config, タイトル, CookieManager 生成）を行い、CookieManager を返す。

    Returns
    -------
    stx.CookieManager
        本ページで使用する CookieManager インスタンス。

    Notes
    -----
    - layout="centered" はフォームを中央寄せ表示。
    - CookieManager の key はページ内で一意にする。
    """
    st.set_page_config(page_title="Auth Portal (Simple)", page_icon="🔐", layout="centered")
    st.title("🔐 シンプル・ログイン")
    cm = stx.CookieManager(key="cm_portal_simple")
    return cm


def main() -> None:
    """
    本ページのメイン制御。

    フロー概要:
    1) ページ初期化と CookieManager 準備
    2) Cookie → JWT 検証で current_user 判定
    3) Cookie ダンプ表示（デバッグ用）
    4) ログイン状態に応じた UI 出し分け（未ログイン: ログインフォーム、ログイン中: ログアウトUI）
    5) フッター（補足情報）表示
    """
    # 1) 初期化
    cm = setup_page()

    # 2) Cookie → JWT 検証（current_user, payload, token を取得）
    current_user, payload, token = get_current_user_from_cookie(cm)

    # 3) Cookie ダンプ表示（トラブルシューティングに有用）
    render_cookie_dump(cm)

    # 4) ログイン状態の表示
    render_login_status(current_user)

    st.divider()

    # 5) 出し分け：未ログイン → フォーム表示、ログイン中 → ログアウト表示
    if not current_user:
        render_login_form_and_handle(cm)
    else:
        render_logout_and_handle(cm)

    st.divider()
    st.caption(
        f"Cookie 名: `{COOKIE_NAME}` / "
        "このページはログイン・ログアウト・Cookie表示のみの最小構成です。"
    )


# エントリポイント（Streamlit 実行時）
if __name__ == "__main__":
    # Streamlit は通常 `streamlit run` で実行されるため、ここは直接実行時の保険。
    main()
else:
    # Streamlit がインポート時にモジュールレベルを評価するため、常時 main() を呼ぶ
    # （import 時に描画したい場合は以下を使用）
    main()
