# -*- coding: utf-8 -*-

# auth_portal_app/lib/usage_guide/registry.py
# ============================================================
# PAIS使い方ガイド 登録
#
# 機能：
# - 使い方ページに表示する大項目を登録する
# - PAIS全体説明パネルを登録する
# - 表示順を一元管理する
#
# 方針：
# - pages/130_使い方.py に項目一覧を書かない
# - 項目の追加・削除・並べ替えは本ファイルで行う
# ============================================================

from __future__ import annotations

# ============================================================
# 使い方ガイド
# ============================================================

from .guide_proofreading import GUIDE_PROOFREADING
from .guide_report_creation import GUIDE_REPORT_CREATION
from .guide_chat import GUIDE_CHAT
from .guide_translation import GUIDE_TRANSLATION
from .guide_minutes import GUIDE_MINUTES
from .guide_image import GUIDE_IMAGE

from .guide_document_creation import GUIDE_DOCUMENT_CREATION

from .guide_report_search import GUIDE_REPORT_SEARCH
from .guide_file_management import GUIDE_FILE_MANAGEMENT
from .guide_other import GUIDE_OTHER

from .pais_design_policy import INFO_PAIS_DESIGN_POLICY
from .ai_guideline import INFO_AI_GUIDELINE
from .prec_ai_manual import INFO_PREC_AI_MANUAL
from .development_plan import INFO_DEVELOPMENT_PLAN

from .style_sample import INFO_USAGE_GUIDE_STYLE_SAMPLE

# ============================================================
# models
# ============================================================

from .models import (
    GuideCategory,
    InfoPanel,
)


# ============================================================
# 使い方 大項目
#
# この並び順がページ上の表示順になる
# ============================================================

GUIDE_CATEGORIES: tuple[GuideCategory, ...] = (
    GUIDE_PROOFREADING,
    #GUIDE_REPORT_CREATION,
    GUIDE_CHAT,
    GUIDE_TRANSLATION,
    GUIDE_MINUTES,
    GUIDE_IMAGE,
    GUIDE_DOCUMENT_CREATION,
    #GUIDE_REPORT_SEARCH,
    GUIDE_FILE_MANAGEMENT,
    GUIDE_OTHER,
)


# ============================================================
# PAISについて
#
# 次の段階で登録する
# - PAISの設計思想
# - AIガイドラインについて
# - 現在作成中の機能
# ============================================================

INFO_PANELS: tuple[InfoPanel, ...] = (
    INFO_PAIS_DESIGN_POLICY,
    INFO_AI_GUIDELINE,
    INFO_PREC_AI_MANUAL,
    INFO_DEVELOPMENT_PLAN,
    INFO_USAGE_GUIDE_STYLE_SAMPLE,
)