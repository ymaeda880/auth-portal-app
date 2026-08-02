# -*- coding: utf-8 -*-
# auth_portal_app/lib/login_component/browser_login.py
# ============================================================
# ブラウザー自動入力対応ログインコンポーネント
#
# 機能：
# - Streamlit Components v2で通常のHTML formを描画する
# - ブラウザーのユーザー名・パスワード自動入力に対応する
# - ログイン送信時にユーザー名とパスワードをPythonへ返す
#
# 方針：
# - iframeを使用しない
# - 通常のPOST送信は行わない
# - パスワードはstateとして保持せず，submit triggerだけで返す
# ============================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import streamlit as st


# ============================================================
# 戻り値
# ============================================================
@dataclass(frozen=True)
class BrowserLoginSubmission:
    username: str
    password: str


# ============================================================
# HTML
# ============================================================
_LOGIN_HTML = """
<form id="pais-login-form" autocomplete="on">
    <div class="pais-login-field">
        <label for="pais-login-username">ユーザー名</label>
        <input
            id="pais-login-username"
            name="username"
            type="text"
            autocomplete="username"
            autocapitalize="none"
            spellcheck="false"
            placeholder="ユーザー名"
        />
    </div>

    <div class="pais-login-field">
        <label for="pais-login-password">パスワード</label>
        <input
            id="pais-login-password"
            name="password"
            type="password"
            autocomplete="current-password"
            placeholder="パスワード"
        />
    </div>

    <button id="pais-login-submit" type="submit">
        ログイン
    </button>
</form>
"""


# ============================================================
# CSS
# ============================================================
_LOGIN_CSS = """
#pais-login-form {
    display: grid;
    grid-template-columns:
        minmax(220px, 1fr)
        minmax(220px, 1fr)
        minmax(150px, 0.65fr);
    gap: 16px;
    align-items: end;
    width: 100%;
    margin: 0;
    padding: 0;
    font-family: var(--st-font);
    color: var(--st-text-color);
}

.pais-login-field {
    min-width: 0;
}

.pais-login-field label {
    display: block;
    margin: 0 0 8px 0;
    font-size: 0.95rem;
    line-height: 1.25;
}

.pais-login-field input {
    width: 100%;
    height: 2.5rem;
    box-sizing: border-box;
    padding: 0 0.75rem;
    border: 1px solid rgba(49, 51, 63, 0.22);
    border-radius: 0.5rem;
    outline: none;
    background: var(--st-secondary-background-color);
    color: var(--st-text-color);
    font: inherit;
}

.pais-login-field input:focus {
    border-color: var(--st-primary-color);
    box-shadow: 0 0 0 1px var(--st-primary-color);
}

#pais-login-submit {
    width: 100%;
    height: 2.5rem;
    box-sizing: border-box;
    border: 1px solid var(--st-primary-color);
    border-radius: 0.5rem;
    background: var(--st-primary-color);
    color: white;
    font: inherit;
    font-weight: 600;
    cursor: pointer;
}

#pais-login-submit:hover {
    filter: brightness(0.96);
}

#pais-login-submit:disabled {
    cursor: not-allowed;
    opacity: 0.65;
}

@media (max-width: 760px) {
    #pais-login-form {
        grid-template-columns: 1fr;
    }
}
"""


# ============================================================
# JavaScript
# ============================================================
_LOGIN_JS = r"""
export default function({
    parentElement,
    data,
    setTriggerValue
}) {
    const form = parentElement.querySelector("#pais-login-form");
    const username = parentElement.querySelector("#pais-login-username");
    const password = parentElement.querySelector("#pais-login-password");
    const submitButton = parentElement.querySelector("#pais-login-submit");

    if (!form || !username || !password || !submitButton) {
        return;
    }

    if (document.activeElement !== username) {
        const nextUsername = data?.username ?? "";

        if (username.value !== nextUsername) {
            username.value = nextUsername;
        }
    }

    submitButton.disabled = Boolean(data?.disabled);

    form.onsubmit = (event) => {
        event.preventDefault();

        setTriggerValue("submit", {
            username: username.value ?? "",
            password: password.value ?? "",
        });
    };

    password.onkeydown = (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            form.requestSubmit();
        }
    };
}
"""


# ============================================================
# component登録
# ============================================================
_BROWSER_LOGIN_COMPONENT = st.components.v2.component(
    name="pais_browser_login",
    html=_LOGIN_HTML,
    css=_LOGIN_CSS,
    js=_LOGIN_JS,
    isolate_styles=False,
)


# ============================================================
# public API
# ============================================================
def render_browser_login(
    *,
    key: str,
    default_username: str = "",
    disabled: bool = False,
) -> BrowserLoginSubmission | None:
    # ------------------------------------------------------------
    # submit triggerは一回限りの値として受け取る
    #
    # パスワードはdefault/stateに保存せず，
    # 送信された瞬間だけPythonへ渡す．
    # ------------------------------------------------------------
    result = _BROWSER_LOGIN_COMPONENT(
        key=key,
        data={
            "username": default_username,
            "disabled": disabled,
        },
        on_submit_change=lambda: None,
        width="stretch",
        height="content",
    )

    submit_value: Any = getattr(result, "submit", None)

    if not isinstance(submit_value, dict):
        return None

    return BrowserLoginSubmission(
        username=str(submit_value.get("username") or ""),
        password=str(submit_value.get("password") or ""),
    )
