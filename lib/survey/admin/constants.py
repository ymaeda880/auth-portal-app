# -*- coding: utf-8 -*-

# auth_portal_app/lib/survey/admin/constants.py

# ============================================================
# アンケート管理 定数
#
# 機能：
# - 管理画面で使用する状態値を定義する
# - 管理画面で使用するsession_stateキーを定義する
#
# 方針：
# - Streamlit描画処理は持たない
# - アンケート管理画面固有の定数だけを管理する
# ============================================================

from __future__ import annotations


# ============================================================
# アンケート状態
# ============================================================

STATUS_DRAFT = "draft"
STATUS_SCHEDULED = "scheduled"
STATUS_RUNNING = "running"
STATUS_CLOSED = "closed"


STATUS_LABELS = {
    STATUS_DRAFT: "登録済み",
    STATUS_SCHEDULED: "実施予定",
    STATUS_RUNNING: "実施中",
    STATUS_CLOSED: "終了",
}


# ============================================================
# 質問形式
# ============================================================

CHOICE_TYPES = {
    "radio",
    "select",
    "rating",
}

TEXT_TYPES = {
    "text",
    "textarea",
}


# ============================================================
# session_stateキー
# ============================================================

K_UPLOAD_TEXT = "survey_admin_upload_text"

K_UPLOAD_NAME = "survey_admin_upload_name"

K_PARSE_RESULT = "survey_admin_parse_result"

K_SELECTED_RECORD = "survey_admin_selected_record"

K_RECORD_RADIO = "survey_admin_record_radio"

K_PUBLICATION_MESSAGE = (
    "survey_admin_publication_message"
)