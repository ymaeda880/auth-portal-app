# -*- coding: utf-8 -*-

# auth_portal_app/lib/usage_guide/models.py

# ============================================================
# PAIS使い方ガイド データモデル
#
# 機能：
# - 大項目を表す GuideCategory を定義する
# - 個別の「やりたいこと」を表す GuideItem を定義する
# - 詳細説明の各節を表す GuideSection を定義する
# - GuideSection 内の小項目を表す GuideSubSection を定義する
# - PAIS全体説明用の InfoPanel を定義する
#
# 方針：
# - 説明内容とStreamlit描画処理を分離する
# - 詳細説明の項目名を固定しすぎない
# - 後から説明項目を自由に追加・削除できるようにする
# - GuideSection は従来どおり body 単独でも使用できる
# - 必要な場合だけ GuideSubSection で詳細を分割する
# ============================================================

from __future__ import annotations


# ============================================================
# imports
# ============================================================

from dataclasses import dataclass, field


# ============================================================
# 詳細説明サブセクション
# ============================================================

@dataclass(frozen=True)
class GuideSubSection:
    """
    GuideSection 内の1つの小項目．

    例：
    - ① 音声ファイルを分割する
    - ② タイムスタンプ付き文字起こしを行う
    - ③ 話者分離を行う
    - ④ 逐語録を修正する

    GuideSection の中をさらに細かく分けたい場合に使用する．
    """

    title: str
    body: str


# ============================================================
# 詳細説明セクション
# ============================================================

@dataclass(frozen=True)
class GuideSection:
    """
    個別説明内の1セクション．

    例：
    - 概要
    - 基本的な流れ
    - 使い方
    - 注意事項
    - 設定
    - 保存場所
    - 事例

    title を自由に設定できるため，
    後から説明項目を追加してもモデル変更を不要とする．

    単純な説明の場合は body のみを使用する．

    詳細をさらに分割したい場合は，
    subsections に GuideSubSection を設定する．
    """

    title: str

    # セクション本文
    body: str = ""

    # セクション内の小項目
    subsections: tuple[GuideSubSection, ...] = field(
        default_factory=tuple,
    )


# ============================================================
# 個別ガイド項目
# ============================================================

@dataclass(frozen=True)
class GuideItem:
    """
    利用者の「やりたいこと」単位の説明．
    """

    key: str
    title: str

    # 一覧表示用の短い説明
    summary: str = ""

    # 利用するPAIS機能
    app_name: str = ""
    page_name: str = ""

    # AI利用情報
    uses_ai: bool | None = None
    ai_note: str = ""

    # 詳細説明
    sections: tuple[GuideSection, ...] = field(
        default_factory=tuple,
    )


# ============================================================
# 大項目
# ============================================================

@dataclass(frozen=True)
class GuideCategory:
    """
    PAISの使い方ページに表示する大項目．

    例：
    - 文章の校正
    - 報告書作成支援
    - チャット
    - 議事録の作成
    """

    key: str
    title: str
    icon: str
    summary: str

    items: tuple[GuideItem, ...] = field(
        default_factory=tuple,
    )


# ============================================================
# PAIS全体説明パネル
# ============================================================

@dataclass(frozen=True)
class InfoPanel:
    """
    「PAISについて」に表示する説明パネル．

    GuideCategoryとは異なり，
    特定のアプリやページへの案内を目的としない．
    """

    key: str
    title: str
    icon: str
    summary: str

    sections: tuple[GuideSection, ...] = field(
        default_factory=tuple,
    )