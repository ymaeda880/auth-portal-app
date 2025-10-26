# login_test_app/lib/sso.py
from __future__ import annotations
from typing import Optional, Dict, Any

import jwt
import streamlit as st

# 🔐 ポータル側と必ず一致させること
AUTH_SECRET = st.secrets.get("AUTH_SECRET", "CHANGE_ME")
AUTH_ALGO   = "HS256"
AUTH_ISS    = "prec-auth"       # ポータルの発行者(iss)
AUTH_AUD    = "prec-internal"   # 受信者(aud)

def verify_token(
    token: Optional[str],
    *,
    check_iss: bool = True,
    check_aud: bool = True,
    leeway_seconds: int = 30,  # 時計ズレ許容
) -> Optional[Dict[str, Any]]:
    """
    JWT を検証し、有効なら payload(dict) を返す。無効・期限切れは None。
    - 必須: exp, sub
    - 既定で iss/aud も照合（ポータルと値を合わせる）
    """
    if not token:
        return None

    try:
        options = {"require": ["exp", "sub"]}
        kwargs: Dict[str, Any] = {"algorithms": [AUTH_ALGO], "options": options, "leeway": leeway_seconds}
        if check_iss:
            kwargs["issuer"] = AUTH_ISS
        if check_aud:
            kwargs["audience"] = AUTH_AUD

        payload = jwt.decode(token, AUTH_SECRET, **kwargs)
        # ここで必要なら追加チェック（例: apps が list か）
        apps = payload.get("apps", [])
        if apps is not None and not isinstance(apps, list):
            payload["apps"] = []
        return payload

    except jwt.ExpiredSignatureError:
        # 期限切れ
        return None
    except jwt.InvalidTokenError:
        # 署名不一致/クレーム不正 等
        return None
