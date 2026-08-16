# -*- coding: utf-8 -*-
# auth_portal_app/lib/survey/storage.py
# ============================================================
# 社内アンケート ファイル保存
#
# 機能：
# - JSONファイルを安全に読み書きする
# - SurveyTex原本と解析済み定義を保存する
# - 現在のアンケート情報を保存・取得する
# - ユーザーごとの最新回答を保存・取得する
# - 再回答前の回答を履歴として保存する
#
# 方針：
# - JSONはUTF-8で保存する
# - 一時ファイルへ書き込んでから置き換える
# - 保存処理では必要なディレクトリだけを作成する
# - Streamlitには依存しない
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import (
    SurveyDefinition,
    SurveyResponse,
    SurveyStatus,
)
from .paths import (
    SurveyPaths,
    survey_definition_dir,
    survey_definition_json_path,
    survey_definition_svtex_path,
    survey_response_history_dir,
    survey_user_response_path,
)


# ============================================================
# JSON読み込み
# ============================================================
def read_json_file(
    path: Path,
) -> dict[str, Any]:
    # ------------------------------------------------------------
    # JSONファイルを読み込む
    # ------------------------------------------------------------
    if not path.exists():
        raise FileNotFoundError(
            f"JSONファイルが見つかりません：{path}"
        )

    if not path.is_file():
        raise ValueError(
            f"JSONファイルではありません：{path}"
        )

    try:
        text = path.read_text(
            encoding="utf-8-sig",
        )
    except OSError as exc:
        raise OSError(
            f"JSONファイルを読み込めませんでした：{path}"
        ) from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"JSONの形式が不正です：{path}"
            f"（{exc.lineno}行目，{exc.colno}列目）"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"JSONのルートはオブジェクトである必要があります：{path}"
        )

    return data


# ============================================================
# JSON保存
# ============================================================
def write_json_file(
    path: Path,
    data: dict[str, Any],
) -> None:
    # ------------------------------------------------------------
    # JSONファイルを一時ファイル経由で保存する
    # ------------------------------------------------------------
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_text = json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
    )

    _atomic_write_text(
        path=path,
        text=json_text + "\n",
        encoding="utf-8",
    )


# ============================================================
# テキスト保存
# ============================================================
def write_text_file(
    path: Path,
    text: str,
) -> None:
    # ------------------------------------------------------------
    # テキストファイルを一時ファイル経由で保存する
    # ------------------------------------------------------------
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    _atomic_write_text(
        path=path,
        text=text,
        encoding="utf-8",
    )


def read_text_file(
    path: Path,
) -> str:
    # ------------------------------------------------------------
    # UTF-8テキストを読み込む
    # ------------------------------------------------------------
    if not path.exists():
        raise FileNotFoundError(
            f"テキストファイルが見つかりません：{path}"
        )

    if not path.is_file():
        raise ValueError(
            f"テキストファイルではありません：{path}"
        )

    try:
        return path.read_text(
            encoding="utf-8-sig",
        )
    except OSError as exc:
        raise OSError(
            f"テキストファイルを読み込めませんでした：{path}"
        ) from exc


# ============================================================
# SHA-256
# ============================================================
def calculate_text_sha256(
    text: str,
) -> str:
    # ------------------------------------------------------------
    # 文字列のSHA-256を返す
    # ------------------------------------------------------------
    return hashlib.sha256(
        text.encode("utf-8"),
    ).hexdigest()


def calculate_file_sha256(
    path: Path,
) -> str:
    # ------------------------------------------------------------
    # ファイルのSHA-256を返す
    # ------------------------------------------------------------
    if not path.exists():
        raise FileNotFoundError(
            f"ファイルが見つかりません：{path}"
        )

    digest = hashlib.sha256()

    try:
        with path.open("rb") as file_obj:
            while True:
                chunk = file_obj.read(
                    1024 * 1024,
                )

                if not chunk:
                    break

                digest.update(chunk)

    except OSError as exc:
        raise OSError(
            f"ファイルを読み込めませんでした：{path}"
        ) from exc

    return digest.hexdigest()


# ============================================================
# アンケート定義保存
# ============================================================
def save_survey_definition(
    paths: SurveyPaths,
    *,
    definition: SurveyDefinition,
    svtex_text: str,
) -> None:
    # ------------------------------------------------------------
    # ID・バージョン別の定義保存先
    # ------------------------------------------------------------
    definition_dir = survey_definition_dir(
        paths,
        survey_id=definition.survey_id,
        version=definition.version,
    )

    definition_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    svtex_path = survey_definition_svtex_path(
        paths,
        survey_id=definition.survey_id,
        version=definition.version,
    )

    definition_path = survey_definition_json_path(
        paths,
        survey_id=definition.survey_id,
        version=definition.version,
    )

    # ------------------------------------------------------------
    # SurveyTex原本と解析済みJSONを保存
    # ------------------------------------------------------------
    write_text_file(
        svtex_path,
        svtex_text,
    )

    write_json_file(
        definition_path,
        definition.to_dict(),
    )


def load_survey_definition(
    paths: SurveyPaths,
    *,
    survey_id: str,
    version: int,
) -> SurveyDefinition:
    # ------------------------------------------------------------
    # ID・バージョン別定義を読み込む
    # ------------------------------------------------------------
    definition_path = survey_definition_json_path(
        paths,
        survey_id=survey_id,
        version=version,
    )

    data = read_json_file(
        definition_path,
    )

    return SurveyDefinition.from_dict(
        data,
    )


def load_survey_svtex(
    paths: SurveyPaths,
    *,
    survey_id: str,
    version: int,
) -> str:
    # ------------------------------------------------------------
    # ID・バージョン別SurveyTex原本を読み込む
    # ------------------------------------------------------------
    svtex_path = survey_definition_svtex_path(
        paths,
        survey_id=survey_id,
        version=version,
    )

    return read_text_file(
        svtex_path,
    )


def survey_definition_exists(
    paths: SurveyPaths,
    *,
    survey_id: str,
    version: int,
) -> bool:
    # ------------------------------------------------------------
    # 定義JSONとSurveyTex原本が両方存在するか確認
    # ------------------------------------------------------------
    definition_path = survey_definition_json_path(
        paths,
        survey_id=survey_id,
        version=version,
    )

    svtex_path = survey_definition_svtex_path(
        paths,
        survey_id=survey_id,
        version=version,
    )

    return (
        definition_path.is_file()
        and svtex_path.is_file()
    )


# ============================================================
# 現在のアンケート保存
# ============================================================
def save_current_survey(
    paths: SurveyPaths,
    *,
    definition: SurveyDefinition,
    status: SurveyStatus,
    svtex_text: str,
) -> None:
    # ------------------------------------------------------------
    # currentディレクトリを初期化
    # ------------------------------------------------------------
    paths.current_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ------------------------------------------------------------
    # 現在のSurveyTex原本
    # ------------------------------------------------------------
    write_text_file(
        paths.current_svtex_path,
        svtex_text,
    )

    # ------------------------------------------------------------
    # 現在の解析済み定義
    # ------------------------------------------------------------
    write_json_file(
        paths.current_definition_path,
        definition.to_dict(),
    )

    # ------------------------------------------------------------
    # 現在の管理状態
    # ------------------------------------------------------------
    write_json_file(
        paths.current_status_path,
        status.to_dict(),
    )


def load_current_definition(
    paths: SurveyPaths,
) -> SurveyDefinition | None:
    # ------------------------------------------------------------
    # 現在の解析済み定義を読み込む
    # ------------------------------------------------------------
    if not paths.current_definition_path.is_file():
        return None

    data = read_json_file(
        paths.current_definition_path,
    )

    return SurveyDefinition.from_dict(
        data,
    )


def load_current_status(
    paths: SurveyPaths,
) -> SurveyStatus | None:
    # ------------------------------------------------------------
    # 現在のアンケート状態を読み込む
    # ------------------------------------------------------------
    if not paths.current_status_path.is_file():
        return None

    data = read_json_file(
        paths.current_status_path,
    )

    return SurveyStatus.from_dict(
        data,
    )


def load_current_svtex(
    paths: SurveyPaths,
) -> str | None:
    # ------------------------------------------------------------
    # 現在のSurveyTex原本を読み込む
    # ------------------------------------------------------------
    if not paths.current_svtex_path.is_file():
        return None

    return read_text_file(
        paths.current_svtex_path,
    )


def current_survey_exists(
    paths: SurveyPaths,
) -> bool:
    # ------------------------------------------------------------
    # currentに必要な3ファイルが存在するか確認
    # ------------------------------------------------------------
    return (
        paths.current_svtex_path.is_file()
        and paths.current_definition_path.is_file()
        and paths.current_status_path.is_file()
    )


def clear_current_survey(
    paths: SurveyPaths,
) -> None:
    # ------------------------------------------------------------
    # current配下だけを削除する
    # ------------------------------------------------------------
    if not paths.current_root.exists():
        return

    for path in (
        paths.current_svtex_path,
        paths.current_definition_path,
        paths.current_status_path,
    ):
        if path.is_file():
            path.unlink()


# ============================================================
# アンケート関連ファイル完全削除
# ============================================================
def delete_survey_files_completely(
    paths: SurveyPaths,
    *,
    survey_id: str,
    version: int,
    clear_current: bool = False,
) -> None:
    # ------------------------------------------------------------
    # 入力値確認
    # ------------------------------------------------------------
    normalized_survey_id = str(
        survey_id or ""
    ).strip()

    if not normalized_survey_id:
        raise ValueError(
            "survey_idが空です．"
        )

    normalized_version = int(
        version
    )

    if normalized_version < 1:
        raise ValueError(
            "versionは1以上で指定してください．"
        )

    # ------------------------------------------------------------
    # 定義保存フォルダー
    # ------------------------------------------------------------
    definition_version_dir = survey_definition_dir(
        paths,
        survey_id=normalized_survey_id,
        version=normalized_version,
    )

    definition_survey_dir = (
        definition_version_dir.parent
    )

    # ------------------------------------------------------------
    # 回答保存フォルダー
    # ------------------------------------------------------------
    response_dir = (
        paths.responses_root
        / normalized_survey_id
    )

    # ------------------------------------------------------------
    # 回答履歴保存フォルダー
    # ------------------------------------------------------------
    history_dir = (
        paths.history_root
        / normalized_survey_id
    )

    delete_targets = (
        definition_survey_dir,
        response_dir,
        history_dir,
    )

    # ------------------------------------------------------------
    # 削除対象確認
    # ------------------------------------------------------------
    for target in delete_targets:
        if not target.exists():
            continue

        if not target.is_dir():
            raise ValueError(
                "削除対象がフォルダーではありません："
                f"{target}"
            )

    # ------------------------------------------------------------
    # 定義・回答・履歴を削除
    # ------------------------------------------------------------
    for target in delete_targets:
        if target.is_dir():
            shutil.rmtree(
                target,
            )

    # ------------------------------------------------------------
    # currentとして残っている場合
    # ------------------------------------------------------------
    if clear_current:
        clear_current_survey(
            paths,
        )


# ============================================================
# ユーザー回答保存
# ============================================================
def load_user_response(
    paths: SurveyPaths,
    *,
    survey_id: str,
    user_sub: str,
) -> SurveyResponse | None:
    # ------------------------------------------------------------
    # ユーザーの最新回答を読み込む
    # ------------------------------------------------------------
    response_path = survey_user_response_path(
        paths,
        survey_id=survey_id,
        user_sub=user_sub,
    )

    if not response_path.is_file():
        return None

    data = read_json_file(
        response_path,
    )

    return SurveyResponse.from_dict(
        data,
    )


def save_user_response(
    paths: SurveyPaths,
    *,
    response: SurveyResponse,
    preserve_previous: bool = True,
) -> None:
    # ------------------------------------------------------------
    # 最新回答の保存先
    # ------------------------------------------------------------
    response_path = survey_user_response_path(
        paths,
        survey_id=response.survey_id,
        user_sub=response.user_sub,
    )

    response_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ------------------------------------------------------------
    # 既存回答があれば履歴へ退避
    # ------------------------------------------------------------
    if preserve_previous and response_path.is_file():
        _archive_existing_response(
            paths,
            survey_id=response.survey_id,
            user_sub=response.user_sub,
            response_path=response_path,
        )

    # ------------------------------------------------------------
    # 新しい回答を最新回答として保存
    # ------------------------------------------------------------
    write_json_file(
        response_path,
        response.to_dict(),
    )


def user_response_exists(
    paths: SurveyPaths,
    *,
    survey_id: str,
    user_sub: str,
) -> bool:
    # ------------------------------------------------------------
    # 最新回答の存在確認
    # ------------------------------------------------------------
    response_path = survey_user_response_path(
        paths,
        survey_id=survey_id,
        user_sub=user_sub,
    )

    return response_path.is_file()


# ============================================================
# 回答履歴
# ============================================================
def list_user_response_history(
    paths: SurveyPaths,
    *,
    survey_id: str,
    user_sub: str,
) -> list[Path]:
    # ------------------------------------------------------------
    # ユーザー回答履歴を新しい順に返す
    # ------------------------------------------------------------
    history_dir = survey_response_history_dir(
        paths,
        survey_id=survey_id,
        user_sub=user_sub,
    )

    if not history_dir.exists():
        return []

    history_files = [
        path
        for path in history_dir.glob("*.json")
        if path.is_file()
    ]

    return sorted(
        history_files,
        key=lambda path: path.name,
        reverse=True,
    )


def load_response_history_file(
    history_path: Path,
) -> SurveyResponse:
    # ------------------------------------------------------------
    # 指定した回答履歴JSONを読み込む
    # ------------------------------------------------------------
    data = read_json_file(
        history_path,
    )

    return SurveyResponse.from_dict(
        data,
    )


# ============================================================
# アンケート定義一覧
# ============================================================
def list_survey_definitions(
    paths: SurveyPaths,
) -> list[tuple[str, int]]:
    # ------------------------------------------------------------
    # definitions配下のアンケートIDとバージョンを列挙する
    # ------------------------------------------------------------
    if not paths.definitions_root.exists():
        return []

    results: list[tuple[str, int]] = []

    for survey_dir in paths.definitions_root.iterdir():
        if not survey_dir.is_dir():
            continue

        survey_id = survey_dir.name

        for version_dir in survey_dir.iterdir():
            if not version_dir.is_dir():
                continue

            version_name = version_dir.name

            if not version_name.startswith("v"):
                continue

            try:
                version = int(
                    version_name[1:],
                )
            except ValueError:
                continue

            definition_path = (
                version_dir
                / "survey_definition.json"
            )

            svtex_path = (
                version_dir
                / "survey.svtex"
            )

            if (
                definition_path.is_file()
                and svtex_path.is_file()
            ):
                results.append(
                    (
                        survey_id,
                        version,
                    )
                )

    return sorted(
        results,
        key=lambda item: (
            item[0],
            item[1],
        ),
        reverse=True,
    )


# ============================================================
# 回答ファイル一覧
# ============================================================
def list_survey_response_files(
    paths: SurveyPaths,
    *,
    survey_id: str,
) -> list[Path]:
    # ------------------------------------------------------------
    # アンケートに属する最新回答JSONを返す
    # ------------------------------------------------------------
    response_root = (
        paths.responses_root
        / survey_id
    )

    # ===== DEBUG START =====
    # print(
    #     "[survey response files]"
    #     f" responses_root={paths.responses_root}"
    # )
    # print(
    #     "[survey response files]"
    #     f" survey_id={survey_id}"
    # )
    # print(
    #     "[survey response files]"
    #     f" response_root={response_root}"
    # )
    # print(
    #     "[survey response files]"
    #     f" exists={response_root.exists()}"
    # )
    # print(
    #     "[survey response files]"
    #     f" files={list(response_root.glob('*.json'))}"
    # )
    # ===== DEBUG END =====


    if not response_root.exists():
        return []

    response_files = [
        path
        for path in response_root.glob("*.json")
        if path.is_file()
    ]

    return sorted(
        response_files,
        key=lambda path: path.name,
    )


def load_all_survey_responses(
    paths: SurveyPaths,
    *,
    survey_id: str,
) -> list[SurveyResponse]:
    # ------------------------------------------------------------
    # アンケートに属する最新回答をすべて読み込む
    # ------------------------------------------------------------
    responses: list[SurveyResponse] = []

    for response_path in list_survey_response_files(
        paths,
        survey_id=survey_id,
    ):
        try:
            response = SurveyResponse.from_dict(
                read_json_file(
                    response_path,
                )
            )
        except (
            OSError,
            ValueError,
        ):
            continue

        responses.append(
            response,
        )

    return responses


# ============================================================
# 内部関数：既存回答の履歴保存
# ============================================================
def _archive_existing_response(
    paths: SurveyPaths,
    *,
    survey_id: str,
    user_sub: str,
    response_path: Path,
) -> Path:
    # ------------------------------------------------------------
    # 履歴ディレクトリ
    # ------------------------------------------------------------
    history_dir = survey_response_history_dir(
        paths,
        survey_id=survey_id,
        user_sub=user_sub,
    )

    history_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ------------------------------------------------------------
    # 履歴ファイル名
    # ------------------------------------------------------------
    timestamp = _now_utc_filename()

    history_path = (
        history_dir
        / f"{timestamp}.json"
    )

    suffix_number = 1

    while history_path.exists():
        history_path = (
            history_dir
            / f"{timestamp}_{suffix_number}.json"
        )
        suffix_number += 1

    # ------------------------------------------------------------
    # 既存回答を履歴へコピー
    # ------------------------------------------------------------
    shutil.copy2(
        response_path,
        history_path,
    )

    return history_path


# ============================================================
# 内部関数：原子的テキスト保存
# ============================================================
def _atomic_write_text(
    *,
    path: Path,
    text: str,
    encoding: str,
) -> None:
    # ------------------------------------------------------------
    # 保存先と同じディレクトリに一時ファイルを作成する
    # ------------------------------------------------------------
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            newline="\n",
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_file.write(text)
            temp_file.flush()
            os.fsync(
                temp_file.fileno(),
            )

            temp_path = Path(
                temp_file.name,
            )

        # --------------------------------------------------------
        # 同一ファイルシステム内で置換
        # --------------------------------------------------------
        os.replace(
            temp_path,
            path,
        )

    except Exception:
        if (
            temp_path is not None
            and temp_path.exists()
        ):
            try:
                temp_path.unlink()
            except OSError:
                pass

        raise


# ============================================================
# 内部関数：UTC時刻
# ============================================================
def _now_utc_filename() -> str:
    # ------------------------------------------------------------
    # ファイル名に使用できるUTC時刻文字列
    # ------------------------------------------------------------
    return datetime.now(
        timezone.utc,
    ).strftime(
        "%Y%m%dT%H%M%S_%fZ",
    )