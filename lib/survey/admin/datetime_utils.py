# -*- coding: utf-8 -*-

# auth_portal_app/lib/survey/admin/datetime_utils.py

# ============================================================
# アンケート管理 日時処理
#
# 機能：
# - UTC現在日時を取得する
# - 回答開始日・回答期限をUTC日時へ変換する
# - ISO形式日時をUTC datetimeへ変換する
# - 保存日時をJSTの日付・表示文字列へ変換する
#
# 方針：
# - 保存時刻はUTCを基準とする
# - 管理画面表示時だけJSTへ変換する
# - Streamlitには依存しない
# ============================================================

from __future__ import annotations


# ============================================================
# imports
# ============================================================

from datetime import (
    date,
    datetime,
    time,
    timezone,
)

from typing import Any
from zoneinfo import ZoneInfo


# ============================================================
# 定数
# ============================================================

JST = ZoneInfo(
    "Asia/Tokyo"
)

UTC = timezone.utc


# ============================================================
# UTC現在日時
# ============================================================

def utc_now_iso() -> str:
    return datetime.now(
        UTC,
    ).isoformat(
        timespec="seconds",
    )


# ============================================================
# 回答開始日
# ============================================================

def date_to_start_utc_iso(
    value: date,
) -> str:
    local_value = datetime.combine(
        value,
        time(
            0,
            0,
            0,
        ),
        tzinfo=JST,
    )

    return local_value.astimezone(
        UTC,
    ).isoformat(
        timespec="seconds",
    )


# ============================================================
# 回答期限
# ============================================================

def date_to_end_utc_iso(
    value: date,
) -> str:
    local_value = datetime.combine(
        value,
        time(
            23,
            59,
            59,
        ),
        tzinfo=JST,
    )

    return local_value.astimezone(
        UTC,
    ).isoformat(
        timespec="seconds",
    )


# ============================================================
# ISO日時解析
# ============================================================

def parse_iso_datetime(
    value: Any,
) -> datetime | None:
    normalized = str(
        value or "",
    ).strip()

    if not normalized:
        return None

    if normalized.endswith(
        "Z"
    ):
        normalized = (
            normalized[:-1]
            + "+00:00"
        )

    try:
        parsed = datetime.fromisoformat(
            normalized,
        )

    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=UTC,
        )

    return parsed.astimezone(
        UTC,
    )


# ============================================================
# JST日付
# ============================================================

def iso_to_jst_date(
    value: Any,
    *,
    default: date | None = None,
) -> date:
    parsed = parse_iso_datetime(
        value,
    )

    if parsed is None:
        return (
            default
            or datetime.now(
                JST,
            ).date()
        )

    return parsed.astimezone(
        JST,
    ).date()


# ============================================================
# JST表示
# ============================================================

def format_datetime_jst(
    value: Any,
    *,
    empty_text: str = "設定なし",
) -> str:
    parsed = parse_iso_datetime(
        value,
    )

    if parsed is None:
        return empty_text

    return parsed.astimezone(
        JST,
    ).strftime(
        "%Y年%m月%d日 %H:%M",
    )