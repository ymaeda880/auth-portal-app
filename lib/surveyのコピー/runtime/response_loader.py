# -*- coding: utf-8 -*-
# auth_portal_app/lib/survey/runtime/response_loader.py
# ============================================================
# 社内アンケート 回答読込
#
# 機能：
# - ユーザーの現在回答JSONを読み込む
# - 任意の回答JSONを読み込む
# - 回答JSONの基本構造を確認する
# - 回答データを保存用の標準形式へ正規化する
# - 回答ファイルが存在しない場合に未回答として扱う
# - 読込エラーを結果オブジェクトとして返す
#
# 回答保存先：
# - responses/<survey_id>/<user_sub>.json
#
# 履歴保存先：
# - history/<survey_id>/<user_sub>/<UTC日時>.json
#
# 方針：
# - Streamlitには依存しない
# - ファイルが存在しないことはエラーにしない
# - JSON破損や形式不正はエラーとして返す
# - 読込処理ではファイルを書き換えない
# - Pathを引数として受け取り，paths.pyへの依存を抑える
# - 回答本文はdictとして返し，UIやruntime側で利用する
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

import math
from datetime import date, datetime, timezone

# ============================================================
# 定数
# ============================================================
UTC = timezone.utc

RESPONSE_REQUIRED_FIELDS = {
    "survey_id",
    "survey_version",
    "user_sub",
    "answers",
}

RESPONSE_OPTIONAL_FIELDS = {
    "response_id",
    "submitted_at",
    "updated_at",
    "response_revision",
    "definition_sha256",
}

RESPONSE_KNOWN_FIELDS = (
    RESPONSE_REQUIRED_FIELDS
    | RESPONSE_OPTIONAL_FIELDS
)


# ============================================================
# 回答読込エラー
# ============================================================
@dataclass(frozen=True)
class ResponseLoadIssue:
    # ------------------------------------------------------------
    # severity
    # - error
    # - warning
    # ------------------------------------------------------------
    severity: str
    message: str

    field_name: str | None = None
    file_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "message": self.message,
            "field_name": self.field_name,
            "file_path": self.file_path,
        }


# ============================================================
# 回答読込結果
# ============================================================
@dataclass(frozen=True)
class SurveyResponseLoadResult:
    # ------------------------------------------------------------
    # 読込対象
    # ------------------------------------------------------------
    response_path: Path

    # ------------------------------------------------------------
    # ファイル存在
    # ------------------------------------------------------------
    exists: bool

    # ------------------------------------------------------------
    # 正規化済み回答データ
    #
    # ファイルが存在しない場合：
    # - response_data={}
    #
    # 読込エラーの場合：
    # - response_data={}
    # ------------------------------------------------------------
    response_data: dict[str, Any]

    # ------------------------------------------------------------
    # エラー・警告
    # ------------------------------------------------------------
    errors: tuple[ResponseLoadIssue, ...] = ()
    warnings: tuple[ResponseLoadIssue, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.errors

    @property
    def was_loaded(self) -> bool:
        return (
            self.exists
            and self.is_valid
            and bool(self.response_data)
        )

    @property
    def is_unanswered(self) -> bool:
        return not self.exists

    @property
    def answers(self) -> dict[str, Any]:
        answers = self.response_data.get(
            "answers",
            {},
        )

        if not isinstance(
            answers,
            dict,
        ):
            return {}

        return dict(
            answers,
        )

    @property
    def survey_id(self) -> str | None:
        value = self.response_data.get(
            "survey_id",
        )

        if value is None:
            return None

        normalized = str(
            value,
        ).strip()

        return normalized or None

    @property
    def survey_version(self) -> int | None:
        value = self.response_data.get(
            "survey_version",
        )

        if isinstance(
            value,
            bool,
        ):
            return None

        if isinstance(
            value,
            int,
        ):
            return value

        return None

    @property
    def user_sub(self) -> str | None:
        value = self.response_data.get(
            "user_sub",
        )

        if value is None:
            return None

        normalized = str(
            value,
        ).strip()

        return normalized or None

    @property
    def response_revision(self) -> int:
        value = self.response_data.get(
            "response_revision",
            0,
        )

        if isinstance(
            value,
            bool,
        ):
            return 0

        if isinstance(
            value,
            int,
        ):
            return max(
                value,
                0,
            )

        return 0

    @property
    def submitted_at(self) -> datetime | None:
        return parse_response_datetime(
            self.response_data.get(
                "submitted_at",
            )
        )

    @property
    def updated_at(self) -> datetime | None:
        return parse_response_datetime(
            self.response_data.get(
                "updated_at",
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "response_path": str(
                self.response_path,
            ),
            "exists": self.exists,
            "response_data": dict(
                self.response_data,
            ),
            "errors": [
                issue.to_dict()
                for issue in self.errors
            ],
            "warnings": [
                issue.to_dict()
                for issue in self.warnings
            ],
            "is_valid": self.is_valid,
            "was_loaded": self.was_loaded,
            "is_unanswered": self.is_unanswered,
            "survey_id": self.survey_id,
            "survey_version": self.survey_version,
            "user_sub": self.user_sub,
            "response_revision": (
                self.response_revision
            ),
            "submitted_at": (
                self.submitted_at.isoformat()
                if self.submitted_at is not None
                else None
            ),
            "updated_at": (
                self.updated_at.isoformat()
                if self.updated_at is not None
                else None
            ),
            "answers": self.answers,
        }


# ============================================================
# public API：現在回答パスの生成
# ============================================================
def build_current_response_path(
    *,
    responses_root: Path,
    survey_id: str,
    user_sub: str,
) -> Path:
    normalized_survey_id = normalize_path_component(
        survey_id,
        field_name="survey_id",
    )

    normalized_user_sub = normalize_path_component(
        user_sub,
        field_name="user_sub",
    )

    return (
        Path(responses_root)
        / normalized_survey_id
        / f"{normalized_user_sub}.json"
    )


# ============================================================
# public API：現在回答の読込
# ============================================================
def load_current_response(
    *,
    responses_root: Path,
    survey_id: str,
    user_sub: str,
    expected_survey_version: int | None = None,
    expected_definition_sha256: str | None = None,
) -> SurveyResponseLoadResult:
    # ------------------------------------------------------------
    # 現在回答ファイルのパス
    # ------------------------------------------------------------
    response_path = build_current_response_path(
        responses_root=responses_root,
        survey_id=survey_id,
        user_sub=user_sub,
    )
    # ------------------------------------------------------------
    # 回答JSON読込
    # ------------------------------------------------------------
    result = load_response_file(
        response_path,
    )

    if not result.exists:
        return result

    if not result.is_valid:
        return result

    errors = list(
        result.errors,
    )

    warnings = list(
        result.warnings,
    )

    response_data = dict(
        result.response_data,
    )

    # ------------------------------------------------------------
    # アンケートID整合性
    # ------------------------------------------------------------
    loaded_survey_id = response_data.get(
        "survey_id",
    )

    if loaded_survey_id != survey_id:
        errors.append(
            ResponseLoadIssue(
                severity="error",
                message=(
                    "回答ファイルのsurvey_idが"
                    "読込対象のアンケートIDと一致しません．"
                ),
                field_name="survey_id",
                file_path=str(
                    response_path,
                ),
            )
        )

    # ------------------------------------------------------------
    # ユーザーID整合性
    # ------------------------------------------------------------
    loaded_user_sub = response_data.get(
        "user_sub",
    )

    if loaded_user_sub != user_sub:
        errors.append(
            ResponseLoadIssue(
                severity="error",
                message=(
                    "回答ファイルのuser_subが"
                    "読込対象のユーザーIDと一致しません．"
                ),
                field_name="user_sub",
                file_path=str(
                    response_path,
                ),
            )
        )

    # ------------------------------------------------------------
    # アンケートバージョン確認
    #
    # 過去バージョンの回答は読込可能とするが，
    # 現在定義との違いを警告する
    # ------------------------------------------------------------
    if expected_survey_version is not None:
        loaded_version = response_data.get(
            "survey_version",
        )

        if loaded_version != expected_survey_version:
            warnings.append(
                ResponseLoadIssue(
                    severity="warning",
                    message=(
                        "保存済み回答のアンケートバージョンが"
                        "現在の定義と一致しません．"
                        f"保存済み：{loaded_version}，"
                        f"現在：{expected_survey_version}"
                    ),
                    field_name="survey_version",
                    file_path=str(
                        response_path,
                    ),
                )
            )

    # ------------------------------------------------------------
    # 定義ハッシュ確認
    #
    # ハッシュが異なる場合も回答は読込可能とする
    # ------------------------------------------------------------
    if expected_definition_sha256:
        loaded_sha256 = str(
            response_data.get(
                "definition_sha256",
                "",
            )
            or ""
        ).strip()

        if (
            loaded_sha256
            and loaded_sha256
            != expected_definition_sha256
        ):
            warnings.append(
                ResponseLoadIssue(
                    severity="warning",
                    message=(
                        "保存済み回答の定義ハッシュが"
                        "現在のアンケート定義と一致しません．"
                    ),
                    field_name="definition_sha256",
                    file_path=str(
                        response_path,
                    ),
                )
            )

        elif not loaded_sha256:
            warnings.append(
                ResponseLoadIssue(
                    severity="warning",
                    message=(
                        "保存済み回答にdefinition_sha256が"
                        "記録されていません．"
                    ),
                    field_name="definition_sha256",
                    file_path=str(
                        response_path,
                    ),
                )
            )

    return SurveyResponseLoadResult(
        response_path=response_path,
        exists=True,
        response_data=response_data,
        errors=tuple(
            errors,
        ),
        warnings=tuple(
            warnings,
        ),
    )


# ============================================================
# public API：任意の回答JSON読込
# ============================================================
def load_response_file(
    response_path: Path,
) -> SurveyResponseLoadResult:
    normalized_path = Path(
        response_path,
    )

    # ------------------------------------------------------------
    # ファイルが存在しない場合
    #
    # 未回答として扱い，エラーにはしない
    # ------------------------------------------------------------
    if not normalized_path.exists():
        return SurveyResponseLoadResult(
            response_path=normalized_path,
            exists=False,
            response_data={},
            errors=(),
            warnings=(),
        )

    # ------------------------------------------------------------
    # ディレクトリが指定された場合
    # ------------------------------------------------------------
    if not normalized_path.is_file():
        return SurveyResponseLoadResult(
            response_path=normalized_path,
            exists=True,
            response_data={},
            errors=(
                ResponseLoadIssue(
                    severity="error",
                    message=(
                        "回答パスがファイルではありません．"
                    ),
                    field_name="response_path",
                    file_path=str(
                        normalized_path,
                    ),
                ),
            ),
            warnings=(),
        )

    # ------------------------------------------------------------
    # JSON読込
    # ------------------------------------------------------------
    try:
        raw_text = normalized_path.read_text(
            encoding="utf-8-sig",
        )

    except OSError as exc:
        return SurveyResponseLoadResult(
            response_path=normalized_path,
            exists=True,
            response_data={},
            errors=(
                ResponseLoadIssue(
                    severity="error",
                    message=(
                        "回答ファイルを読み込めませんでした："
                        f"{exc}"
                    ),
                    field_name="response_path",
                    file_path=str(
                        normalized_path,
                    ),
                ),
            ),
            warnings=(),
        )

    # ------------------------------------------------------------
    # 空ファイル
    # ------------------------------------------------------------
    if not raw_text.strip():
        return SurveyResponseLoadResult(
            response_path=normalized_path,
            exists=True,
            response_data={},
            errors=(
                ResponseLoadIssue(
                    severity="error",
                    message=(
                        "回答ファイルが空です．"
                    ),
                    field_name="response_path",
                    file_path=str(
                        normalized_path,
                    ),
                ),
            ),
            warnings=(),
        )

    # ------------------------------------------------------------
    # JSON解析
    # ------------------------------------------------------------
    try:
        loaded_data = json.loads(
            raw_text,
        )

    except json.JSONDecodeError as exc:
        return SurveyResponseLoadResult(
            response_path=normalized_path,
            exists=True,
            response_data={},
            errors=(
                ResponseLoadIssue(
                    severity="error",
                    message=(
                        "回答ファイルのJSON形式が不正です："
                        f"{exc.msg}"
                        f"（{exc.lineno}行"
                        f"{exc.colno}列）"
                    ),
                    field_name="json",
                    file_path=str(
                        normalized_path,
                    ),
                ),
            ),
            warnings=(),
        )

    # ------------------------------------------------------------
    # JSONルート型
    # ------------------------------------------------------------
    if not isinstance(
        loaded_data,
        dict,
    ):
        return SurveyResponseLoadResult(
            response_path=normalized_path,
            exists=True,
            response_data={},
            errors=(
                ResponseLoadIssue(
                    severity="error",
                    message=(
                        "回答JSONの最上位は"
                        "オブジェクトである必要があります．"
                    ),
                    field_name="json",
                    file_path=str(
                        normalized_path,
                    ),
                ),
            ),
            warnings=(),
        )

    # ------------------------------------------------------------
    # 基本構造検証・正規化
    # ------------------------------------------------------------
    (
        normalized_data,
        errors,
        warnings,
    ) = validate_and_normalize_response_data(
        loaded_data,
        response_path=normalized_path,
    )

    return SurveyResponseLoadResult(
        response_path=normalized_path,
        exists=True,
        response_data=normalized_data,
        errors=errors,
        warnings=warnings,
    )


# ============================================================
# public API：回答データの基本検証・正規化
# ============================================================
def validate_and_normalize_response_data(
    response_data: Mapping[str, Any],
    *,
    response_path: Path | None = None,
) -> tuple[
    dict[str, Any],
    tuple[ResponseLoadIssue, ...],
    tuple[ResponseLoadIssue, ...],
]:
    errors: list[ResponseLoadIssue] = []
    warnings: list[ResponseLoadIssue] = []

    file_path = (
        str(response_path)
        if response_path is not None
        else None
    )

    normalized_data = dict(
        response_data,
    )

    # ------------------------------------------------------------
    # 必須フィールド
    # ------------------------------------------------------------
    missing_fields = sorted(
        field_name
        for field_name in RESPONSE_REQUIRED_FIELDS
        if field_name not in normalized_data
    )

    for field_name in missing_fields:
        errors.append(
            ResponseLoadIssue(
                severity="error",
                message=(
                    "回答JSONに必須フィールドが"
                    f"ありません：{field_name}"
                ),
                field_name=field_name,
                file_path=file_path,
            )
        )

    # ------------------------------------------------------------
    # survey_id
    # ------------------------------------------------------------
    if "survey_id" in normalized_data:
        survey_id = normalized_data.get(
            "survey_id",
        )

        if not isinstance(
            survey_id,
            str,
        ):
            errors.append(
                ResponseLoadIssue(
                    severity="error",
                    message=(
                        "survey_idは文字列で"
                        "指定してください．"
                    ),
                    field_name="survey_id",
                    file_path=file_path,
                )
            )

        else:
            normalized_survey_id = survey_id.strip()

            if not normalized_survey_id:
                errors.append(
                    ResponseLoadIssue(
                        severity="error",
                        message=(
                            "survey_idが空です．"
                        ),
                        field_name="survey_id",
                        file_path=file_path,
                    )
                )

            else:
                normalized_data[
                    "survey_id"
                ] = normalized_survey_id

    # ------------------------------------------------------------
    # survey_version
    # ------------------------------------------------------------
    if "survey_version" in normalized_data:
        survey_version = normalized_data.get(
            "survey_version",
        )

        if (
            isinstance(
                survey_version,
                bool,
            )
            or not isinstance(
                survey_version,
                int,
            )
            or survey_version < 1
        ):
            errors.append(
                ResponseLoadIssue(
                    severity="error",
                    message=(
                        "survey_versionは1以上の"
                        "整数で指定してください．"
                    ),
                    field_name="survey_version",
                    file_path=file_path,
                )
            )

    # ------------------------------------------------------------
    # user_sub
    # ------------------------------------------------------------
    if "user_sub" in normalized_data:
        user_sub = normalized_data.get(
            "user_sub",
        )

        if not isinstance(
            user_sub,
            str,
        ):
            errors.append(
                ResponseLoadIssue(
                    severity="error",
                    message=(
                        "user_subは文字列で"
                        "指定してください．"
                    ),
                    field_name="user_sub",
                    file_path=file_path,
                )
            )

        else:
            normalized_user_sub = user_sub.strip()

            if not normalized_user_sub:
                errors.append(
                    ResponseLoadIssue(
                        severity="error",
                        message=(
                            "user_subが空です．"
                        ),
                        field_name="user_sub",
                        file_path=file_path,
                    )
                )

            else:
                normalized_data[
                    "user_sub"
                ] = normalized_user_sub

    # ------------------------------------------------------------
    # answers
    # ------------------------------------------------------------
    if "answers" in normalized_data:
        answers = normalized_data.get(
            "answers",
        )

        if not isinstance(
            answers,
            dict,
        ):
            errors.append(
                ResponseLoadIssue(
                    severity="error",
                    message=(
                        "answersはJSONオブジェクトで"
                        "指定してください．"
                    ),
                    field_name="answers",
                    file_path=file_path,
                )
            )

        else:
            normalized_answers: dict[str, Any] = {}

            for question_id, answer in answers.items():
                if not isinstance(
                    question_id,
                    str,
                ):
                    errors.append(
                        ResponseLoadIssue(
                            severity="error",
                            message=(
                                "answersの質問IDは"
                                "文字列で指定してください．"
                            ),
                            field_name="answers",
                            file_path=file_path,
                        )
                    )
                    continue

                normalized_question_id = (
                    question_id.strip()
                )

                if not normalized_question_id:
                    errors.append(
                        ResponseLoadIssue(
                            severity="error",
                            message=(
                                "answersに空の質問IDが"
                                "含まれています．"
                            ),
                            field_name="answers",
                            file_path=file_path,
                        )
                    )
                    continue

                normalized_answers[
                    normalized_question_id
                ] = answer

            normalized_data[
                "answers"
            ] = normalized_answers

    # ------------------------------------------------------------
    # response_revision
    # ------------------------------------------------------------
    revision = normalized_data.get(
        "response_revision",
        1,
    )

    if (
        isinstance(
            revision,
            bool,
        )
        or not isinstance(
            revision,
            int,
        )
        or revision < 1
    ):
        errors.append(
            ResponseLoadIssue(
                severity="error",
                message=(
                    "response_revisionは1以上の"
                    "整数で指定してください．"
                ),
                field_name="response_revision",
                file_path=file_path,
            )
        )

    else:
        normalized_data[
            "response_revision"
        ] = revision

    # ------------------------------------------------------------
    # response_id
    # ------------------------------------------------------------
    response_id = normalized_data.get(
        "response_id",
    )

    if response_id is not None:
        if not isinstance(
            response_id,
            str,
        ):
            errors.append(
                ResponseLoadIssue(
                    severity="error",
                    message=(
                        "response_idは文字列で"
                        "指定してください．"
                    ),
                    field_name="response_id",
                    file_path=file_path,
                )
            )

        else:
            normalized_response_id = (
                response_id.strip()
            )

            if normalized_response_id:
                normalized_data[
                    "response_id"
                ] = normalized_response_id

            else:
                normalized_data.pop(
                    "response_id",
                    None,
                )

    # ------------------------------------------------------------
    # definition_sha256
    # ------------------------------------------------------------
    definition_sha256 = normalized_data.get(
        "definition_sha256",
    )

    if definition_sha256 is not None:
        if not isinstance(
            definition_sha256,
            str,
        ):
            errors.append(
                ResponseLoadIssue(
                    severity="error",
                    message=(
                        "definition_sha256は文字列で"
                        "指定してください．"
                    ),
                    field_name="definition_sha256",
                    file_path=file_path,
                )
            )

        else:
            normalized_sha256 = (
                definition_sha256.strip().lower()
            )

            if normalized_sha256:
                normalized_data[
                    "definition_sha256"
                ] = normalized_sha256

            else:
                normalized_data.pop(
                    "definition_sha256",
                    None,
                )

    # ------------------------------------------------------------
    # 日時フィールド
    # ------------------------------------------------------------
    for field_name in (
        "submitted_at",
        "updated_at",
    ):
        raw_datetime = normalized_data.get(
            field_name,
        )

        if raw_datetime is None:
            continue

        parsed_datetime = parse_response_datetime(
            raw_datetime,
        )

        if parsed_datetime is None:
            errors.append(
                ResponseLoadIssue(
                    severity="error",
                    message=(
                        f"{field_name}を"
                        "ISO 8601形式として"
                        "解釈できません．"
                    ),
                    field_name=field_name,
                    file_path=file_path,
                )
            )

        else:
            normalized_data[
                field_name
            ] = parsed_datetime.isoformat()

    # ------------------------------------------------------------
    # 未知フィールド
    #
    # 将来互換性のため削除せず，警告だけとする
    # ------------------------------------------------------------
    unknown_fields = sorted(
        set(normalized_data)
        - RESPONSE_KNOWN_FIELDS
    )

    for field_name in unknown_fields:
        warnings.append(
            ResponseLoadIssue(
                severity="warning",
                message=(
                    "回答JSONに未定義のフィールドが"
                    f"含まれています：{field_name}"
                ),
                field_name=field_name,
                file_path=file_path,
            )
        )

    return (
        normalized_data,
        tuple(
            errors,
        ),
        tuple(
            warnings,
        ),
    )


# ============================================================
# public API：回答日時の解析
# ============================================================
def parse_response_datetime(
    value: Any,
) -> datetime | None:
    if value is None:
        return None

    if isinstance(
        value,
        datetime,
    ):
        parsed = value

    elif isinstance(
        value,
        str,
    ):
        normalized_text = value.strip()

        if not normalized_text:
            return None

        if normalized_text.endswith(
            "Z",
        ):
            normalized_text = (
                normalized_text[:-1]
                + "+00:00"
            )

        try:
            parsed = datetime.fromisoformat(
                normalized_text,
            )

        except ValueError:
            return None

    else:
        return None

    # ------------------------------------------------------------
    # timezone未設定の場合はUTCとして扱う
    # ------------------------------------------------------------
    if parsed.tzinfo is None:
        return parsed.replace(
            tzinfo=UTC,
        )

    return parsed.astimezone(
        UTC,
    )


# ============================================================
# パス構成要素の正規化
# ============================================================
def normalize_path_component(
    value: str,
    *,
    field_name: str,
) -> str:
    normalized = str(
        value or "",
    ).strip()

    if not normalized:
        raise ValueError(
            f"{field_name}が空です．"
        )

    # ------------------------------------------------------------
    # ディレクトリトラバーサル防止
    # ------------------------------------------------------------
    if normalized in {
        ".",
        "..",
    }:
        raise ValueError(
            (
                f"{field_name}に使用できない"
                "値が指定されています．"
            )
        )

    forbidden_characters = {
        "/",
        "\\",
        "\x00",
    }

    if any(
        character in normalized
        for character in forbidden_characters
    ):
        raise ValueError(
            (
                f"{field_name}にパス区切り文字を"
                "含めることはできません．"
            )
        )

    return normalized

# ============================================================
# 履歴回答情報
# ============================================================
@dataclass(frozen=True)
class HistoryResponseInfo:
    # ------------------------------------------------------------
    # 履歴ファイル
    # ------------------------------------------------------------
    history_path: Path

    # ------------------------------------------------------------
    # 回答識別情報
    # ------------------------------------------------------------
    survey_id: str
    user_sub: str

    # ------------------------------------------------------------
    # 回答情報
    # ------------------------------------------------------------
    survey_version: int | None
    response_revision: int
    response_id: str | None

    # ------------------------------------------------------------
    # 保存日時
    # ------------------------------------------------------------
    submitted_at: datetime | None
    updated_at: datetime | None
    history_created_at: datetime | None

    # ------------------------------------------------------------
    # ファイル状態
    # ------------------------------------------------------------
    is_valid: bool
    errors: tuple[ResponseLoadIssue, ...] = ()
    warnings: tuple[ResponseLoadIssue, ...] = ()

    @property
    def file_name(self) -> str:
        return self.history_path.name

    @property
    def effective_datetime(self) -> datetime | None:
        # --------------------------------------------------------
        # 履歴の並び順に使用する代表日時
        #
        # 優先順位：
        # 1. history_created_at
        # 2. updated_at
        # 3. submitted_at
        # --------------------------------------------------------
        if self.history_created_at is not None:
            return self.history_created_at

        if self.updated_at is not None:
            return self.updated_at

        return self.submitted_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "history_path": str(
                self.history_path,
            ),
            "file_name": self.file_name,
            "survey_id": self.survey_id,
            "user_sub": self.user_sub,
            "survey_version": self.survey_version,
            "response_revision": (
                self.response_revision
            ),
            "response_id": self.response_id,
            "submitted_at": (
                self.submitted_at.isoformat()
                if self.submitted_at is not None
                else None
            ),
            "updated_at": (
                self.updated_at.isoformat()
                if self.updated_at is not None
                else None
            ),
            "history_created_at": (
                self.history_created_at.isoformat()
                if self.history_created_at is not None
                else None
            ),
            "effective_datetime": (
                self.effective_datetime.isoformat()
                if self.effective_datetime is not None
                else None
            ),
            "is_valid": self.is_valid,
            "errors": [
                issue.to_dict()
                for issue in self.errors
            ],
            "warnings": [
                issue.to_dict()
                for issue in self.warnings
            ],
        }


# ============================================================
# 履歴回答一覧読込結果
# ============================================================
@dataclass(frozen=True)
class SurveyResponseHistoryResult:
    # ------------------------------------------------------------
    # 履歴ディレクトリ
    # ------------------------------------------------------------
    history_directory: Path

    # ------------------------------------------------------------
    # 履歴回答一覧
    # ------------------------------------------------------------
    histories: tuple[HistoryResponseInfo, ...]

    # ------------------------------------------------------------
    # 一覧取得処理自体のエラー・警告
    # ------------------------------------------------------------
    errors: tuple[ResponseLoadIssue, ...] = ()
    warnings: tuple[ResponseLoadIssue, ...] = ()

    @property
    def exists(self) -> bool:
        return self.history_directory.exists()

    @property
    def is_valid(self) -> bool:
        return not self.errors

    @property
    def count(self) -> int:
        return len(
            self.histories,
        )

    @property
    def valid_histories(
        self,
    ) -> tuple[HistoryResponseInfo, ...]:
        return tuple(
            history
            for history in self.histories
            if history.is_valid
        )

    @property
    def invalid_histories(
        self,
    ) -> tuple[HistoryResponseInfo, ...]:
        return tuple(
            history
            for history in self.histories
            if not history.is_valid
        )

    @property
    def latest_history(
        self,
    ) -> HistoryResponseInfo | None:
        if not self.histories:
            return None

        return self.histories[0]

    def to_dict(self) -> dict[str, Any]:
        return {
            "history_directory": str(
                self.history_directory,
            ),
            "exists": self.exists,
            "is_valid": self.is_valid,
            "count": self.count,
            "valid_count": len(
                self.valid_histories,
            ),
            "invalid_count": len(
                self.invalid_histories,
            ),
            "histories": [
                history.to_dict()
                for history in self.histories
            ],
            "errors": [
                issue.to_dict()
                for issue in self.errors
            ],
            "warnings": [
                issue.to_dict()
                for issue in self.warnings
            ],
        }


# ============================================================
# public API：履歴ディレクトリの生成
# ============================================================
def build_response_history_directory(
    *,
    history_root: Path,
    survey_id: str,
    user_sub: str,
) -> Path:
    normalized_survey_id = normalize_path_component(
        survey_id,
        field_name="survey_id",
    )

    normalized_user_sub = normalize_path_component(
        user_sub,
        field_name="user_sub",
    )

    return (
        Path(history_root)
        / normalized_survey_id
        / normalized_user_sub
    )


# ============================================================
# public API：履歴回答一覧の取得
# ============================================================
def load_response_history(
    *,
    history_root: Path,
    survey_id: str,
    user_sub: str,
    include_invalid: bool = True,
) -> SurveyResponseHistoryResult:
    # ------------------------------------------------------------
    # 履歴ディレクトリ
    # ------------------------------------------------------------
    history_directory = (
        build_response_history_directory(
            history_root=history_root,
            survey_id=survey_id,
            user_sub=user_sub,
        )
    )

    # ------------------------------------------------------------
    # 履歴ディレクトリが存在しない場合
    #
    # 履歴がないことはエラーにしない
    # ------------------------------------------------------------
    if not history_directory.exists():
        return SurveyResponseHistoryResult(
            history_directory=(
                history_directory
            ),
            histories=(),
            errors=(),
            warnings=(),
        )

    # ------------------------------------------------------------
    # ディレクトリでない場合
    # ------------------------------------------------------------
    if not history_directory.is_dir():
        return SurveyResponseHistoryResult(
            history_directory=(
                history_directory
            ),
            histories=(),
            errors=(
                ResponseLoadIssue(
                    severity="error",
                    message=(
                        "回答履歴の保存先が"
                        "ディレクトリではありません．"
                    ),
                    field_name=(
                        "history_directory"
                    ),
                    file_path=str(
                        history_directory,
                    ),
                ),
            ),
            warnings=(),
        )

    histories: list[HistoryResponseInfo] = []
    errors: list[ResponseLoadIssue] = []
    warnings: list[ResponseLoadIssue] = []

    # ------------------------------------------------------------
    # JSONファイル一覧
    # ------------------------------------------------------------
    try:
        history_paths = sorted(
            (
                path
                for path in history_directory.iterdir()
                if path.is_file()
                and path.suffix.lower() == ".json"
            ),
            key=lambda path: path.name,
            reverse=True,
        )

    except OSError as exc:
        return SurveyResponseHistoryResult(
            history_directory=(
                history_directory
            ),
            histories=(),
            errors=(
                ResponseLoadIssue(
                    severity="error",
                    message=(
                        "回答履歴ディレクトリを"
                        "読み込めませんでした："
                        f"{exc}"
                    ),
                    field_name=(
                        "history_directory"
                    ),
                    file_path=str(
                        history_directory,
                    ),
                ),
            ),
            warnings=(),
        )

    # ------------------------------------------------------------
    # 履歴ファイルごとの読込
    # ------------------------------------------------------------
    for history_path in history_paths:
        load_result = load_response_file(
            history_path,
        )

        history_info = (
            build_history_response_info(
                history_path=history_path,
                load_result=load_result,
                expected_survey_id=survey_id,
                expected_user_sub=user_sub,
            )
        )

        if (
            include_invalid
            or history_info.is_valid
        ):
            histories.append(
                history_info,
            )

    # ------------------------------------------------------------
    # 最新順へ並べ替え
    #
    # 日時を取得できない履歴は末尾へ置く
    # ------------------------------------------------------------
    histories.sort(
        key=build_history_sort_key,
        reverse=True,
    )

    # ------------------------------------------------------------
    # JSON以外のファイル
    #
    # 将来，補助ファイルを置く可能性があるため，
    # 警告にはしない
    # ------------------------------------------------------------

    return SurveyResponseHistoryResult(
        history_directory=history_directory,
        histories=tuple(
            histories,
        ),
        errors=tuple(
            errors,
        ),
        warnings=tuple(
            warnings,
        ),
    )


# ============================================================
# public API：最新履歴回答の読込
# ============================================================
def load_latest_history_response(
    *,
    history_root: Path,
    survey_id: str,
    user_sub: str,
) -> SurveyResponseLoadResult:
    # ------------------------------------------------------------
    # 履歴一覧取得
    #
    # 破損ファイルを除外し，
    # 正常に読み込める最新履歴を使用する
    # ------------------------------------------------------------
    history_result = load_response_history(
        history_root=history_root,
        survey_id=survey_id,
        user_sub=user_sub,
        include_invalid=False,
    )

    # ------------------------------------------------------------
    # 履歴一覧取得エラー
    # ------------------------------------------------------------
    if not history_result.is_valid:
        return SurveyResponseLoadResult(
            response_path=(
                history_result.history_directory
            ),
            exists=(
                history_result.history_directory.exists()
            ),
            response_data={},
            errors=history_result.errors,
            warnings=history_result.warnings,
        )

    # ------------------------------------------------------------
    # 履歴なし
    # ------------------------------------------------------------
    latest_history = (
        history_result.latest_history
    )

    if latest_history is None:
        return SurveyResponseLoadResult(
            response_path=(
                history_result.history_directory
            ),
            exists=False,
            response_data={},
            errors=(),
            warnings=(
                history_result.warnings
            ),
        )

    # ------------------------------------------------------------
    # 最新履歴の回答JSONを再読込
    # ------------------------------------------------------------
    return load_response_file(
        latest_history.history_path,
    )


# ============================================================
# public API：指定履歴回答の読込
# ============================================================
def load_history_response(
    *,
    history_root: Path,
    survey_id: str,
    user_sub: str,
    history_file_name: str,
) -> SurveyResponseLoadResult:
    history_directory = (
        build_response_history_directory(
            history_root=history_root,
            survey_id=survey_id,
            user_sub=user_sub,
        )
    )

    normalized_file_name = (
        normalize_history_file_name(
            history_file_name,
        )
    )

    history_path = (
        history_directory
        / normalized_file_name
    )

    # ------------------------------------------------------------
    # resolveによるディレクトリ外参照防止
    # ------------------------------------------------------------
    try:
        resolved_directory = (
            history_directory.resolve(
                strict=False,
            )
        )

        resolved_history_path = (
            history_path.resolve(
                strict=False,
            )
        )

        resolved_history_path.relative_to(
            resolved_directory,
        )

    except (
        OSError,
        ValueError,
    ):
        return SurveyResponseLoadResult(
            response_path=history_path,
            exists=False,
            response_data={},
            errors=(
                ResponseLoadIssue(
                    severity="error",
                    message=(
                        "回答履歴ディレクトリ外の"
                        "ファイルは読み込めません．"
                    ),
                    field_name=(
                        "history_file_name"
                    ),
                    file_path=str(
                        history_path,
                    ),
                ),
            ),
            warnings=(),
        )

    result = load_response_file(
        history_path,
    )

    if not result.was_loaded:
        return result

    errors = list(
        result.errors,
    )

    warnings = list(
        result.warnings,
    )

    response_data = dict(
        result.response_data,
    )

    # ------------------------------------------------------------
    # survey_id整合性
    # ------------------------------------------------------------
    if (
        response_data.get(
            "survey_id"
        )
        != survey_id
    ):
        errors.append(
            ResponseLoadIssue(
                severity="error",
                message=(
                    "履歴回答のsurvey_idが"
                    "指定されたアンケートIDと"
                    "一致しません．"
                ),
                field_name="survey_id",
                file_path=str(
                    history_path,
                ),
            )
        )

    # ------------------------------------------------------------
    # user_sub整合性
    # ------------------------------------------------------------
    if (
        response_data.get(
            "user_sub"
        )
        != user_sub
    ):
        errors.append(
            ResponseLoadIssue(
                severity="error",
                message=(
                    "履歴回答のuser_subが"
                    "指定されたユーザーIDと"
                    "一致しません．"
                ),
                field_name="user_sub",
                file_path=str(
                    history_path,
                ),
            )
        )

    return SurveyResponseLoadResult(
        response_path=history_path,
        exists=True,
        response_data=response_data,
        errors=tuple(
            errors,
        ),
        warnings=tuple(
            warnings,
        ),
    )


# ============================================================
# 履歴情報の生成
# ============================================================
def build_history_response_info(
    *,
    history_path: Path,
    load_result: SurveyResponseLoadResult,
    expected_survey_id: str,
    expected_user_sub: str,
) -> HistoryResponseInfo:
    errors = list(
        load_result.errors,
    )

    warnings = list(
        load_result.warnings,
    )

    response_data = dict(
        load_result.response_data,
    )

    # ------------------------------------------------------------
    # survey_id
    # ------------------------------------------------------------
    loaded_survey_id = str(
        response_data.get(
            "survey_id",
            "",
        )
        or ""
    ).strip()

    if (
        loaded_survey_id
        and loaded_survey_id
        != expected_survey_id
    ):
        errors.append(
            ResponseLoadIssue(
                severity="error",
                message=(
                    "履歴回答のsurvey_idが"
                    "保存先ディレクトリと一致しません．"
                ),
                field_name="survey_id",
                file_path=str(
                    history_path,
                ),
            )
        )

    # ------------------------------------------------------------
    # user_sub
    # ------------------------------------------------------------
    loaded_user_sub = str(
        response_data.get(
            "user_sub",
            "",
        )
        or ""
    ).strip()

    if (
        loaded_user_sub
        and loaded_user_sub
        != expected_user_sub
    ):
        errors.append(
            ResponseLoadIssue(
                severity="error",
                message=(
                    "履歴回答のuser_subが"
                    "保存先ディレクトリと一致しません．"
                ),
                field_name="user_sub",
                file_path=str(
                    history_path,
                ),
            )
        )

    # ------------------------------------------------------------
    # survey_version
    # ------------------------------------------------------------
    raw_survey_version = response_data.get(
        "survey_version",
    )

    if (
        isinstance(
            raw_survey_version,
            int,
        )
        and not isinstance(
            raw_survey_version,
            bool,
        )
    ):
        survey_version = raw_survey_version

    else:
        survey_version = None

    # ------------------------------------------------------------
    # response_revision
    # ------------------------------------------------------------
    raw_revision = response_data.get(
        "response_revision",
        0,
    )

    if (
        isinstance(
            raw_revision,
            int,
        )
        and not isinstance(
            raw_revision,
            bool,
        )
    ):
        response_revision = max(
            raw_revision,
            0,
        )

    else:
        response_revision = 0

    # ------------------------------------------------------------
    # response_id
    # ------------------------------------------------------------
    raw_response_id = response_data.get(
        "response_id",
    )

    if isinstance(
        raw_response_id,
        str,
    ):
        response_id = (
            raw_response_id.strip()
            or None
        )

    else:
        response_id = None

    return HistoryResponseInfo(
        history_path=history_path,
        survey_id=(
            loaded_survey_id
            or expected_survey_id
        ),
        user_sub=(
            loaded_user_sub
            or expected_user_sub
        ),
        survey_version=survey_version,
        response_revision=(
            response_revision
        ),
        response_id=response_id,
        submitted_at=(
            parse_response_datetime(
                response_data.get(
                    "submitted_at",
                )
            )
        ),
        updated_at=(
            parse_response_datetime(
                response_data.get(
                    "updated_at",
                )
            )
        ),
        history_created_at=(
            parse_history_datetime_from_name(
                history_path.name,
            )
        ),
        is_valid=not errors,
        errors=tuple(
            errors,
        ),
        warnings=tuple(
            warnings,
        ),
    )


# ============================================================
# 履歴ファイル名からUTC日時を取得
# ============================================================
def parse_history_datetime_from_name(
    file_name: str,
) -> datetime | None:
    # ------------------------------------------------------------
    # 想定形式
    #
    # 20260728T012345123456Z.json
    # 20260728T012345Z.json
    # 2026-07-28T01-23-45.123456Z.json
    # ------------------------------------------------------------
    stem = Path(
        file_name,
    ).stem.strip()

    datetime_formats = (
        "%Y%m%dT%H%M%S%fZ",
        "%Y%m%dT%H%M%SZ",
        "%Y-%m-%dT%H-%M-%S.%fZ",
        "%Y-%m-%dT%H-%M-%SZ",
    )

    for datetime_format in datetime_formats:
        try:
            parsed = datetime.strptime(
                stem,
                datetime_format,
            )

        except ValueError:
            continue

        return parsed.replace(
            tzinfo=UTC,
        )

    return None


# ============================================================
# 履歴の並び替えキー
# ============================================================
def build_history_sort_key(
    history: HistoryResponseInfo,
) -> tuple[
    datetime,
    int,
    str,
]:
    effective_datetime = (
        history.effective_datetime
    )

    if effective_datetime is None:
        effective_datetime = datetime.min.replace(
            tzinfo=UTC,
        )

    return (
        effective_datetime,
        history.response_revision,
        history.file_name,
    )


# ============================================================
# 履歴ファイル名の正規化
# ============================================================
def normalize_history_file_name(
    value: str,
) -> str:
    normalized = str(
        value or "",
    ).strip()

    if not normalized:
        raise ValueError(
            "history_file_nameが空です．"
        )

    # ------------------------------------------------------------
    # ファイル名だけを許可
    # ------------------------------------------------------------
    if Path(normalized).name != normalized:
        raise ValueError(
            (
                "history_file_nameには"
                "ファイル名だけを指定してください．"
            )
        )

    if normalized in {
        ".",
        "..",
    }:
        raise ValueError(
            (
                "history_file_nameに"
                "使用できない値です．"
            )
        )

    if not normalized.lower().endswith(
        ".json",
    ):
        raise ValueError(
            (
                "回答履歴ファイルは"
                "JSON形式で指定してください．"
            )
        )

    if "\x00" in normalized:
        raise ValueError(
            (
                "history_file_nameに"
                "NULL文字を含めることはできません．"
            )
        )

    return normalized

# ============================================================
# 空回答生成結果
# ============================================================
@dataclass(frozen=True)
class EmptySurveyResponse:
    # ------------------------------------------------------------
    # 回答識別情報
    # ------------------------------------------------------------
    survey_id: str
    survey_version: int
    user_sub: str
    response_id: str
    response_revision: int

    # ------------------------------------------------------------
    # アンケート定義情報
    # ------------------------------------------------------------
    definition_sha256: str | None

    # ------------------------------------------------------------
    # 回答
    # ------------------------------------------------------------
    answers: dict[str, Any]

    # ------------------------------------------------------------
    # 日時
    # ------------------------------------------------------------
    submitted_at: datetime | None
    updated_at: datetime

    @property
    def is_submitted(self) -> bool:
        return self.submitted_at is not None

    @property
    def answer_count(self) -> int:
        return len(
            self.answers,
        )

    @property
    def answered_question_count(self) -> int:
        return sum(
            1
            for answer in self.answers.values()
            if not is_empty_initial_answer(
                answer,
            )
        )

    def to_response_data(self) -> dict[str, Any]:
        return {
            "survey_id": self.survey_id,
            "survey_version": (
                self.survey_version
            ),
            "user_sub": self.user_sub,
            "response_id": self.response_id,
            "response_revision": (
                self.response_revision
            ),
            "definition_sha256": (
                self.definition_sha256
            ),
            "answers": dict(
                self.answers,
            ),
            "submitted_at": (
                self.submitted_at.isoformat()
                if self.submitted_at is not None
                else None
            ),
            "updated_at": (
                self.updated_at.isoformat()
            ),
        }

    def to_dict(self) -> dict[str, Any]:
        response_data = (
            self.to_response_data()
        )

        response_data.update(
            {
                "is_submitted": (
                    self.is_submitted
                ),
                "answer_count": (
                    self.answer_count
                ),
                "answered_question_count": (
                    self.answered_question_count
                ),
            }
        )

        return response_data


# ============================================================
# public API：空回答の生成
# ============================================================
def create_empty_response(
    *,
    survey_definition: Any,
    survey_id: str | None = None,
    survey_version: int | None = None,
    user_sub: str,
    definition_sha256: str | None = None,
    response_id: str | None = None,
    response_revision: int = 1,
    now: datetime | None = None,
    include_default_answers: bool = True,
) -> EmptySurveyResponse:
    # ------------------------------------------------------------
    # ユーザーID
    # ------------------------------------------------------------
    normalized_user_sub = (
        normalize_path_component(
            user_sub,
            field_name="user_sub",
        )
    )

    # ------------------------------------------------------------
    # アンケートID
    #
    # 引数が未指定の場合は定義から取得する
    # ------------------------------------------------------------
    resolved_survey_id = (
        resolve_survey_id(
            survey_definition=(
                survey_definition
            ),
            explicit_survey_id=survey_id,
        )
    )

    # ------------------------------------------------------------
    # アンケートバージョン
    #
    # 引数が未指定の場合は定義から取得する
    # ------------------------------------------------------------
    resolved_survey_version = (
        resolve_survey_version(
            survey_definition=(
                survey_definition
            ),
            explicit_survey_version=(
                survey_version
            ),
        )
    )

    # ------------------------------------------------------------
    # 回答リビジョン
    # ------------------------------------------------------------
    normalized_revision = (
        normalize_response_revision(
            response_revision,
        )
    )

    # ------------------------------------------------------------
    # 回答ID
    # ------------------------------------------------------------
    normalized_response_id = (
        normalize_or_build_response_id(
            response_id=response_id,
            survey_id=resolved_survey_id,
            user_sub=normalized_user_sub,
        )
    )

    # ------------------------------------------------------------
    # 定義ハッシュ
    # ------------------------------------------------------------
    normalized_definition_sha256 = (
        normalize_definition_sha256(
            definition_sha256,
        )
    )

    # ------------------------------------------------------------
    # 更新日時
    # ------------------------------------------------------------
    updated_at = normalize_utc_datetime(
        now,
    )

    # ------------------------------------------------------------
    # 初期回答
    #
    # build_empty_answers()は次の第2-2-2回で追加する
    # ------------------------------------------------------------
    if include_default_answers:
        answers = build_empty_answers(
            survey_definition=(
                survey_definition
            ),
        )

    else:
        answers = {}

    return EmptySurveyResponse(
        survey_id=resolved_survey_id,
        survey_version=(
            resolved_survey_version
        ),
        user_sub=normalized_user_sub,
        response_id=(
            normalized_response_id
        ),
        response_revision=(
            normalized_revision
        ),
        definition_sha256=(
            normalized_definition_sha256
        ),
        answers=answers,
        submitted_at=None,
        updated_at=updated_at,
    )


# ============================================================
# public API：回答IDの生成
# ============================================================
def build_response_id(
    *,
    survey_id: str,
    user_sub: str,
) -> str:
    normalized_survey_id = (
        normalize_path_component(
            survey_id,
            field_name="survey_id",
        )
    )

    normalized_user_sub = (
        normalize_path_component(
            user_sub,
            field_name="user_sub",
        )
    )

    # ------------------------------------------------------------
    # response_id
    #
    # survey_id・user_subは識別しやすさのため含める．
    # 一意性はUUID4で確保する．
    # ------------------------------------------------------------
    unique_part = uuid4().hex

    return (
        f"{normalized_survey_id}"
        f"__{normalized_user_sub}"
        f"__{unique_part}"
    )


# ============================================================
# 回答IDの正規化または生成
# ============================================================
def normalize_or_build_response_id(
    *,
    response_id: str | None,
    survey_id: str,
    user_sub: str,
) -> str:
    if response_id is None:
        return build_response_id(
            survey_id=survey_id,
            user_sub=user_sub,
        )

    normalized = str(
        response_id,
    ).strip()

    if not normalized:
        return build_response_id(
            survey_id=survey_id,
            user_sub=user_sub,
        )

    # ------------------------------------------------------------
    # JSON保存値として不適切な制御文字を禁止
    # ------------------------------------------------------------
    if any(
        ord(character) < 32
        for character in normalized
    ):
        raise ValueError(
            (
                "response_idに制御文字を"
                "含めることはできません．"
            )
        )

    if len(normalized) > 255:
        raise ValueError(
            (
                "response_idは255文字以内で"
                "指定してください．"
            )
        )

    return normalized


# ============================================================
# アンケートIDの解決
# ============================================================
def resolve_survey_id(
    *,
    survey_definition: Any,
    explicit_survey_id: str | None,
) -> str:
    # ------------------------------------------------------------
    # 明示指定を優先する
    # ------------------------------------------------------------
    if explicit_survey_id is not None:
        return normalize_path_component(
            explicit_survey_id,
            field_name="survey_id",
        )

    # ------------------------------------------------------------
    # 定義から取得する
    # ------------------------------------------------------------
    definition_survey_id = (
        get_definition_value(
            survey_definition,
            field_names=(
                "survey_id",
                "id",
            ),
        )
    )

    if definition_survey_id is None:
        raise ValueError(
            (
                "survey_idが指定されておらず，"
                "アンケート定義からも取得できません．"
            )
        )

    return normalize_path_component(
        str(
            definition_survey_id,
        ),
        field_name="survey_id",
    )


# ============================================================
# アンケートバージョンの解決
# ============================================================
def resolve_survey_version(
    *,
    survey_definition: Any,
    explicit_survey_version: int | None,
) -> int:
    # ------------------------------------------------------------
    # 明示指定を優先する
    # ------------------------------------------------------------
    if explicit_survey_version is not None:
        return normalize_survey_version(
            explicit_survey_version,
        )

    # ------------------------------------------------------------
    # 定義から取得する
    # ------------------------------------------------------------
    definition_version = (
        get_definition_value(
            survey_definition,
            field_names=(
                "survey_version",
                "version",
            ),
        )
    )

    if definition_version is None:
        raise ValueError(
            (
                "survey_versionが指定されておらず，"
                "アンケート定義からも取得できません．"
            )
        )

    return normalize_survey_version(
        definition_version,
    )


# ============================================================
# アンケートバージョンの正規化
# ============================================================
def normalize_survey_version(
    value: Any,
) -> int:
    if isinstance(
        value,
        bool,
    ):
        raise ValueError(
            (
                "survey_versionは1以上の"
                "整数で指定してください．"
            )
        )

    if isinstance(
        value,
        int,
    ):
        normalized = value

    elif isinstance(
        value,
        str,
    ):
        stripped = value.strip()

        if not stripped:
            raise ValueError(
                "survey_versionが空です．"
            )

        try:
            normalized = int(
                stripped,
            )

        except ValueError as exc:
            raise ValueError(
                (
                    "survey_versionは1以上の"
                    "整数で指定してください．"
                )
            ) from exc

    else:
        raise TypeError(
            (
                "survey_versionは整数または"
                "整数形式の文字列で"
                "指定してください．"
            )
        )

    if normalized < 1:
        raise ValueError(
            (
                "survey_versionは1以上の"
                "整数で指定してください．"
            )
        )

    return normalized


# ============================================================
# 回答リビジョンの正規化
# ============================================================
def normalize_response_revision(
    value: Any,
) -> int:
    if isinstance(
        value,
        bool,
    ):
        raise ValueError(
            (
                "response_revisionは1以上の"
                "整数で指定してください．"
            )
        )

    if isinstance(
        value,
        int,
    ):
        normalized = value

    elif isinstance(
        value,
        str,
    ):
        stripped = value.strip()

        if not stripped:
            raise ValueError(
                "response_revisionが空です．"
            )

        try:
            normalized = int(
                stripped,
            )

        except ValueError as exc:
            raise ValueError(
                (
                    "response_revisionは1以上の"
                    "整数で指定してください．"
                )
            ) from exc

    else:
        raise TypeError(
            (
                "response_revisionは整数または"
                "整数形式の文字列で"
                "指定してください．"
            )
        )

    if normalized < 1:
        raise ValueError(
            (
                "response_revisionは1以上の"
                "整数で指定してください．"
            )
        )

    return normalized


# ============================================================
# 定義ハッシュの正規化
# ============================================================
def normalize_definition_sha256(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized = str(
        value,
    ).strip().lower()

    if not normalized:
        return None

    # ------------------------------------------------------------
    # SHA256は64桁の16進文字列
    # ------------------------------------------------------------
    if len(normalized) != 64:
        raise ValueError(
            (
                "definition_sha256は"
                "64文字の16進文字列で"
                "指定してください．"
            )
        )

    valid_characters = set(
        "0123456789abcdef",
    )

    if any(
        character not in valid_characters
        for character in normalized
    ):
        raise ValueError(
            (
                "definition_sha256に"
                "16進数以外の文字が"
                "含まれています．"
            )
        )

    return normalized


# ============================================================
# UTC日時の正規化
# ============================================================
def normalize_utc_datetime(
    value: datetime | None,
) -> datetime:
    # ------------------------------------------------------------
    # 未指定の場合は現在UTC日時
    # ------------------------------------------------------------
    if value is None:
        return datetime.now(
            UTC,
        )

    if not isinstance(
        value,
        datetime,
    ):
        raise TypeError(
            "nowはdatetime型で指定してください．"
        )

    # ------------------------------------------------------------
    # timezone未設定はUTCとして扱う
    # ------------------------------------------------------------
    if value.tzinfo is None:
        return value.replace(
            tzinfo=UTC,
        )

    return value.astimezone(
        UTC,
    )


# ============================================================
# 定義オブジェクトから値を取得
# ============================================================
def get_definition_value(
    survey_definition: Any,
    *,
    field_names: tuple[str, ...],
) -> Any:
    if survey_definition is None:
        return None

    # ------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------
    if isinstance(
        survey_definition,
        Mapping,
    ):
        for field_name in field_names:
            if field_name in survey_definition:
                return survey_definition.get(
                    field_name,
                )

        return None

    # ------------------------------------------------------------
    # dataclass・通常クラス
    # ------------------------------------------------------------
    for field_name in field_names:
        if hasattr(
            survey_definition,
            field_name,
        ):
            return getattr(
                survey_definition,
                field_name,
            )

    return None


# ============================================================
# 初期回答が空か判定
# ============================================================
def is_empty_initial_answer(
    value: Any,
) -> bool:
    if value is None:
        return True

    if isinstance(
        value,
        str,
    ):
        return not value.strip()

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
            dict,
        ),
    ):
        return len(
            value,
        ) == 0

    return False

# ============================================================
# public API：質問ごとの初期回答生成
# ============================================================
def build_empty_answers(
    *,
    survey_definition: Any,
) -> dict[str, Any]:
    # ------------------------------------------------------------
    # アンケート定義から質問一覧を取得する
    # ------------------------------------------------------------
    questions = extract_questions(
        survey_definition,
    )

    answers: dict[str, Any] = {}

    # ------------------------------------------------------------
    # 質問ごとの初期回答を生成する
    #
    # 質問IDが取得できない質問は，
    # 定義不正として例外にする
    # ------------------------------------------------------------
    for question_index, question in enumerate(
        questions,
        start=1,
    ):
        question_id = extract_question_id(
            question,
        )

        if question_id is None:
            raise ValueError(
                (
                    "アンケート定義の質問に"
                    "idが設定されていません："
                    f"{question_index}問目"
                )
            )

        if question_id in answers:
            raise ValueError(
                (
                    "アンケート定義に重複した"
                    "質問IDがあります："
                    f"{question_id}"
                )
            )

        question_type = extract_question_type(
            question,
        )

        # --------------------------------------------------------
        # 質問の初期値
        #
        # get_question_default_value()は
        # 次の第2-2-2-2回で追加する
        # --------------------------------------------------------
        default_value = (
            get_question_default_value(
                question=question,
                question_type=question_type,
            )
        )

        finalized_default_value = (
            finalize_question_default_value(
                question=question,
                question_type=question_type,
                value=default_value,
            )
        )

        answers[
            question_id
        ] = finalized_default_value

    validate_empty_answers(
        survey_definition=survey_definition,
        answers=answers,
    )

    return clone_empty_answers(
        answers,
    )


# ============================================================
# public API：質問一覧の取得
# ============================================================
def extract_questions(
    survey_definition: Any,
) -> tuple[Any, ...]:
    if survey_definition is None:
        raise ValueError(
            "survey_definitionが未指定です．"
        )

    # ------------------------------------------------------------
    # アンケート定義自体が質問一覧の場合
    # ------------------------------------------------------------
    if isinstance(
        survey_definition,
        (
            list,
            tuple,
        ),
    ):
        return normalize_questions_sequence(
            survey_definition,
        )

    # ------------------------------------------------------------
    # Mapping形式
    #
    # 想定例：
    # {
    #     "id": "survey_001",
    #     "version": 1,
    #     "questions": [...]
    # }
    # ------------------------------------------------------------
    if isinstance(
        survey_definition,
        Mapping,
    ):
        raw_questions = survey_definition.get(
            "questions",
        )

        if raw_questions is None:
            raise ValueError(
                (
                    "アンケート定義に"
                    "questionsがありません．"
                )
            )

        return normalize_questions_sequence(
            raw_questions,
        )

    # ------------------------------------------------------------
    # dataclass・通常クラス
    # ------------------------------------------------------------
    if hasattr(
        survey_definition,
        "questions",
    ):
        raw_questions = getattr(
            survey_definition,
            "questions",
        )

        return normalize_questions_sequence(
            raw_questions,
        )

    raise TypeError(
        (
            "survey_definitionから"
            "質問一覧を取得できません．"
        )
    )


# ============================================================
# 質問一覧の正規化
# ============================================================
def normalize_questions_sequence(
    raw_questions: Any,
) -> tuple[Any, ...]:
    if raw_questions is None:
        return ()

    # ------------------------------------------------------------
    # 文字列はSequenceとして扱わない
    # ------------------------------------------------------------
    if isinstance(
        raw_questions,
        (
            str,
            bytes,
            bytearray,
        ),
    ):
        raise TypeError(
            (
                "questionsは質問オブジェクトの"
                "配列で指定してください．"
            )
        )

    if not isinstance(
        raw_questions,
        (
            list,
            tuple,
        ),
    ):
        raise TypeError(
            (
                "questionsはlistまたはtupleで"
                "指定してください．"
            )
        )

    normalized_questions: list[Any] = []

    for question_index, question in enumerate(
        raw_questions,
        start=1,
    ):
        if question is None:
            raise ValueError(
                (
                    "questionsにNoneが"
                    "含まれています："
                    f"{question_index}問目"
                )
            )

        if not is_supported_question_object(
            question,
        ):
            raise TypeError(
                (
                    "質問はMapping，dataclass，"
                    "または属性を持つオブジェクトで"
                    "指定してください："
                    f"{question_index}問目"
                )
            )

        normalized_questions.append(
            question,
        )

    return tuple(
        normalized_questions,
    )


# ============================================================
# 質問オブジェクトの対応判定
# ============================================================
def is_supported_question_object(
    question: Any,
) -> bool:
    if isinstance(
        question,
        Mapping,
    ):
        return True

    if hasattr(
        question,
        "__dict__",
    ):
        return True

    # ------------------------------------------------------------
    # slotsを使用するdataclassなどへの対応
    # ------------------------------------------------------------
    if (
        hasattr(
            question,
            "id",
        )
        or hasattr(
            question,
            "question_id",
        )
    ):
        return True

    return False


# ============================================================
# public API：質問ID一覧の取得
# ============================================================
def extract_question_ids(
    survey_definition: Any,
) -> tuple[str, ...]:
    questions = extract_questions(
        survey_definition,
    )

    question_ids: list[str] = []
    seen_question_ids: set[str] = set()

    for question_index, question in enumerate(
        questions,
        start=1,
    ):
        question_id = extract_question_id(
            question,
        )

        if question_id is None:
            raise ValueError(
                (
                    "アンケート定義の質問に"
                    "idが設定されていません："
                    f"{question_index}問目"
                )
            )

        if question_id in seen_question_ids:
            raise ValueError(
                (
                    "アンケート定義に重複した"
                    "質問IDがあります："
                    f"{question_id}"
                )
            )

        seen_question_ids.add(
            question_id,
        )

        question_ids.append(
            question_id,
        )

    return tuple(
        question_ids,
    )


# ============================================================
# public API：質問IDと質問オブジェクトの対応表
# ============================================================
def build_question_map(
    survey_definition: Any,
) -> dict[str, Any]:
    questions = extract_questions(
        survey_definition,
    )

    question_map: dict[str, Any] = {}

    for question_index, question in enumerate(
        questions,
        start=1,
    ):
        question_id = extract_question_id(
            question,
        )

        if question_id is None:
            raise ValueError(
                (
                    "アンケート定義の質問に"
                    "idが設定されていません："
                    f"{question_index}問目"
                )
            )

        if question_id in question_map:
            raise ValueError(
                (
                    "アンケート定義に重複した"
                    "質問IDがあります："
                    f"{question_id}"
                )
            )

        question_map[
            question_id
        ] = question

    return question_map


# ============================================================
# 質問IDの取得
# ============================================================
def extract_question_id(
    question: Any,
) -> str | None:
    raw_question_id = get_question_value(
        question,
        field_names=(
            "id",
            "question_id",
        ),
    )

    if raw_question_id is None:
        return None

    normalized_question_id = str(
        raw_question_id,
    ).strip()

    if not normalized_question_id:
        return None

    # ------------------------------------------------------------
    # 質問IDは回答JSONのキーとして利用する
    # ------------------------------------------------------------
    if any(
        ord(character) < 32
        for character in normalized_question_id
    ):
        raise ValueError(
            (
                "質問IDに制御文字を"
                "含めることはできません．"
            )
        )

    if len(
        normalized_question_id,
    ) > 255:
        raise ValueError(
            (
                "質問IDは255文字以内で"
                "指定してください："
                f"{normalized_question_id}"
            )
        )

    return normalized_question_id


# ============================================================
# 質問形式の取得
# ============================================================
def extract_question_type(
    question: Any,
) -> str:
    raw_question_type = get_question_value(
        question,
        field_names=(
            "type",
            "question_type",
        ),
    )

    if raw_question_type is None:
        raise ValueError(
            (
                "質問にtypeが"
                "設定されていません："
                f"{extract_question_id(question) or 'ID不明'}"
            )
        )

    # ------------------------------------------------------------
    # Enum形式への対応
    # ------------------------------------------------------------
    if hasattr(
        raw_question_type,
        "value",
    ):
        raw_question_type = getattr(
            raw_question_type,
            "value",
        )

    normalized_question_type = str(
        raw_question_type,
    ).strip().lower()

    if not normalized_question_type:
        raise ValueError(
            (
                "質問のtypeが空です："
                f"{extract_question_id(question) or 'ID不明'}"
            )
        )

    supported_question_types = {
        "radio",
        "checkbox",
        "select",
        "text",
        "textarea",
        "number",
        "date",
        "rating",
    }

    if (
        normalized_question_type
        not in supported_question_types
    ):
        raise ValueError(
            (
                "未対応の質問形式です："
                f"{normalized_question_type}"
                "，質問ID："
                f"{extract_question_id(question) or 'ID不明'}"
            )
        )

    return normalized_question_type


# ============================================================
# 質問オブジェクトから値を取得
# ============================================================
def get_question_value(
    question: Any,
    *,
    field_names: tuple[str, ...],
    default: Any = None,
) -> Any:
    if question is None:
        return default

    # ------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------
    if isinstance(
        question,
        Mapping,
    ):
        for field_name in field_names:
            if field_name in question:
                return question.get(
                    field_name,
                )

        return default

    # ------------------------------------------------------------
    # dataclass・通常クラス
    # ------------------------------------------------------------
    for field_name in field_names:
        if hasattr(
            question,
            field_name,
        ):
            return getattr(
                question,
                field_name,
            )

    return default


# ============================================================
# 質問のdefault指定有無
# ============================================================
def has_question_default(
    question: Any,
) -> bool:
    if question is None:
        return False

    if isinstance(
        question,
        Mapping,
    ):
        return (
            "default"
            in question
            or "default_value"
            in question
        )

    return (
        hasattr(
            question,
            "default",
        )
        or hasattr(
            question,
            "default_value",
        )
    )


# ============================================================
# 質問のdefault値取得
# ============================================================
def extract_raw_question_default(
    question: Any,
) -> Any:
    return get_question_value(
        question,
        field_names=(
            "default",
            "default_value",
        ),
        default=None,
    )

# ============================================================
# public API：質問形式ごとの初期回答取得
# ============================================================
def get_question_default_value(
    *,
    question: Any,
    question_type: str | None = None,
) -> Any:
    # ------------------------------------------------------------
    # 質問形式
    # ------------------------------------------------------------
    resolved_question_type = (
        question_type
        or extract_question_type(
            question,
        )
    )

    normalized_question_type = str(
        resolved_question_type,
    ).strip().lower()

    # ------------------------------------------------------------
    # default指定の有無
    # ------------------------------------------------------------
    has_default = has_question_default(
        question,
    )

    raw_default = (
        extract_raw_question_default(
            question,
        )
        if has_default
        else None
    )

    # ------------------------------------------------------------
    # radio
    # ------------------------------------------------------------
    if normalized_question_type == "radio":
        return get_radio_default_value(
            question=question,
            raw_default=raw_default,
            has_default=has_default,
        )

    # ------------------------------------------------------------
    # checkbox
    # ------------------------------------------------------------
    if normalized_question_type == "checkbox":
        return get_checkbox_default_value(
            question=question,
            raw_default=raw_default,
            has_default=has_default,
        )

    # ------------------------------------------------------------
    # select
    # ------------------------------------------------------------
    if normalized_question_type == "select":
        return get_select_default_value(
            question=question,
            raw_default=raw_default,
            has_default=has_default,
        )

    # ------------------------------------------------------------
    # text・textarea・number・date・rating
    #
    # 次回追加するnormalize_default_answer()へ渡す
    # ------------------------------------------------------------
    return normalize_default_answer(
        question=question,
        question_type=(
            normalized_question_type
        ),
        raw_default=raw_default,
        has_default=has_default,
    )


# ============================================================
# radio初期値
# ============================================================
def get_radio_default_value(
    *,
    question: Any,
    raw_default: Any,
    has_default: bool,
) -> str | None:
    # ------------------------------------------------------------
    # default未指定
    #
    # radioは未選択状態をNoneで表す
    # ------------------------------------------------------------
    if not has_default:
        return None

    # ------------------------------------------------------------
    # 明示的なnull
    # ------------------------------------------------------------
    if raw_default is None:
        return None

    # ------------------------------------------------------------
    # 複数値は許可しない
    # ------------------------------------------------------------
    if isinstance(
        raw_default,
        (
            list,
            tuple,
            set,
            dict,
        ),
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    "radioのdefaultは"
                    "単一の選択肢値で指定してください．"
                ),
            )
        )

    normalized_default = normalize_scalar_option_value(
        raw_default,
        question=question,
        question_type="radio",
    )

    option_values = extract_option_values(
        question,
    )

    # ------------------------------------------------------------
    # 選択肢との整合性
    # ------------------------------------------------------------
    if (
        normalized_default
        not in option_values
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    "radioのdefaultが"
                    "選択肢に存在しません："
                    f"{normalized_default}"
                ),
            )
        )

    return normalized_default


# ============================================================
# checkbox初期値
# ============================================================
def get_checkbox_default_value(
    *,
    question: Any,
    raw_default: Any,
    has_default: bool,
) -> list[str]:
    # ------------------------------------------------------------
    # default未指定
    #
    # checkboxは空配列を初期値とする
    # ------------------------------------------------------------
    if not has_default:
        return []

    # ------------------------------------------------------------
    # 明示的なnull
    # ------------------------------------------------------------
    if raw_default is None:
        return []

    # ------------------------------------------------------------
    # 単一文字列も1件の選択として受け入れる
    # ------------------------------------------------------------
    if isinstance(
        raw_default,
        str,
    ):
        raw_values: list[Any] = [
            raw_default,
        ]

    elif isinstance(
        raw_default,
        (
            list,
            tuple,
            set,
        ),
    ):
        raw_values = list(
            raw_default,
        )

    else:
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    "checkboxのdefaultは"
                    "選択肢値の配列で指定してください．"
                ),
            )
        )

    option_values = extract_option_values(
        question,
    )

    normalized_values: list[str] = []
    seen_values: set[str] = set()

    for raw_value in raw_values:
        normalized_value = (
            normalize_scalar_option_value(
                raw_value,
                question=question,
                question_type="checkbox",
            )
        )

        # --------------------------------------------------------
        # 選択肢との整合性
        # --------------------------------------------------------
        if normalized_value not in option_values:
            raise ValueError(
                build_default_error_message(
                    question=question,
                    message=(
                        "checkboxのdefaultに"
                        "選択肢に存在しない値が"
                        "含まれています："
                        f"{normalized_value}"
                    ),
                )
            )

        # --------------------------------------------------------
        # 重複除去
        #
        # 最初に現れた順序を維持する
        # --------------------------------------------------------
        if normalized_value in seen_values:
            continue

        seen_values.add(
            normalized_value,
        )

        normalized_values.append(
            normalized_value,
        )

    return normalized_values


# ============================================================
# select初期値
# ============================================================
def get_select_default_value(
    *,
    question: Any,
    raw_default: Any,
    has_default: bool,
) -> str | None:
    # ------------------------------------------------------------
    # default未指定
    #
    # selectは未選択状態をNoneで表す
    # ------------------------------------------------------------
    if not has_default:
        return None

    # ------------------------------------------------------------
    # 明示的なnull
    # ------------------------------------------------------------
    if raw_default is None:
        return None

    # ------------------------------------------------------------
    # 複数値は許可しない
    # ------------------------------------------------------------
    if isinstance(
        raw_default,
        (
            list,
            tuple,
            set,
            dict,
        ),
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    "selectのdefaultは"
                    "単一の選択肢値で指定してください．"
                ),
            )
        )

    normalized_default = normalize_scalar_option_value(
        raw_default,
        question=question,
        question_type="select",
    )

    option_values = extract_option_values(
        question,
    )

    # ------------------------------------------------------------
    # 選択肢との整合性
    # ------------------------------------------------------------
    if (
        normalized_default
        not in option_values
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    "selectのdefaultが"
                    "選択肢に存在しません："
                    f"{normalized_default}"
                ),
            )
        )

    return normalized_default


# ============================================================
# public API：選択肢一覧の取得
# ============================================================
def extract_options(
    question: Any,
) -> tuple[Any, ...]:
    raw_options = get_question_value(
        question,
        field_names=(
            "options",
            "choices",
        ),
        default=None,
    )

    if raw_options is None:
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    "選択式質問にoptionsが"
                    "設定されていません．"
                ),
            )
        )

    if isinstance(
        raw_options,
        (
            str,
            bytes,
            bytearray,
        ),
    ):
        raise TypeError(
            build_default_error_message(
                question=question,
                message=(
                    "optionsは選択肢オブジェクトの"
                    "配列で指定してください．"
                ),
            )
        )

    if not isinstance(
        raw_options,
        (
            list,
            tuple,
        ),
    ):
        raise TypeError(
            build_default_error_message(
                question=question,
                message=(
                    "optionsはlistまたはtupleで"
                    "指定してください．"
                ),
            )
        )

    normalized_options: list[Any] = []

    for option_index, option in enumerate(
        raw_options,
        start=1,
    ):
        if option is None:
            raise ValueError(
                build_default_error_message(
                    question=question,
                    message=(
                        "optionsにNoneが"
                        "含まれています："
                        f"{option_index}件目"
                    ),
                )
            )

        if not is_supported_option_object(
            option,
        ):
            raise TypeError(
                build_default_error_message(
                    question=question,
                    message=(
                        "選択肢は文字列，Mapping，"
                        "または属性を持つオブジェクトで"
                        "指定してください："
                        f"{option_index}件目"
                    ),
                )
            )

        normalized_options.append(
            option,
        )

    if not normalized_options:
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    "選択式質問には1件以上の"
                    "optionが必要です．"
                ),
            )
        )

    return tuple(
        normalized_options,
    )


# ============================================================
# public API：選択肢値一覧の取得
# ============================================================
def extract_option_values(
    question: Any,
) -> tuple[str, ...]:
    options = extract_options(
        question,
    )

    option_values: list[str] = []
    seen_values: set[str] = set()

    for option_index, option in enumerate(
        options,
        start=1,
    ):
        option_value = extract_option_value(
            option,
        )

        if option_value is None:
            raise ValueError(
                build_default_error_message(
                    question=question,
                    message=(
                        "選択肢にvalueが"
                        "設定されていません："
                        f"{option_index}件目"
                    ),
                )
            )

        if option_value in seen_values:
            raise ValueError(
                build_default_error_message(
                    question=question,
                    message=(
                        "選択肢のvalueが"
                        "重複しています："
                        f"{option_value}"
                    ),
                )
            )

        seen_values.add(
            option_value,
        )

        option_values.append(
            option_value,
        )

    return tuple(
        option_values,
    )


# ============================================================
# 選択肢オブジェクトの対応判定
# ============================================================
def is_supported_option_object(
    option: Any,
) -> bool:
    # ------------------------------------------------------------
    # 簡易記法
    #
    # option = "使用したことがある"
    #
    # labelとvalueを同一値として扱う
    # ------------------------------------------------------------
    if isinstance(
        option,
        str,
    ):
        return True

    if isinstance(
        option,
        Mapping,
    ):
        return True

    if hasattr(
        option,
        "__dict__",
    ):
        return True

    if (
        hasattr(
            option,
            "value",
        )
        or hasattr(
            option,
            "label",
        )
    ):
        return True

    return False


# ============================================================
# 選択肢値の取得
# ============================================================
def extract_option_value(
    option: Any,
) -> str | None:
    # ------------------------------------------------------------
    # 簡易文字列形式
    # ------------------------------------------------------------
    if isinstance(
        option,
        str,
    ):
        normalized = option.strip()

        return normalized or None

    # ------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------
    if isinstance(
        option,
        Mapping,
    ):
        if "value" in option:
            raw_value = option.get(
                "value",
            )

        elif "label" in option:
            # ----------------------------------------------------
            # value省略時はlabelを値として使用する
            # ----------------------------------------------------
            raw_value = option.get(
                "label",
            )

        else:
            return None

    # ------------------------------------------------------------
    # dataclass・通常クラス
    # ------------------------------------------------------------
    else:
        if hasattr(
            option,
            "value",
        ):
            raw_value = getattr(
                option,
                "value",
            )

        elif hasattr(
            option,
            "label",
        ):
            raw_value = getattr(
                option,
                "label",
            )

        else:
            return None

    if raw_value is None:
        return None

    normalized = str(
        raw_value,
    ).strip()

    if not normalized:
        return None

    if any(
        ord(character) < 32
        for character in normalized
    ):
        raise ValueError(
            (
                "選択肢のvalueに制御文字を"
                "含めることはできません．"
            )
        )

    if len(
        normalized,
    ) > 1000:
        raise ValueError(
            (
                "選択肢のvalueは1000文字以内で"
                "指定してください．"
            )
        )

    return normalized


# ============================================================
# 単一選択肢値の正規化
# ============================================================
def normalize_scalar_option_value(
    value: Any,
    *,
    question: Any,
    question_type: str,
) -> str:
    if value is None:
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    f"{question_type}のdefaultに"
                    "nullは指定できません．"
                ),
            )
        )

    # ------------------------------------------------------------
    # boolはTrue・Falseという選択肢を
    # 明示している場合に利用できるよう文字列化する
    # ------------------------------------------------------------
    if isinstance(
        value,
        bool,
    ):
        normalized = (
            "true"
            if value
            else "false"
        )

    elif isinstance(
        value,
        (
            str,
            int,
            float,
        ),
    ):
        normalized = str(
            value,
        ).strip()

    else:
        raise TypeError(
            build_default_error_message(
                question=question,
                message=(
                    f"{question_type}のdefaultは"
                    "文字列または単一の値で"
                    "指定してください．"
                ),
            )
        )

    if not normalized:
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    f"{question_type}のdefaultが"
                    "空です．"
                ),
            )
        )

    return normalized


# ============================================================
# defaultエラーメッセージ生成
# ============================================================
def build_default_error_message(
    *,
    question: Any,
    message: str,
) -> str:
    question_id = extract_question_id(
        question,
    )

    if question_id:
        return (
            f"{message}"
            f" 質問ID：{question_id}"
        )

    return (
        f"{message}"
        " 質問ID：不明"
    )

# ============================================================
# public API：非選択式質問の初期値正規化
# ============================================================
def normalize_default_answer(
    *,
    question: Any,
    question_type: str,
    raw_default: Any,
    has_default: bool,
) -> Any:
    normalized_question_type = str(
        question_type,
    ).strip().lower()

    # ------------------------------------------------------------
    # text
    # ------------------------------------------------------------
    if normalized_question_type == "text":
        return get_text_default_value(
            question=question,
            raw_default=raw_default,
            has_default=has_default,
        )

    # ------------------------------------------------------------
    # textarea
    # ------------------------------------------------------------
    if normalized_question_type == "textarea":
        return get_textarea_default_value(
            question=question,
            raw_default=raw_default,
            has_default=has_default,
        )

    # ------------------------------------------------------------
    # number
    # ------------------------------------------------------------
    if normalized_question_type == "number":
        return get_number_default_value(
            question=question,
            raw_default=raw_default,
            has_default=has_default,
        )

    # ------------------------------------------------------------
    # date
    # ------------------------------------------------------------
    if normalized_question_type == "date":
        return get_date_default_value(
            question=question,
            raw_default=raw_default,
            has_default=has_default,
        )

    # ------------------------------------------------------------
    # rating
    # ------------------------------------------------------------
    if normalized_question_type == "rating":
        return get_rating_default_value(
            question=question,
            raw_default=raw_default,
            has_default=has_default,
        )

    raise ValueError(
        build_default_error_message(
            question=question,
            message=(
                "初期回答を生成できない"
                "質問形式です："
                f"{normalized_question_type}"
            ),
        )
    )


# ============================================================
# text初期値
# ============================================================
def get_text_default_value(
    *,
    question: Any,
    raw_default: Any,
    has_default: bool,
) -> str:
    # ------------------------------------------------------------
    # default未指定
    # ------------------------------------------------------------
    if not has_default:
        return ""

    # ------------------------------------------------------------
    # 明示的なnull
    # ------------------------------------------------------------
    if raw_default is None:
        return ""

    # ------------------------------------------------------------
    # 配列・辞書は許可しない
    # ------------------------------------------------------------
    if isinstance(
        raw_default,
        (
            list,
            tuple,
            set,
            dict,
        ),
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    "textのdefaultは"
                    "単一の文字列で指定してください．"
                ),
            )
        )

    normalized = str(
        raw_default,
    )

    validate_text_default_length(
        question=question,
        value=normalized,
        question_type="text",
    )

    return normalized


# ============================================================
# textarea初期値
# ============================================================
def get_textarea_default_value(
    *,
    question: Any,
    raw_default: Any,
    has_default: bool,
) -> str:
    # ------------------------------------------------------------
    # default未指定
    # ------------------------------------------------------------
    if not has_default:
        return ""

    # ------------------------------------------------------------
    # 明示的なnull
    # ------------------------------------------------------------
    if raw_default is None:
        return ""

    # ------------------------------------------------------------
    # 配列・辞書は許可しない
    # ------------------------------------------------------------
    if isinstance(
        raw_default,
        (
            list,
            tuple,
            set,
            dict,
        ),
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    "textareaのdefaultは"
                    "単一の文字列で指定してください．"
                ),
            )
        )

    normalized = str(
        raw_default,
    )

    validate_text_default_length(
        question=question,
        value=normalized,
        question_type="textarea",
    )

    return normalized


# ============================================================
# number初期値
# ============================================================
def get_number_default_value(
    *,
    question: Any,
    raw_default: Any,
    has_default: bool,
) -> int | float | None:
    # ------------------------------------------------------------
    # default未指定
    # ------------------------------------------------------------
    if not has_default:
        return None

    # ------------------------------------------------------------
    # 明示的なnull
    # ------------------------------------------------------------
    if raw_default is None:
        return None

    normalized = normalize_numeric_value(
        raw_default,
        question=question,
        field_name="default",
    )

    minimum = extract_optional_numeric_attribute(
        question,
        field_names=(
            "min",
            "minimum",
        ),
        attribute_name="min",
    )

    maximum = extract_optional_numeric_attribute(
        question,
        field_names=(
            "max",
            "maximum",
        ),
        attribute_name="max",
    )

    step = extract_optional_numeric_attribute(
        question,
        field_names=(
            "step",
        ),
        attribute_name="step",
    )

    # ------------------------------------------------------------
    # min・max設定自体の整合性
    # ------------------------------------------------------------
    validate_numeric_range_definition(
        question=question,
        minimum=minimum,
        maximum=maximum,
    )

    # ------------------------------------------------------------
    # defaultの範囲確認
    # ------------------------------------------------------------
    validate_numeric_default_range(
        question=question,
        value=normalized,
        minimum=minimum,
        maximum=maximum,
        question_type="number",
    )

    # ------------------------------------------------------------
    # step確認
    # ------------------------------------------------------------
    validate_numeric_default_step(
        question=question,
        value=normalized,
        minimum=minimum,
        step=step,
        question_type="number",
    )

    return normalized


# ============================================================
# date初期値
# ============================================================
def get_date_default_value(
    *,
    question: Any,
    raw_default: Any,
    has_default: bool,
) -> str | None:
    # ------------------------------------------------------------
    # default未指定
    # ------------------------------------------------------------
    if not has_default:
        return None

    # ------------------------------------------------------------
    # 明示的なnull
    # ------------------------------------------------------------
    if raw_default is None:
        return None

    normalized = normalize_date_value(
        raw_default,
        question=question,
        field_name="default",
    )

    minimum = extract_optional_date_attribute(
        question,
        field_names=(
            "min",
            "minimum",
            "min_date",
        ),
        attribute_name="min",
    )

    maximum = extract_optional_date_attribute(
        question,
        field_names=(
            "max",
            "maximum",
            "max_date",
        ),
        attribute_name="max",
    )

    # ------------------------------------------------------------
    # min・max設定自体の整合性
    # ------------------------------------------------------------
    if (
        minimum is not None
        and maximum is not None
        and minimum > maximum
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    "dateのminはmax以下に"
                    "設定してください．"
                ),
            )
        )

    # ------------------------------------------------------------
    # defaultの範囲確認
    # ------------------------------------------------------------
    parsed_default = date.fromisoformat(
        normalized,
    )

    if (
        minimum is not None
        and parsed_default < minimum
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    "dateのdefaultが"
                    "minより前です："
                    f"{normalized}"
                ),
            )
        )

    if (
        maximum is not None
        and parsed_default > maximum
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    "dateのdefaultが"
                    "maxより後です："
                    f"{normalized}"
                ),
            )
        )

    return normalized


# ============================================================
# rating初期値
# ============================================================
def get_rating_default_value(
    *,
    question: Any,
    raw_default: Any,
    has_default: bool,
) -> int | float | None:
    # ------------------------------------------------------------
    # ratingの既定範囲
    #
    # min・max未指定時：
    # - min = 1
    # - max = 5
    # ------------------------------------------------------------
    minimum = extract_optional_numeric_attribute(
        question,
        field_names=(
            "min",
            "minimum",
        ),
        attribute_name="min",
    )

    maximum = extract_optional_numeric_attribute(
        question,
        field_names=(
            "max",
            "maximum",
        ),
        attribute_name="max",
    )

    step = extract_optional_numeric_attribute(
        question,
        field_names=(
            "step",
        ),
        attribute_name="step",
    )

    if minimum is None:
        minimum = 1

    if maximum is None:
        maximum = 5

    if step is None:
        step = 1

    validate_numeric_range_definition(
        question=question,
        minimum=minimum,
        maximum=maximum,
    )

    if step <= 0:
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    "ratingのstepは0より"
                    "大きい値で指定してください．"
                ),
            )
        )

    # ------------------------------------------------------------
    # default未指定
    # ------------------------------------------------------------
    if not has_default:
        return None

    # ------------------------------------------------------------
    # 明示的なnull
    # ------------------------------------------------------------
    if raw_default is None:
        return None

    normalized = normalize_numeric_value(
        raw_default,
        question=question,
        field_name="default",
    )

    validate_numeric_default_range(
        question=question,
        value=normalized,
        minimum=minimum,
        maximum=maximum,
        question_type="rating",
    )

    validate_numeric_default_step(
        question=question,
        value=normalized,
        minimum=minimum,
        step=step,
        question_type="rating",
    )

    return normalized


# ============================================================
# text・textareaの最大文字数確認
# ============================================================
def validate_text_default_length(
    *,
    question: Any,
    value: str,
    question_type: str,
) -> None:
    raw_max_length = get_question_value(
        question,
        field_names=(
            "max_length",
            "maxlength",
        ),
        default=None,
    )

    if raw_max_length is None:
        return

    max_length = normalize_positive_integer(
        raw_max_length,
        question=question,
        field_name="max_length",
        allow_zero=True,
    )

    if len(value) > max_length:
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    f"{question_type}のdefaultが"
                    "max_lengthを超えています："
                    f"{len(value)}文字／"
                    f"上限{max_length}文字"
                ),
            )
        )


# ============================================================
# 数値属性の取得
# ============================================================
def extract_optional_numeric_attribute(
    question: Any,
    *,
    field_names: tuple[str, ...],
    attribute_name: str,
) -> int | float | None:
    raw_value = get_question_value(
        question,
        field_names=field_names,
        default=None,
    )

    if raw_value is None:
        return None

    return normalize_numeric_value(
        raw_value,
        question=question,
        field_name=attribute_name,
    )


# ============================================================
# 数値の正規化
# ============================================================
def normalize_numeric_value(
    value: Any,
    *,
    question: Any,
    field_name: str,
) -> int | float:
    if isinstance(
        value,
        bool,
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    f"{field_name}は数値で"
                    "指定してください．"
                ),
            )
        )

    if isinstance(
        value,
        int,
    ):
        return value

    if isinstance(
        value,
        float,
    ):
        if not math.isfinite(
            value,
        ):
            raise ValueError(
                build_default_error_message(
                    question=question,
                    message=(
                        f"{field_name}に"
                        "無限大またはNaNは"
                        "指定できません．"
                    ),
                )
            )

        if value.is_integer():
            return int(
                value,
            )

        return value

    if isinstance(
        value,
        str,
    ):
        stripped = value.strip()

        if not stripped:
            raise ValueError(
                build_default_error_message(
                    question=question,
                    message=(
                        f"{field_name}が空です．"
                    ),
                )
            )

        try:
            parsed = float(
                stripped,
            )

        except ValueError as exc:
            raise ValueError(
                build_default_error_message(
                    question=question,
                    message=(
                        f"{field_name}を数値として"
                        "解釈できません："
                        f"{stripped}"
                    ),
                )
            ) from exc

        if not math.isfinite(
            parsed,
        ):
            raise ValueError(
                build_default_error_message(
                    question=question,
                    message=(
                        f"{field_name}に"
                        "無限大またはNaNは"
                        "指定できません．"
                    ),
                )
            )

        if parsed.is_integer():
            return int(
                parsed,
            )

        return parsed

    raise TypeError(
        build_default_error_message(
            question=question,
            message=(
                f"{field_name}は数値または"
                "数値形式の文字列で"
                "指定してください．"
            ),
        )
    )


# ============================================================
# 数値範囲定義の検証
# ============================================================
def validate_numeric_range_definition(
    *,
    question: Any,
    minimum: int | float | None,
    maximum: int | float | None,
) -> None:
    if (
        minimum is not None
        and maximum is not None
        and minimum > maximum
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    "minはmax以下に"
                    "設定してください．"
                ),
            )
        )


# ============================================================
# 数値defaultの範囲確認
# ============================================================
def validate_numeric_default_range(
    *,
    question: Any,
    value: int | float,
    minimum: int | float | None,
    maximum: int | float | None,
    question_type: str,
) -> None:
    if (
        minimum is not None
        and value < minimum
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    f"{question_type}のdefaultが"
                    "min未満です："
                    f"{value}"
                ),
            )
        )

    if (
        maximum is not None
        and value > maximum
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    f"{question_type}のdefaultが"
                    "maxを超えています："
                    f"{value}"
                ),
            )
        )


# ============================================================
# 数値defaultのstep確認
# ============================================================
def validate_numeric_default_step(
    *,
    question: Any,
    value: int | float,
    minimum: int | float | None,
    step: int | float | None,
    question_type: str,
) -> None:
    if step is None:
        return

    if step <= 0:
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    f"{question_type}のstepは"
                    "0より大きい値で"
                    "指定してください．"
                ),
            )
        )

    base_value = (
        minimum
        if minimum is not None
        else 0
    )

    difference = (
        float(value)
        - float(base_value)
    )

    quotient = (
        difference
        / float(step)
    )

    # ------------------------------------------------------------
    # 浮動小数点誤差を考慮して整数倍か判定する
    # ------------------------------------------------------------
    if not math.isclose(
        quotient,
        round(
            quotient,
        ),
        rel_tol=1e-9,
        abs_tol=1e-9,
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    f"{question_type}のdefaultが"
                    "stepに一致しません："
                    f"default={value}，"
                    f"step={step}"
                ),
            )
        )


# ============================================================
# 日付属性の取得
# ============================================================
def extract_optional_date_attribute(
    question: Any,
    *,
    field_names: tuple[str, ...],
    attribute_name: str,
) -> date | None:
    raw_value = get_question_value(
        question,
        field_names=field_names,
        default=None,
    )

    if raw_value is None:
        return None

    normalized = normalize_date_value(
        raw_value,
        question=question,
        field_name=attribute_name,
    )

    return date.fromisoformat(
        normalized,
    )


# ============================================================
# 日付の正規化
# ============================================================
def normalize_date_value(
    value: Any,
    *,
    question: Any,
    field_name: str,
) -> str:
    # ------------------------------------------------------------
    # datetime
    # ------------------------------------------------------------
    if isinstance(
        value,
        datetime,
    ):
        return value.date().isoformat()

    # ------------------------------------------------------------
    # date
    # ------------------------------------------------------------
    if isinstance(
        value,
        date,
    ):
        return value.isoformat()

    # ------------------------------------------------------------
    # 文字列
    # ------------------------------------------------------------
    if isinstance(
        value,
        str,
    ):
        stripped = value.strip()

        if not stripped:
            raise ValueError(
                build_default_error_message(
                    question=question,
                    message=(
                        f"{field_name}が空です．"
                    ),
                )
            )

        try:
            parsed = date.fromisoformat(
                stripped,
            )

        except ValueError as exc:
            raise ValueError(
                build_default_error_message(
                    question=question,
                    message=(
                        f"{field_name}は"
                        "YYYY-MM-DD形式で"
                        "指定してください："
                        f"{stripped}"
                    ),
                )
            ) from exc

        return parsed.isoformat()

    raise TypeError(
        build_default_error_message(
            question=question,
            message=(
                f"{field_name}はdate型，"
                "datetime型，または"
                "YYYY-MM-DD形式の文字列で"
                "指定してください．"
            ),
        )
    )


# ============================================================
# 0以上の整数の正規化
# ============================================================
def normalize_positive_integer(
    value: Any,
    *,
    question: Any,
    field_name: str,
    allow_zero: bool = False,
) -> int:
    if isinstance(
        value,
        bool,
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    f"{field_name}は整数で"
                    "指定してください．"
                ),
            )
        )

    if isinstance(
        value,
        int,
    ):
        normalized = value

    elif isinstance(
        value,
        str,
    ):
        stripped = value.strip()

        if not stripped:
            raise ValueError(
                build_default_error_message(
                    question=question,
                    message=(
                        f"{field_name}が空です．"
                    ),
                )
            )

        try:
            normalized = int(
                stripped,
            )

        except ValueError as exc:
            raise ValueError(
                build_default_error_message(
                    question=question,
                    message=(
                        f"{field_name}は整数で"
                        "指定してください．"
                    ),
                )
            ) from exc

    else:
        raise TypeError(
            build_default_error_message(
                question=question,
                message=(
                    f"{field_name}は整数または"
                    "整数形式の文字列で"
                    "指定してください．"
                ),
            )
        )

    minimum_value = (
        0
        if allow_zero
        else 1
    )

    if normalized < minimum_value:
        comparator_text = (
            "0以上"
            if allow_zero
            else "1以上"
        )

        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    f"{field_name}は"
                    f"{comparator_text}の整数で"
                    "指定してください．"
                ),
            )
        )

    return normalized

# ============================================================
# 値がスカラーか判定
# ============================================================
def is_scalar_value(
    value: Any,
) -> bool:
    return isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    )


# ============================================================
# 値がコレクションか判定
# ============================================================
def is_collection_value(
    value: Any,
) -> bool:
    return isinstance(
        value,
        (
            list,
            tuple,
            set,
            dict,
        ),
    )


# ============================================================
# Noneまたは空文字か判定
# ============================================================
def is_empty_string(
    value: Any,
) -> bool:
    return (
        isinstance(value, str)
        and not value.strip()
    )


# ============================================================
# bool禁止
# ============================================================
def validate_not_bool(
    *,
    value: Any,
    question: Any,
    field_name: str,
) -> None:
    if isinstance(
        value,
        bool,
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    f"{field_name}に"
                    "True/Falseは指定できません．"
                ),
            )
        )


# ============================================================
# 文字列へ変換
# ============================================================
def normalize_string(
    *,
    value: Any,
    question: Any,
    field_name: str,
    allow_empty: bool = False,
) -> str:
    if value is None:
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    f"{field_name}が未指定です．"
                ),
            )
        )

    if is_collection_value(
        value,
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    f"{field_name}は"
                    "文字列で指定してください．"
                ),
            )
        )

    normalized = str(
        value,
    )

    if (
        not allow_empty
        and not normalized.strip()
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    f"{field_name}が空です．"
                ),
            )
        )

    return normalized


# ============================================================
# 制御文字チェック
# ============================================================
def validate_no_control_characters(
    *,
    value: str,
    question: Any,
    field_name: str,
) -> None:
    for character in value:
        if ord(character) < 32:
            raise ValueError(
                build_default_error_message(
                    question=question,
                    message=(
                        f"{field_name}に"
                        "制御文字を含めることは"
                        "できません．"
                    ),
                )
            )


# ============================================================
# 最大長チェック
# ============================================================
def validate_max_length(
    *,
    value: str,
    maximum: int,
    question: Any,
    field_name: str,
) -> None:
    if len(value) > maximum:
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    f"{field_name}は"
                    f"{maximum}文字以内で"
                    "指定してください．"
                ),
            )
        )


# ============================================================
# 数値か判定
# ============================================================
def is_numeric_value(
    value: Any,
) -> bool:
    if isinstance(
        value,
        bool,
    ):
        return False

    return isinstance(
        value,
        (
            int,
            float,
        ),
    )


# ============================================================
# 有限数か判定
# ============================================================
def validate_finite_number(
    *,
    value: float,
    question: Any,
    field_name: str,
) -> None:
    if not math.isfinite(
        value,
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    f"{field_name}に"
                    "NaNまたはInfinityは"
                    "指定できません．"
                ),
            )
        )


# ============================================================
# 数値をfloatへ
# ============================================================
def to_float(
    *,
    value: Any,
    question: Any,
    field_name: str,
) -> float:
    numeric = normalize_numeric_value(
        value,
        question=question,
        field_name=field_name,
    )

    result = float(
        numeric,
    )

    validate_finite_number(
        value=result,
        question=question,
        field_name=field_name,
    )

    return result

# ============================================================
# date型へ変換
# ============================================================
def to_date(
    *,
    value: Any,
    question: Any,
    field_name: str,
) -> date:
    normalized = normalize_date_value(
        value,
        question=question,
        field_name=field_name,
    )

    return date.fromisoformat(
        normalized,
    )


# ============================================================
# 最小値・最大値範囲判定
# ============================================================
def validate_range(
    *,
    value: float,
    minimum: float | None,
    maximum: float | None,
    question: Any,
    field_name: str,
) -> None:
    if (
        minimum is not None
        and value < minimum
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    f"{field_name}が"
                    "最小値未満です．"
                ),
            )
        )

    if (
        maximum is not None
        and value > maximum
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    f"{field_name}が"
                    "最大値を超えています．"
                ),
            )
        )


# ============================================================
# 日付範囲判定
# ============================================================
def validate_date_range(
    *,
    value: date,
    minimum: date | None,
    maximum: date | None,
    question: Any,
    field_name: str,
) -> None:
    if (
        minimum is not None
        and value < minimum
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    f"{field_name}が"
                    "最小日付より前です．"
                ),
            )
        )

    if (
        maximum is not None
        and value > maximum
    ):
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    f"{field_name}が"
                    "最大日付より後です．"
                ),
            )
        )


# ============================================================
# option値存在確認
# ============================================================
def validate_option_exists(
    *,
    option_value: str,
    option_values: tuple[str, ...],
    question: Any,
) -> None:
    if option_value not in option_values:
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    "存在しない選択肢です："
                    f"{option_value}"
                ),
            )
        )


# ============================================================
# optionラベル一覧取得
# ============================================================
def extract_option_labels(
    question: Any,
) -> tuple[str, ...]:
    options = extract_options(
        question,
    )

    labels: list[str] = []

    for option in options:

        if isinstance(
            option,
            str,
        ):
            labels.append(
                option,
            )
            continue

        label = get_question_value(
            option,
            field_names=(
                "label",
            ),
            default=None,
        )

        if label is None:
            value = extract_option_value(
                option,
            )

            labels.append(
                value or "",
            )

        else:
            labels.append(
                str(label),
            )

    return tuple(
        labels,
    )


# ============================================================
# Mapping・dataclass共通取得
# ============================================================
def get_object_value(
    obj: Any,
    *,
    field_name: str,
    default: Any = None,
) -> Any:
    if obj is None:
        return default

    if isinstance(
        obj,
        Mapping,
    ):
        return obj.get(
            field_name,
            default,
        )

    if hasattr(
        obj,
        field_name,
    ):
        return getattr(
            obj,
            field_name,
        )

    return default


# ============================================================
# 値が存在するか
# ============================================================
def has_object_value(
    obj: Any,
    field_name: str,
) -> bool:
    if obj is None:
        return False

    if isinstance(
        obj,
        Mapping,
    ):
        return field_name in obj

    return hasattr(
        obj,
        field_name,
    )


# ============================================================
# Mappingコピー
# ============================================================
def copy_mapping(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    copied: dict[str, Any] = {}

    for key, item in value.items():
        copied[key] = item

    return copied


# ============================================================
# listコピー
# ============================================================
def copy_sequence(
    value: list[Any],
) -> list[Any]:
    copied: list[Any] = []

    for item in value:
        copied.append(
            item,
        )

    return copied


# ============================================================
# 空dict生成
# ============================================================
def empty_mapping() -> dict[str, Any]:
    return {}


# ============================================================
# 空list生成
# ============================================================
def empty_sequence() -> list[Any]:
    return []


# ============================================================
# エラー用質問ID
# ============================================================
def get_question_identifier(
    question: Any,
) -> str:
    question_id = extract_question_id(
        question,
    )

    if question_id is not None:
        return question_id

    return "unknown"


# ============================================================
# 型名取得
# ============================================================
def get_type_name(
    value: Any,
) -> str:
    return type(
        value,
    ).__name__


# ============================================================
# デバッグ表示
# ============================================================
def describe_value(
    value: Any,
) -> str:
    if value is None:
        return "None"

    return (
        f"{repr(value)}"
        f" ({get_type_name(value)})"
    )

# ============================================================
# Sequenceを文字列listへ正規化
# ============================================================
def normalize_string_sequence(
    value: Any,
    *,
    question: Any,
    field_name: str,
    allow_single_string: bool = False,
    allow_empty_items: bool = False,
) -> list[str]:
    # ------------------------------------------------------------
    # 単一文字列
    # ------------------------------------------------------------
    if isinstance(
        value,
        str,
    ):
        if not allow_single_string:
            raise TypeError(
                build_default_error_message(
                    question=question,
                    message=(
                        f"{field_name}は文字列の"
                        "配列で指定してください．"
                    ),
                )
            )

        raw_items: list[Any] = [
            value,
        ]

    # ------------------------------------------------------------
    # list・tuple・set
    # ------------------------------------------------------------
    elif isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        raw_items = list(
            value,
        )

    else:
        raise TypeError(
            build_default_error_message(
                question=question,
                message=(
                    f"{field_name}は文字列の"
                    "配列で指定してください．"
                ),
            )
        )

    normalized_items: list[str] = []

    for item_index, raw_item in enumerate(
        raw_items,
        start=1,
    ):
        if raw_item is None:
            raise ValueError(
                build_default_error_message(
                    question=question,
                    message=(
                        f"{field_name}にNoneが"
                        "含まれています："
                        f"{item_index}件目"
                    ),
                )
            )

        if is_collection_value(
            raw_item,
        ):
            raise TypeError(
                build_default_error_message(
                    question=question,
                    message=(
                        f"{field_name}に配列または"
                        "辞書が含まれています："
                        f"{item_index}件目"
                    ),
                )
            )

        normalized_item = str(
            raw_item,
        ).strip()

        if (
            not normalized_item
            and not allow_empty_items
        ):
            raise ValueError(
                build_default_error_message(
                    question=question,
                    message=(
                        f"{field_name}に空文字が"
                        "含まれています："
                        f"{item_index}件目"
                    ),
                )
            )

        normalized_items.append(
            normalized_item,
        )

    return normalized_items


# ============================================================
# 文字列listの重複除去
# ============================================================
def deduplicate_strings(
    values: list[str],
) -> list[str]:
    normalized_values: list[str] = []
    seen_values: set[str] = set()

    for value in values:
        if value in seen_values:
            continue

        seen_values.add(
            value,
        )

        normalized_values.append(
            value,
        )

    return normalized_values


# ============================================================
# 初期回答値を安全にコピー
# ============================================================
def clone_initial_answer_value(
    value: Any,
) -> Any:
    # ------------------------------------------------------------
    # JSONスカラー
    # ------------------------------------------------------------
    if value is None:
        return None

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    # ------------------------------------------------------------
    # list
    # ------------------------------------------------------------
    if isinstance(
        value,
        list,
    ):
        return [
            clone_initial_answer_value(
                item,
            )
            for item in value
        ]

    # ------------------------------------------------------------
    # tuple・set
    #
    # 回答JSONではlistへ統一する
    # ------------------------------------------------------------
    if isinstance(
        value,
        (
            tuple,
            set,
        ),
    ):
        return [
            clone_initial_answer_value(
                item,
            )
            for item in value
        ]

    # ------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------
    if isinstance(
        value,
        Mapping,
    ):
        cloned_mapping: dict[str, Any] = {}

        for key, item in value.items():
            normalized_key = str(
                key,
            )

            cloned_mapping[
                normalized_key
            ] = clone_initial_answer_value(
                item,
            )

        return cloned_mapping

    # ------------------------------------------------------------
    # date・datetime
    # ------------------------------------------------------------
    if isinstance(
        value,
        datetime,
    ):
        return value.isoformat()

    if isinstance(
        value,
        date,
    ):
        return value.isoformat()

    raise TypeError(
        (
            "初期回答にJSON保存できない"
            "値が含まれています："
            f"{describe_value(value)}"
        )
    )


# ============================================================
# 初期回答がJSON保存可能か確認
# ============================================================
def validate_initial_answer_json_value(
    *,
    value: Any,
    question: Any,
) -> None:
    cloned_value = clone_initial_answer_value(
        value,
    )

    try:
        json.dumps(
            cloned_value,
            ensure_ascii=False,
            allow_nan=False,
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            build_default_error_message(
                question=question,
                message=(
                    "初期回答をJSON形式で"
                    "保存できません："
                    f"{describe_value(value)}"
                ),
            )
        ) from exc


# ============================================================
# 質問形式と初期回答型の整合性確認
# ============================================================
def validate_initial_answer_type(
    *,
    question: Any,
    question_type: str,
    value: Any,
) -> None:
    normalized_question_type = str(
        question_type,
    ).strip().lower()

    # ------------------------------------------------------------
    # radio・select
    # ------------------------------------------------------------
    if normalized_question_type in {
        "radio",
        "select",
    }:
        if (
            value is not None
            and not isinstance(
                value,
                str,
            )
        ):
            raise TypeError(
                build_default_error_message(
                    question=question,
                    message=(
                        f"{normalized_question_type}の"
                        "初期回答は文字列または"
                        "Noneである必要があります．"
                    ),
                )
            )

        return

    # ------------------------------------------------------------
    # checkbox
    # ------------------------------------------------------------
    if normalized_question_type == "checkbox":
        if not isinstance(
            value,
            list,
        ):
            raise TypeError(
                build_default_error_message(
                    question=question,
                    message=(
                        "checkboxの初期回答は"
                        "listである必要があります．"
                    ),
                )
            )

        if not all(
            isinstance(
                item,
                str,
            )
            for item in value
        ):
            raise TypeError(
                build_default_error_message(
                    question=question,
                    message=(
                        "checkboxの初期回答には"
                        "文字列だけを指定してください．"
                    ),
                )
            )

        return

    # ------------------------------------------------------------
    # text・textarea
    # ------------------------------------------------------------
    if normalized_question_type in {
        "text",
        "textarea",
    }:
        if not isinstance(
            value,
            str,
        ):
            raise TypeError(
                build_default_error_message(
                    question=question,
                    message=(
                        f"{normalized_question_type}の"
                        "初期回答は文字列である"
                        "必要があります．"
                    ),
                )
            )

        return

    # ------------------------------------------------------------
    # number・rating
    # ------------------------------------------------------------
    if normalized_question_type in {
        "number",
        "rating",
    }:
        if value is None:
            return

        if (
            isinstance(
                value,
                bool,
            )
            or not isinstance(
                value,
                (
                    int,
                    float,
                ),
            )
        ):
            raise TypeError(
                build_default_error_message(
                    question=question,
                    message=(
                        f"{normalized_question_type}の"
                        "初期回答は数値または"
                        "Noneである必要があります．"
                    ),
                )
            )

        return

    # ------------------------------------------------------------
    # date
    # ------------------------------------------------------------
    if normalized_question_type == "date":
        if (
            value is not None
            and not isinstance(
                value,
                str,
            )
        ):
            raise TypeError(
                build_default_error_message(
                    question=question,
                    message=(
                        "dateの初期回答は"
                        "YYYY-MM-DD形式の文字列または"
                        "Noneである必要があります．"
                    ),
                )
            )

        return

    raise ValueError(
        build_default_error_message(
            question=question,
            message=(
                "初期回答型を確認できない"
                "質問形式です："
                f"{normalized_question_type}"
            ),
        )
    )


# ============================================================
# 質問初期回答の最終確認
# ============================================================
def finalize_question_default_value(
    *,
    question: Any,
    question_type: str,
    value: Any,
) -> Any:
    validate_initial_answer_type(
        question=question,
        question_type=question_type,
        value=value,
    )

    validate_initial_answer_json_value(
        value=value,
        question=question,
    )

    return clone_initial_answer_value(
        value,
    )


# ============================================================
# 初期回答全体の最終確認
# ============================================================
def validate_empty_answers(
    *,
    survey_definition: Any,
    answers: Mapping[str, Any],
) -> None:
    question_map = build_question_map(
        survey_definition,
    )

    expected_question_ids = set(
        question_map.keys(),
    )

    actual_question_ids = set(
        answers.keys(),
    )

    # ------------------------------------------------------------
    # 不足している質問ID
    # ------------------------------------------------------------
    missing_question_ids = (
        expected_question_ids
        - actual_question_ids
    )

    if missing_question_ids:
        missing_text = "，".join(
            sorted(
                missing_question_ids,
            )
        )

        raise ValueError(
            (
                "初期回答に含まれていない"
                "質問IDがあります："
                f"{missing_text}"
            )
        )

    # ------------------------------------------------------------
    # 定義に存在しない質問ID
    # ------------------------------------------------------------
    unknown_question_ids = (
        actual_question_ids
        - expected_question_ids
    )

    if unknown_question_ids:
        unknown_text = "，".join(
            sorted(
                unknown_question_ids,
            )
        )

        raise ValueError(
            (
                "初期回答に定義外の"
                "質問IDがあります："
                f"{unknown_text}"
            )
        )

    # ------------------------------------------------------------
    # 質問形式ごとの確認
    # ------------------------------------------------------------
    for question_id, question in (
        question_map.items()
    ):
        question_type = extract_question_type(
            question,
        )

        answer_value = answers[
            question_id
        ]

        validate_initial_answer_type(
            question=question,
            question_type=question_type,
            value=answer_value,
        )

        validate_initial_answer_json_value(
            value=answer_value,
            question=question,
        )


# ============================================================
# 初期回答全体を安全にコピー
# ============================================================
def clone_empty_answers(
    answers: Mapping[str, Any],
) -> dict[str, Any]:
    cloned_answers: dict[str, Any] = {}

    for question_id, answer_value in (
        answers.items()
    ):
        normalized_question_id = str(
            question_id,
        ).strip()

        if not normalized_question_id:
            raise ValueError(
                (
                    "初期回答に空の質問IDが"
                    "含まれています．"
                )
            )

        cloned_answers[
            normalized_question_id
        ] = clone_initial_answer_value(
            answer_value,
        )

    return cloned_answers
