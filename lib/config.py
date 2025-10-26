# ─────────────────────────────────────────────────────────────
# lib/config.py
# 共通設定（パス・JWT・Cookie・ラベルなど）
# ─────────────────────────────────────────────────────────────
from __future__ import annotations
from pathlib import Path
import streamlit as st

# ========= パス類 =========
APP_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = APP_ROOT / "data"
USERS_FILE = DATA_DIR / "users.json"
LOGIN_LOG = DATA_DIR / "login_users.jsonl"
SETTINGS_FILE = APP_ROOT / ".streamlit/settings.toml"

# ========= JWT / Cookie 設定 =========
# COOKIE_NAME = "prec_sso"
# JWT_ALGO = "HS256"
# JWT_TTL_SECONDS = 60 * 60  # 1 hour
# JWT_ISS = "prec-auth"
# JWT_AUD = "prec-internal"
# JWT_SECRET = st.secrets.get("AUTH_SECRET", "CHANGE_ME")

# ============================================
# アプリ名の表示・説明設定
# ============================================

APP_LABELS = {
    "bot":            "🤖 社内ボット（RAG）",
    "minutes":        "📝 議事録ジェネレータ",
    "image_maker":    "🎨 画像生成",
    "slide_viewer":   "📽️ スライドビューア",
    "login_test":     "🔐 ログインテスト",
    "command_station":"🛠️ コマンドステーション",
    "doc_manager":    "📚 文書整理・OCR",
    "auth_portal":    "🔐 認証ポータル",
}

APP_HELP = {
    "bot":            "過去報告書のRAG検索とチャット",
    "minutes":        "音声/テキストから議事録を作成",
    "image_maker":    "プリセット付き画像生成ツール",
    "slide_viewer":   "PPTX→PDFの閲覧・配布",
    "login_test":     "SSO/Cookie動作確認用",
    "command_station":"Git/サービス操作など運用ツール",
    "doc_manager":    "PDF整理・OCR・ベクトル化",
    "auth_portal":    "ユーザー/権限/SSOの管理",
}