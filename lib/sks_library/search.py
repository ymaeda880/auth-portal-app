# -*- coding: utf-8 -*-
# auth_portal_app/lib/sks_library/search.py
# ============================================================
# SKSライブラリー キーワード検索
#
# 機能：
# - 蔵書データに対する通常キーワード検索を行う
# - AND検索 / OR検索に対応する
# - 検索対象項目を指定できる
#
# 方針：
# - AIは使用しない
# - 表示用の元データは変更しない
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
import re

import pandas as pd

from .loader import (
    INTERNAL_ID_COLUMN,
    SKS_COLUMNS,
    normalize_for_search,
)


# ============================================================
# 検索対象
# ============================================================
SEARCH_TARGETS = {
    "すべて": SKS_COLUMNS,
    "タイトル": [
        "タイトル",
    ],
    "編著者": [
        "編著者",
    ],
    "発行者": [
        "発行者",
    ],
    "分類: NDC": [
        "分類: NDC",
    ],
    "棚番号-段": [
        "棚番号-段",
    ],
    "発行年": [
        "発行年",
    ],
    "言語": [
        "言語",
    ],
    "注記": [
        "注記：原著名／仮訳、ISBN等",
    ],
    "貴重書": [
        "貴重書",
    ],
    "タグ": [
        "タグ",
    ],
}


# ============================================================
# キーワード分割
# ============================================================
def split_search_terms(
    query: str,
) -> list[str]:
    """
    スペース，読点，カンマ等で検索語を分割する．
    """

    raw = str(
        query or ""
    ).strip()

    if not raw:
        return []

    terms = re.split(
        r"[\s,，、]+",
        raw,
    )

    return [
        normalize_for_search(term)
        for term in terms
        if str(term or "").strip()
    ]


# ============================================================
# 検索対象列取得
# ============================================================
def resolve_search_columns(
    target: str,
) -> list[str]:
    """
    UIで指定された検索対象から実際の列名を取得する．
    """

    target_name = str(
        target or "すべて"
    ).strip()

    return list(
        SEARCH_TARGETS.get(
            target_name,
            SKS_COLUMNS,
        )
    )


# ============================================================
# 検索用行文字列
# ============================================================
def _build_row_search_text(
    row: pd.Series,
    columns: list[str],
) -> str:
    values = [
        normalize_for_search(
            row.get(col, "")
        )
        for col in columns
    ]

    return "\n".join(values)


# ============================================================
# キーワード検索
# ============================================================
def search_books(
    df: pd.DataFrame,
    *,
    query: str,
    mode: str = "AND",
    target: str = "すべて",
) -> pd.DataFrame:
    """
    キーワードによるAND / OR検索を行う．
    """

    terms = split_search_terms(
        query,
    )

    # ------------------------------------------------------------
    # キーワード未入力
    # ------------------------------------------------------------
    if not terms:
        return df.iloc[0:0].copy()

    columns = resolve_search_columns(
        target,
    )

    mode_upper = str(
        mode or "AND"
    ).strip().upper()

    if mode_upper not in (
        "AND",
        "OR",
    ):
        mode_upper = "AND"

    # ------------------------------------------------------------
    # 行ごとの検索判定
    # ------------------------------------------------------------
    matched_indices: list[int] = []

    for idx, row in df.iterrows():
        haystack = _build_row_search_text(
            row,
            columns,
        )

        if mode_upper == "AND":
            matched = all(
                term in haystack
                for term in terms
            )

        else:
            matched = any(
                term in haystack
                for term in terms
            )

        if matched:
            matched_indices.append(
                idx
            )

    # ------------------------------------------------------------
    # 結果
    # ------------------------------------------------------------
    result = df.loc[
        matched_indices
    ].copy()

    result.reset_index(
        drop=True,
        inplace=True,
    )

    return result