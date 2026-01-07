# pages/41_告知管理.py
# ============================================================
# 📣 Notice Admin（管理者専用：メンテ/アップデート告知の作成・管理）
# - 認証：common_lib の require_admin_user(st) に一本化
# - DB: data/notices/notices.db
# - UI:
#   (1) 新規告知の作成
#   (2) DB操作パネル（一覧→1件選択→状態変更/削除/コピー/編集）
#   (3) notices.csv ダウンロード
# ============================================================
from __future__ import annotations

import datetime as dt
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
from typing import Any, Dict, Optional, List

import pandas as pd
import streamlit as st

# ---------- 物理パス解決（既存思想を維持） ----------
_THIS = Path(__file__).resolve()
APP_ROOT = _THIS.parents[1]   # .../auth_portal_app
PROJ_ROOT = _THIS.parents[2]  # .../auth_portal_project
MONO_ROOT = _THIS.parents[3]  # .../projects ← common_lib がここ直下にある想定

for p in (APP_ROOT, PROJ_ROOT, MONO_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# ---------- 認証（common_lib） ----------
from common_lib.auth.auth_helpers import require_admin_user

# ---------- notices（lib/notices） ----------
from lib.notices.db import (
    notice_db_path,
    init_db,
    insert_notice,
    set_notice_status,
    delete_notice,
    get_notice,
    update_notice,
    copy_notice,
    fetch_all_notices,
)
from lib.notices.utils import (
    STATUS_LABEL,
    validate_iso8601,
    parse_iso_to_jst_date,
    notice_radio_label,
)

# ============================================================
# Paths / DB
# ============================================================
_DB_PATH = notice_db_path(APP_ROOT)

# ============================================================
# Page title
# ============================================================
PAGE_TITLE = "📣 告知管理（管理者専用）"


# ============================================================
# Main
# ============================================================
def main() -> None:
    # --------------------------------------------------------
    # Admin gate（common_lib方式）
    # --------------------------------------------------------
    st.set_page_config(page_title=PAGE_TITLE, page_icon="📣", layout="wide")

    sub = require_admin_user(st)
    if not sub:
        st.error("🚫 このページは管理者のみアクセスできます。")
        st.stop()

    left, right = st.columns([2, 1])
    with left:
        st.title(PAGE_TITLE)
    with right:
        st.success(f"✅ 管理者ログイン中: **{sub}**")
    st.caption("AIは使用していません")

    init_db(_DB_PATH)

    with st.sidebar:
        st.caption("DB")
        st.code(str(_DB_PATH))

    # --------------------------------------------------------
    # (1) 新規告知の作成
    # --------------------------------------------------------
    st.subheader("📝 新規告知の作成")

    kinds = {
        "maintenance": "🚧 メンテナンス",
        "update": "🆕 アップデート",
        "info": "ℹ️ お知らせ",
    }
    severities = {
        "normal": "通常",
        "important": "重要",
        "critical": "最重要",
    }
    statuses = {
        "draft": "下書き（非表示）",
        "published": "公開",
        "archived": "アーカイブ（非表示）",
    }

    JST = timezone(timedelta(hours=9))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kind = st.selectbox(
            "種類",
            options=list(kinds.keys()),
            format_func=lambda k: kinds[k],
            key="new_kind",
        )
    with c2:
        severity = st.selectbox(
            "重要度",
            options=list(severities.keys()),
            format_func=lambda k: severities[k],
            key="new_sev",
        )
    with c3:
        status = st.selectbox(
            "状態",
            options=list(statuses.keys()),
            format_func=lambda k: statuses[k],
            index=1,
            key="new_status",
        )
    with c4:
        pinned = st.checkbox("ピン留め（上固定）", value=False, key="new_pinned")

    title = st.text_input(
        "タイトル",
        placeholder="例：12/18 午前 メンテナンスのお知らせ",
        key="new_title",
    )
    body = st.text_area(
        "本文",
        height=180,
        placeholder="例：対象アプリ、影響範囲、開始/終了予定、連絡先などを簡潔に。",
        key="new_body",
    )

    c5, c6, c7 = st.columns(3)

    with c5:
        start_now = st.checkbox("今から表示", value=True, key="new_start_now")

        start_date = st.date_input(
            "表示開始（日付）",
            value=dt.datetime.now(JST).date(),
            disabled=start_now,
            key="new_start_date",
        )

        if start_now:
            start_at = dt.datetime.now(JST).isoformat(timespec="seconds")
        else:
            if start_date is None:
                start_at = ""
                st.warning("表示開始（日付）を選んでください（または「今から表示」をONにしてください）。")
            else:
                start_dt = dt.datetime.combine(
                    start_date,
                    dt.time(0, 0, 0, tzinfo=JST),
                )
                start_at = start_dt.isoformat(timespec="seconds")

    with c6:
        no_end = st.checkbox("終了なし（無期限）", value=True, key="new_no_end")

        end_date = st.date_input(
            "表示終了（日付）",
            value=dt.datetime.now(JST).date(),
            disabled=no_end,
            key="new_end_date",
        )

        if no_end:
            end_at = ""  # 無期限
        else:
            if end_date is None:
                end_at = ""
                st.warning("表示終了（日付）を選んでください（または「終了なし（無期限）」をONにしてください）。")
            else:
                end_dt = dt.datetime.combine(
                    end_date,
                    dt.time(23, 59, 59, tzinfo=JST),
                )
                end_at = end_dt.isoformat(timespec="seconds")

    with c7:
        target_apps = st.text_input(
            "対象アプリ（任意, CSV）",
            value="",
            help='例：bot,minutes,image_maker（空欄OK）',
            key="new_apps",
        )

    # 今回は all 固定（必要なら拡張）
    audience_type = "all"
    audience_key = None

    btn_row = st.columns([1, 2, 6])
    with btn_row[0]:
        do_create = st.button("✅ 登録", key="btn_create")
    with btn_row[1]:
        do_clear = st.button("🧹 クリア", key="btn_clear")

    if do_clear:
        st.rerun()

    if do_create:
        errs: list[str] = []
        if not (title or "").strip():
            errs.append("タイトルは必須です。")
        if not (body or "").strip():
            errs.append("本文は必須です。")
        if not (start_at or "").strip():
            errs.append("表示開始が未設定です（「今から表示」ON または 日付選択が必要）。")
        elif not validate_iso8601(start_at, allow_empty=False):
            errs.append("表示開始の形式が不正です（ISO8601）。")
        if (end_at or "").strip() and not validate_iso8601(end_at, allow_empty=True):
            errs.append("表示終了の形式が不正です（ISO8601）。")

        if errs:
            st.error("\n".join([f"- {e}" for e in errs]))
        else:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            row: Dict[str, Any] = {
                "kind": kind,
                "title": title.strip(),
                "body": body.strip(),
                "severity": severity,
                "status": status,
                "audience_type": audience_type,
                "audience_key": audience_key,
                "start_at": start_at.strip(),
                "end_at": end_at.strip() if end_at.strip() else None,
                "pinned": pinned,
                "created_by": sub,
                "created_at": now,
                "updated_at": now,
                "target_apps": target_apps.strip() if target_apps.strip() else None,
            }
            new_id = insert_notice(_DB_PATH, row)
            st.success(f"登録しました（id={new_id}）。")
            st.rerun()

    st.divider()

    # --------------------------------------------------------
    # (2) DB操作パネル（一覧→選択→操作）
    # --------------------------------------------------------
    st.subheader("🗄 DB 操作パネル（選択→削除/編集/状態変更/コピー）")

    data = fetch_all_notices(_DB_PATH)
    if not data:
        st.info("DBにデータがありません。")
        return

    # --- CSV出力（表示はしないが出力は残す） ---
    df_all = pd.DataFrame(data)
    csv_text = df_all.to_csv(index=False)
    csv_bytes = ("\ufeff" + csv_text).encode("utf-8")  # Excel配慮：UTF-8 BOM

    c_csv1, c_csv2 = st.columns([1, 6])
    with c_csv1:
        st.download_button(
            label="⬇️ notices.csv",
            data=csv_bytes,
            file_name="notices.csv",
            mime="text/csv",
            key="dl_notices_csv",
        )
    with c_csv2:
        st.caption(f"件数: {len(df_all)} / DB: {str(_DB_PATH)}")

    # --- 一覧テーブル（本文は出さない） ---
    show_cols = [
        "id", "kind", "severity", "status", "pinned",
        "title", "start_at", "end_at",
        "created_by", "created_at", "updated_at",
        "target_apps",
    ]
    cols = [c for c in show_cols if c in df_all.columns]
    st.dataframe(df_all[cols], hide_index=True)

    selected = st.radio(
        "操作対象（1件選択）",
        options=data,
        format_func=notice_radio_label,
        index=0,
        horizontal=False,
        key="notice_select_radio",
    )
    nid = int(selected["id"])

    # ▼ 状態表示（STATUS_LABELで統一）
    st.markdown("### 📌 選択中の告知の状態")

    raw_status = selected.get("status")
    pretty_status = STATUS_LABEL.get(raw_status, str(raw_status))

    if raw_status == "published":
        st.success(f"{pretty_status}：現在、ポータルに表示されています。")
    elif raw_status == "draft":
        st.warning(f"{pretty_status}：管理者のみが見え、ユーザーには表示されません。")
    elif raw_status == "archived":
        st.info(f"{pretty_status}：過去の告知として保管されています（非表示）。")
    else:
        st.write(f"状態: {pretty_status}")

    with st.expander("選択中のレコード（詳細）", expanded=False):
        st.json(selected)

    st.markdown("### クイック操作")

    a1, a2, a3, a4, sep, a5 = st.columns([1, 1, 1, 1, 0.05, 3])

    with a1:
        if st.button("公開", key=f"btn_pub_{nid}", disabled=(raw_status == "published")):
            set_notice_status(_DB_PATH, nid, "published")
            st.success("公開にしました。")
            st.rerun()

    with a2:
        if st.button("下書き", key=f"btn_draft_{nid}", disabled=(raw_status == "draft")):
            set_notice_status(_DB_PATH, nid, "draft")
            st.success("下書きにしました。")
            st.rerun()

    with a3:
        if st.button("アーカイブ", key=f"btn_arch_{nid}", disabled=(raw_status == "archived")):
            set_notice_status(_DB_PATH, nid, "archived")
            st.success("アーカイブにしました。")
            st.rerun()

    with a4:
        if st.button("コピー（下書き）", key=f"btn_copy_{nid}"):
            new_id = copy_notice(_DB_PATH, nid, created_by=sub, as_status="draft")
            st.success(f"コピーしました（新id={new_id} / 下書き）。")
            st.rerun()

    with sep:
        st.markdown(
            "<div style='border-left:4px solid #bbb; height:72px; margin:auto'></div>",
            unsafe_allow_html=True,
        )

    with a5:
        d1, d2 = st.columns([3, 1])
        with d1:
            confirm = st.text_input(
                f"削除確認：id={nid} を入力",
                value="",
                placeholder=str(nid),
                help="⚠️ 削除は取り消せません",
                key=f"del_confirm_{nid}",
            )
        with d2:
            if st.button("削除", key=f"btn_del_{nid}", type="secondary"):
                if confirm.strip() != str(nid):
                    st.error("確認IDが一致しません。")
                else:
                    delete_notice(_DB_PATH, nid)
                    st.success("削除しました。")
                    st.rerun()

    st.divider()

    # --------------------------------------------------------
    # 編集（選択中のレコードを更新）
    # --------------------------------------------------------
    st.subheader("✏️ 編集（選択中のレコードを更新）")

    cur = get_notice(_DB_PATH, nid)
    if not cur:
        st.error("レコードが見つかりません。")
        st.stop()

    # 既存値を date に落とす（落ちない場合は今日）
    cur_start_date = parse_iso_to_jst_date(cur.get("start_at") or "", JST) or dt.datetime.now(JST).date()
    cur_end_date = parse_iso_to_jst_date(cur.get("end_at") or "", JST) or dt.datetime.now(JST).date()

    e1, e2, e3, e4 = st.columns(4)
    with e1:
        e_kind = st.selectbox(
            "種類",
            options=list(kinds.keys()),
            index=list(kinds.keys()).index(cur["kind"]) if cur["kind"] in kinds else 0,
            format_func=lambda k: kinds.get(k, k),
            key=f"p_kind_{nid}",
        )
    with e2:
        e_sev = st.selectbox(
            "重要度",
            options=list(severities.keys()),
            index=list(severities.keys()).index(cur["severity"]) if cur["severity"] in severities else 0,
            format_func=lambda k: severities.get(k, k),
            key=f"p_sev_{nid}",
        )
    with e3:
        e_status = st.selectbox(
            "状態",
            options=list(statuses.keys()),
            index=list(statuses.keys()).index(cur["status"]) if cur["status"] in statuses else 1,
            format_func=lambda k: statuses.get(k, k),
            key=f"p_status_{nid}",
        )
    with e4:
        e_pinned = st.checkbox("ピン留め", value=bool(cur.get("pinned", 0)), key=f"p_pin_{nid}")

    e_title = st.text_input("タイトル", value=cur["title"], key=f"p_title_{nid}")
    e_body = st.text_area("本文", value=cur["body"], height=180, key=f"p_body_{nid}")

    e5, e6, e7 = st.columns(3)

    with e5:
        start_now_edit = st.checkbox("今から表示（編集）", value=False, key=f"p_start_now_{nid}")

        start_date_edit = st.date_input(
            "表示開始（日付・編集）",
            value=cur_start_date,
            disabled=start_now_edit,
            key=f"p_start_date_{nid}",
        )

        if start_now_edit:
            e_start = dt.datetime.now(JST).isoformat(timespec="seconds")
        else:
            if start_date_edit is None:
                e_start = ""
                st.warning("表示開始（日付・編集）を選んでください（または「今から表示（編集）」をONにしてください）。")
            else:
                start_dt = dt.datetime.combine(start_date_edit, dt.time(0, 0, 0, tzinfo=JST))
                e_start = start_dt.isoformat(timespec="seconds")

    with e6:
        no_end_default = (cur.get("end_at") in (None, ""))  # DBがNULL/空なら無期限扱い
        no_end_edit = st.checkbox("終了なし（無期限・編集）", value=no_end_default, key=f"p_no_end_{nid}")

        end_date_edit = st.date_input(
            "表示終了（日付・編集）",
            value=cur_end_date,
            disabled=no_end_edit,
            key=f"p_end_date_{nid}",
        )

        if no_end_edit:
            e_end = ""
        else:
            if end_date_edit is None:
                e_end = ""
                st.warning("表示終了（日付・編集）を選んでください（または「終了なし（無期限・編集）」をONにしてください）。")
            else:
                end_dt = dt.datetime.combine(end_date_edit, dt.time(23, 59, 59, tzinfo=JST))
                e_end = end_dt.isoformat(timespec="seconds")

    with e7:
        e_apps = st.text_input(
            "対象アプリ（CSV・任意）",
            value=(cur.get("target_apps") or ""),
            key=f"p_apps_{nid}",
        )

    do_update = st.button("💾 更新する", key=f"btn_update_{nid}")

    if do_update:
        errs: list[str] = []
        if not (e_title or "").strip():
            errs.append("タイトルは必須です。")
        if not (e_body or "").strip():
            errs.append("本文は必須です。")

        if not (e_start or "").strip():
            errs.append("表示開始が未設定です（「今から表示（編集）」ON または 日付選択が必要）。")
        elif not validate_iso8601(e_start, allow_empty=False):
            errs.append("表示開始の形式が不正です（ISO8601）。")

        if (e_end or "").strip() and not validate_iso8601(e_end, allow_empty=True):
            errs.append("表示終了の形式が不正です（ISO8601）。")

        if errs:
            st.error("\n".join([f"- {e}" for e in errs]))
        else:
            update_notice(
                _DB_PATH,
                nid,
                {
                    "kind": e_kind,
                    "title": e_title.strip(),
                    "body": e_body.strip(),
                    "severity": e_sev,
                    "status": e_status,
                    "audience_type": "all",
                    "audience_key": None,
                    "start_at": e_start.strip(),
                    "end_at": e_end.strip() if e_end.strip() else None,
                    "pinned": e_pinned,
                    "target_apps": e_apps.strip() if e_apps.strip() else None,
                },
            )
            st.success("更新しました。")
            st.rerun()


if __name__ == "__main__":
    main()
