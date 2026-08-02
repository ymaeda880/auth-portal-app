# -*- coding: utf-8 -*-
# auth_portal_app/lib/survey/paths.py
# ============================================================
# 社内アンケート 保存パス
#
# 機能：
# - Storages ルートを解決する
# - 管理者用アンケート保存領域を定義する
# - アンケート定義・回答・履歴・DBの保存先を返す
#
# 方針：
# - 保存先は Storages/_admin/survey に固定する
# - auth_portal_app などのアプリ名は保存パスに含めない
# - ディレクトリ作成は ensure_survey_dirs() で明示的に行う
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from dataclasses import dataclass
from pathlib import Path

from common_lib.storage.external_ssd_root import (
    resolve_storage_subdir_root,
)


# ============================================================
# 定数
# ============================================================
SURVEY_OWNER_SUB = "_admin"
SURVEY_DIRNAME = "survey"

CURRENT_DIRNAME = "current"
DEFINITIONS_DIRNAME = "definitions"
RESPONSES_DIRNAME = "responses"
HISTORY_DIRNAME = "history"
ARCHIVE_DIRNAME = "archive"
INDEX_DIRNAME = "index"

SURVEY_DB_FILENAME = "survey.sqlite3"
CURRENT_SURVEY_TEX_FILENAME = "survey.svtex"
CURRENT_SURVEY_JSON_FILENAME = "survey_definition.json"
CURRENT_STATUS_JSON_FILENAME = "survey.json"


# ============================================================
# 保存パス
# ============================================================
@dataclass(frozen=True)
class SurveyPaths:
    storage_root: Path
    survey_root: Path

    current_root: Path
    definitions_root: Path
    responses_root: Path
    history_root: Path
    archive_root: Path
    index_root: Path

    db_path: Path

    current_svtex_path: Path
    current_definition_path: Path
    current_status_path: Path


# ============================================================
# 保存パス解決
# ============================================================
def resolve_survey_paths(
    projects_root: Path,
) -> SurveyPaths:
    # ------------------------------------------------------------
    # Storagesルートを解決
    # ------------------------------------------------------------
    storage_root = resolve_storage_subdir_root(
        projects_root,
        subdir="Storages",
    )

    # ------------------------------------------------------------
    # アンケート専用ルート
    # ------------------------------------------------------------
    survey_root = (
        storage_root
        / SURVEY_OWNER_SUB
        / SURVEY_DIRNAME
    )

    current_root = survey_root / CURRENT_DIRNAME
    definitions_root = survey_root / DEFINITIONS_DIRNAME
    responses_root = survey_root / RESPONSES_DIRNAME
    history_root = survey_root / HISTORY_DIRNAME
    archive_root = survey_root / ARCHIVE_DIRNAME
    index_root = survey_root / INDEX_DIRNAME

    return SurveyPaths(
        storage_root=storage_root,
        survey_root=survey_root,
        current_root=current_root,
        definitions_root=definitions_root,
        responses_root=responses_root,
        history_root=history_root,
        archive_root=archive_root,
        index_root=index_root,
        db_path=index_root / SURVEY_DB_FILENAME,
        current_svtex_path=(
            current_root
            / CURRENT_SURVEY_TEX_FILENAME
        ),
        current_definition_path=(
            current_root
            / CURRENT_SURVEY_JSON_FILENAME
        ),
        current_status_path=(
            current_root
            / CURRENT_STATUS_JSON_FILENAME
        ),
    )


# ============================================================
# ディレクトリ作成
# ============================================================
def ensure_survey_dirs(
    paths: SurveyPaths,
) -> None:
    # ------------------------------------------------------------
    # アンケート保存領域を初期化
    # ------------------------------------------------------------
    dirs = [
        paths.survey_root,
        paths.current_root,
        paths.definitions_root,
        paths.responses_root,
        paths.history_root,
        paths.archive_root,
        paths.index_root,
    ]

    for directory in dirs:
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )


# ============================================================
# アンケート定義保存先
# ============================================================
def survey_definition_dir(
    paths: SurveyPaths,
    *,
    survey_id: str,
    version: int,
) -> Path:
    # ------------------------------------------------------------
    # アンケートID・バージョン別保存先
    # ------------------------------------------------------------
    safe_survey_id = _validate_path_component(
        survey_id,
        field_name="survey_id",
    )

    safe_version = _validate_version(version)

    return (
        paths.definitions_root
        / safe_survey_id
        / f"v{safe_version}"
    )


def survey_definition_svtex_path(
    paths: SurveyPaths,
    *,
    survey_id: str,
    version: int,
) -> Path:
    definition_dir = survey_definition_dir(
        paths,
        survey_id=survey_id,
        version=version,
    )

    return definition_dir / CURRENT_SURVEY_TEX_FILENAME


def survey_definition_json_path(
    paths: SurveyPaths,
    *,
    survey_id: str,
    version: int,
) -> Path:
    definition_dir = survey_definition_dir(
        paths,
        survey_id=survey_id,
        version=version,
    )

    return definition_dir / CURRENT_SURVEY_JSON_FILENAME


# ============================================================
# 回答保存先
# ============================================================
def survey_response_dir(
    paths: SurveyPaths,
    *,
    survey_id: str,
) -> Path:
    # ------------------------------------------------------------
    # アンケート別回答保存先
    # ------------------------------------------------------------
    safe_survey_id = _validate_path_component(
        survey_id,
        field_name="survey_id",
    )

    return paths.responses_root / safe_survey_id


def survey_user_response_path(
    paths: SurveyPaths,
    *,
    survey_id: str,
    user_sub: str,
) -> Path:
    # ------------------------------------------------------------
    # ユーザーごとの最新回答JSON
    # ------------------------------------------------------------
    response_dir = survey_response_dir(
        paths,
        survey_id=survey_id,
    )

    safe_user_sub = _validate_path_component(
        user_sub,
        field_name="user_sub",
    )

    return response_dir / f"{safe_user_sub}.json"


# ============================================================
# 回答履歴保存先
# ============================================================
def survey_response_history_dir(
    paths: SurveyPaths,
    *,
    survey_id: str,
    user_sub: str,
) -> Path:
    # ------------------------------------------------------------
    # ユーザーごとの再回答履歴
    # ------------------------------------------------------------
    safe_survey_id = _validate_path_component(
        survey_id,
        field_name="survey_id",
    )

    safe_user_sub = _validate_path_component(
        user_sub,
        field_name="user_sub",
    )

    return (
        paths.history_root
        / safe_survey_id
        / safe_user_sub
    )


# ============================================================
# アーカイブ保存先
# ============================================================
def survey_archive_dir(
    paths: SurveyPaths,
    *,
    survey_id: str,
    version: int,
) -> Path:
    # ------------------------------------------------------------
    # 終了・アーカイブ済みアンケート保存先
    # ------------------------------------------------------------
    safe_survey_id = _validate_path_component(
        survey_id,
        field_name="survey_id",
    )

    safe_version = _validate_version(version)

    return (
        paths.archive_root
        / safe_survey_id
        / f"v{safe_version}"
    )


# ============================================================
# 内部関数：パス要素検証
# ============================================================
def _validate_path_component(
    value: str,
    *,
    field_name: str,
) -> str:
    # ------------------------------------------------------------
    # パストラバーサル防止
    # ------------------------------------------------------------
    cleaned = str(value or "").strip()

    if not cleaned:
        raise ValueError(
            f"{field_name}が空です．"
        )

    if cleaned in {".", ".."}:
        raise ValueError(
            f"{field_name}に不正な値が指定されています．"
        )

    if "/" in cleaned or "\\" in cleaned:
        raise ValueError(
            f"{field_name}にパス区切り文字は使用できません．"
        )

    return cleaned


def _validate_version(
    version: int,
) -> int:
    # ------------------------------------------------------------
    # バージョン番号検証
    # ------------------------------------------------------------
    try:
        value = int(version)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "versionは整数で指定してください．"
        ) from exc

    if value < 1:
        raise ValueError(
            "versionは1以上で指定してください．"
        )

    return value