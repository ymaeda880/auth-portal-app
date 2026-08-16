# -*- coding: utf-8 -*-
# auth_portal_app/lib/survey/runtime/response_saver.py
# ============================================================
# アンケート回答保存
#
# 機能：
# - 現在回答JSONを保存する
# - 既存回答を履歴フォルダへ退避する
# - 一時ファイルを使用して原子的に置換する
# - 保存日時をUTCで記録する
#
# 方針：
# - 再回答時は現在回答を上書きする
# - 上書き前の回答はhistoryへ保存する
# - JSONはUTF-8・ensure_ascii=Falseで保存する
# - 保存途中の破損を避けるためos.replace()を使用する
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from .response_loader import (
    build_current_response_path,
    build_response_history_directory,
    normalize_path_component,
    parse_response_datetime,
)


# ============================================================
# UTC
# ============================================================
UTC = timezone.utc


# ============================================================
# 保存結果
# ============================================================
@dataclass(frozen=True)
class SurveyResponseSaveResult:
    # ------------------------------------------------------------
    # 保存状態
    # ------------------------------------------------------------
    success: bool
    message: str

    # ------------------------------------------------------------
    # 回答識別情報
    # ------------------------------------------------------------
    survey_id: str
    user_sub: str
    response_id: str | None
    response_revision: int | None

    # ------------------------------------------------------------
    # 保存先
    # ------------------------------------------------------------
    response_path: Path | None
    history_path: Path | None

    # ------------------------------------------------------------
    # 保存日時
    # ------------------------------------------------------------
    saved_at: datetime | None

    # ------------------------------------------------------------
    # 保存データ
    # ------------------------------------------------------------
    response_data: dict[str, Any] | None

    @property
    def history_created(self) -> bool:
        return self.history_path is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "survey_id": self.survey_id,
            "user_sub": self.user_sub,
            "response_id": self.response_id,
            "response_revision": (
                self.response_revision
            ),
            "response_path": (
                str(self.response_path)
                if self.response_path is not None
                else None
            ),
            "history_path": (
                str(self.history_path)
                if self.history_path is not None
                else None
            ),
            "history_created": (
                self.history_created
            ),
            "saved_at": (
                self.saved_at.isoformat()
                if self.saved_at is not None
                else None
            ),
            "response_data": (
                dict(self.response_data)
                if self.response_data is not None
                else None
            ),
        }


# ============================================================
# 履歴退避結果
# ============================================================
@dataclass(frozen=True)
class SurveyResponseArchiveResult:
    # ------------------------------------------------------------
    # 履歴作成状態
    # ------------------------------------------------------------
    archived: bool
    message: str

    # ------------------------------------------------------------
    # パス
    # ------------------------------------------------------------
    source_path: Path
    history_path: Path | None

    # ------------------------------------------------------------
    # 履歴日時
    # ------------------------------------------------------------
    archived_at: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "archived": self.archived,
            "message": self.message,
            "source_path": str(
                self.source_path,
            ),
            "history_path": (
                str(self.history_path)
                if self.history_path is not None
                else None
            ),
            "archived_at": (
                self.archived_at.isoformat()
                if self.archived_at is not None
                else None
            ),
        }


# ============================================================
# public API：現在回答の保存
# ============================================================
def save_current_response(
    *,
    survey_root: Path,
    survey_id: str,
    user_sub: str,
    response_data: Mapping[str, Any],
    archive_existing: bool = True,
    now: datetime | None = None,
) -> SurveyResponseSaveResult:
    # ------------------------------------------------------------
    # 入力値の正規化
    # ------------------------------------------------------------
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

    normalized_saved_at = normalize_save_datetime(
        now,
    )

    # ------------------------------------------------------------
    # 保存データ
    # ------------------------------------------------------------
    normalized_response_data = (
        prepare_response_data_for_save(
            response_data=response_data,
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
            saved_at=normalized_saved_at,
        )
    )

    # ------------------------------------------------------------
    # 現在回答の保存先
    # ------------------------------------------------------------
    response_path = build_current_response_path(
        responses_root=survey_root,
        survey_id=normalized_survey_id,
        user_sub=normalized_user_sub,
    )

    response_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ------------------------------------------------------------
    # 既存回答の履歴退避
    # ------------------------------------------------------------
    history_path: Path | None = None

    if (
        archive_existing
        and response_path.exists()
    ):
        archive_result = archive_existing_response(
            survey_root=survey_root,
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
            source_path=response_path,
            now=normalized_saved_at,
        )

        if not archive_result.archived:
            return SurveyResponseSaveResult(
                success=False,
                message=(
                    "既存回答の履歴退避に"
                    "失敗したため，回答を保存しませんでした．"
                ),
                survey_id=normalized_survey_id,
                user_sub=normalized_user_sub,
                response_id=extract_response_id(
                    normalized_response_data,
                ),
                response_revision=(
                    extract_response_revision(
                        normalized_response_data,
                    )
                ),
                response_path=response_path,
                history_path=None,
                saved_at=None,
                response_data=None,
            )

        history_path = (
            archive_result.history_path
        )

    # ------------------------------------------------------------
    # 回答JSON保存
    # ------------------------------------------------------------
    try:
        write_json_atomic(
            path=response_path,
            data=normalized_response_data,
        )

    except (
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        return SurveyResponseSaveResult(
            success=False,
            message=(
                "回答JSONの保存に失敗しました："
                f"{exc}"
            ),
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
            response_id=extract_response_id(
                normalized_response_data,
            ),
            response_revision=(
                extract_response_revision(
                    normalized_response_data,
                )
            ),
            response_path=response_path,
            history_path=history_path,
            saved_at=None,
            response_data=None,
        )

    return SurveyResponseSaveResult(
        success=True,
        message="アンケート回答を保存しました．",
        survey_id=normalized_survey_id,
        user_sub=normalized_user_sub,
        response_id=extract_response_id(
            normalized_response_data,
        ),
        response_revision=(
            extract_response_revision(
                normalized_response_data,
            )
        ),
        response_path=response_path,
        history_path=history_path,
        saved_at=normalized_saved_at,
        response_data=normalized_response_data,
    )


# ============================================================
# public API：既存回答の履歴退避
# ============================================================
def archive_existing_response(
    *,
    survey_root: Path,
    survey_id: str,
    user_sub: str,
    source_path: Path | None = None,
    now: datetime | None = None,
) -> SurveyResponseArchiveResult:
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

    archived_at = normalize_save_datetime(
        now,
    )

    resolved_source_path = (
        source_path
        if source_path is not None
        else build_current_response_path(
            responses_root=survey_root,
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
        )
    )

    # ------------------------------------------------------------
    # 現在回答が存在しない場合
    # ------------------------------------------------------------
    if not resolved_source_path.exists():
        return SurveyResponseArchiveResult(
            archived=True,
            message=(
                "既存回答がないため，"
                "履歴退避は行いませんでした．"
            ),
            source_path=resolved_source_path,
            history_path=None,
            archived_at=None,
        )

    if not resolved_source_path.is_file():
        return SurveyResponseArchiveResult(
            archived=False,
            message=(
                "既存回答のパスが"
                "ファイルではありません．"
            ),
            source_path=resolved_source_path,
            history_path=None,
            archived_at=None,
        )

    # ------------------------------------------------------------
    # 履歴保存先
    # ------------------------------------------------------------
    history_directory = (
        build_response_history_directory(
            history_root=survey_root,
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
        )
    )

    history_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    history_path = build_history_response_path(
        history_directory=history_directory,
        archived_at=archived_at,
    )

    # ------------------------------------------------------------
    # 履歴へコピー
    # ------------------------------------------------------------
    try:
        copy_file_atomic(
            source_path=resolved_source_path,
            destination_path=history_path,
        )

    except OSError as exc:
        return SurveyResponseArchiveResult(
            archived=False,
            message=(
                "既存回答の履歴保存に"
                "失敗しました："
                f"{exc}"
            ),
            source_path=resolved_source_path,
            history_path=None,
            archived_at=None,
        )

    return SurveyResponseArchiveResult(
        archived=True,
        message="既存回答を履歴へ保存しました．",
        source_path=resolved_source_path,
        history_path=history_path,
        archived_at=archived_at,
    )


# ============================================================
# public API：履歴回答パス生成
# ============================================================
def build_history_response_path(
    *,
    history_directory: Path,
    archived_at: datetime,
) -> Path:
    normalized_archived_at = (
        normalize_save_datetime(
            archived_at,
        )
    )

    # ------------------------------------------------------------
    # UTC日時をファイル名へ使用する
    #
    # 同一マイクロ秒で重複した場合に備え，
    # UUIDの短縮値も付与する
    # ------------------------------------------------------------
    timestamp_text = (
        normalized_archived_at.strftime(
            "%Y%m%dT%H%M%S_%fZ",
        )
    )

    unique_text = uuid4().hex[
        :8
    ]

    file_name = (
        f"{timestamp_text}"
        f"_{unique_text}.json"
    )

    return history_directory / file_name


# ============================================================
# 保存データの準備
# ============================================================
def prepare_response_data_for_save(
    *,
    response_data: Mapping[str, Any],
    survey_id: str,
    user_sub: str,
    saved_at: datetime,
) -> dict[str, Any]:
    if not isinstance(
        response_data,
        Mapping,
    ):
        raise TypeError(
            "response_dataはMappingで指定してください．"
        )

    normalized_data = clone_json_value(
        response_data,
    )

    if not isinstance(
        normalized_data,
        dict,
    ):
        raise TypeError(
            "response_dataをdictへ変換できません．"
        )

    # ------------------------------------------------------------
    # 識別情報を保存引数へ合わせる
    # ------------------------------------------------------------
    normalized_data[
        "survey_id"
    ] = survey_id

    normalized_data[
        "user_sub"
    ] = user_sub

    # ------------------------------------------------------------
    # 更新日時
    # ------------------------------------------------------------
    normalized_data[
        "updated_at"
    ] = saved_at.isoformat()

    # ------------------------------------------------------------
    # 回答状態
    #
    # response_statusが未指定の場合は，
    # submitted_atの有無から状態を決定する
    # ------------------------------------------------------------
    raw_response_status = normalized_data.get(
        "response_status",
    )

    if raw_response_status is None:
        raw_submitted_at = normalized_data.get(
            "submitted_at",
        )

        if raw_submitted_at is None:
            normalized_response_status = (
                RESPONSE_STATUS_DRAFT
            )

        elif (
            isinstance(
                raw_submitted_at,
                str,
            )
            and not raw_submitted_at.strip()
        ):
            normalized_response_status = (
                RESPONSE_STATUS_DRAFT
            )

        else:
            normalized_response_status = (
                RESPONSE_STATUS_SUBMITTED
            )

    else:
        normalized_response_status = (
            normalize_response_status(
                raw_response_status,
            )
        )

    normalized_data[
        "response_status"
    ] = normalized_response_status


    # ------------------------------------------------------------
    # submitted_atがdatetimeの場合はUTC文字列へ正規化
    # ------------------------------------------------------------
    if "submitted_at" in normalized_data:
        normalized_data[
            "submitted_at"
        ] = normalize_optional_datetime_text(
            normalized_data.get(
                "submitted_at",
            )
        )

    # ------------------------------------------------------------
    # response_revision
    # ------------------------------------------------------------
    normalized_data[
        "response_revision"
    ] = normalize_saved_response_revision(
        normalized_data.get(
            "response_revision",
            1,
        )
    )

    # ------------------------------------------------------------
    # answers
    # ------------------------------------------------------------
    raw_answers = normalized_data.get(
        "answers",
        {},
    )

    if not isinstance(
        raw_answers,
        Mapping,
    ):
        raise TypeError(
            "answersはMappingで指定してください．"
        )

    normalized_data[
        "answers"
    ] = clone_json_value(
        raw_answers,
    )

    # ------------------------------------------------------------
    # JSON保存可能性の最終確認
    # ------------------------------------------------------------
    json.dumps(
        normalized_data,
        ensure_ascii=False,
        allow_nan=False,
    )

    return normalized_data


# ============================================================
# JSONの原子的保存
# ============================================================
def write_json_atomic(
    *,
    path: Path,
    data: Mapping[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ------------------------------------------------------------
    # 同一ディレクトリ内に一時ファイルを作成する
    #
    # os.replace()を同一ファイルシステム上で実行するため
    # ------------------------------------------------------------
    file_descriptor, temporary_name = (
        tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=str(
                path.parent,
            ),
        )
    )

    temporary_path = Path(
        temporary_name,
    )

    try:
        with os.fdopen(
            file_descriptor,
            mode="w",
            encoding="utf-8",
            newline="\n",
        ) as file_object:
            json.dump(
                data,
                file_object,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )

            file_object.write(
                "\n",
            )

            file_object.flush()

            os.fsync(
                file_object.fileno(),
            )

        os.replace(
            temporary_path,
            path,
        )

    except Exception:
        temporary_path.unlink(
            missing_ok=True,
        )

        raise


# ============================================================
# ファイルの原子的コピー
# ============================================================
def copy_file_atomic(
    *,
    source_path: Path,
    destination_path: Path,
) -> None:
    destination_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_descriptor, temporary_name = (
        tempfile.mkstemp(
            prefix=(
                f".{destination_path.name}."
            ),
            suffix=".tmp",
            dir=str(
                destination_path.parent,
            ),
        )
    )

    os.close(
        file_descriptor,
    )

    temporary_path = Path(
        temporary_name,
    )

    try:
        shutil.copy2(
            source_path,
            temporary_path,
        )

        os.replace(
            temporary_path,
            destination_path,
        )

    except Exception:
        temporary_path.unlink(
            missing_ok=True,
        )

        raise


# ============================================================
# UTC保存日時の正規化
# ============================================================
def normalize_save_datetime(
    value: datetime | None,
) -> datetime:
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

    if value.tzinfo is None:
        return value.replace(
            tzinfo=UTC,
        )

    return value.astimezone(
        UTC,
    )


# ============================================================
# 任意日時値の文字列正規化
# ============================================================
def normalize_optional_datetime_text(
    value: Any,
) -> str | None:
    if value is None:
        return None

    if isinstance(
        value,
        datetime,
    ):
        return normalize_save_datetime(
            value,
        ).isoformat()

    if isinstance(
        value,
        str,
    ):
        normalized = value.strip()

        if not normalized:
            return None

        parsed_datetime = parse_response_datetime(
            normalized,
        )

        if parsed_datetime is None:
            raise ValueError(
                (
                    "submitted_atを日時として"
                    "解釈できません："
                    f"{normalized}"
                )
            )

        return normalize_save_datetime(
            parsed_datetime,
        ).isoformat()

    raise TypeError(
        (
            "submitted_atはdatetime型，"
            "日時形式の文字列，または"
            "Noneで指定してください．"
        )
    )


# ============================================================
# response_revisionの正規化
# ============================================================
def normalize_saved_response_revision(
    value: Any,
) -> int:
    if isinstance(
        value,
        bool,
    ):
        raise ValueError(
            (
                "response_revisionは"
                "1以上の整数で指定してください．"
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
                    "response_revisionは"
                    "1以上の整数で指定してください．"
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
                "response_revisionは"
                "1以上の整数で指定してください．"
            )
        )

    return normalized


# ============================================================
# JSON保存可能な値へコピー
# ============================================================
def clone_json_value(
    value: Any,
) -> Any:
    if value is None:
        return None

    if isinstance(
        value,
        (
            str,
            int,
            bool,
        ),
    ):
        return value

    if isinstance(
        value,
        float,
    ):
        if value != value:
            raise ValueError(
                "NaNはJSONへ保存できません．"
            )

        if value in {
            float("inf"),
            float("-inf"),
        }:
            raise ValueError(
                "InfinityはJSONへ保存できません．"
            )

        return value

    if isinstance(
        value,
        datetime,
    ):
        return normalize_save_datetime(
            value,
        ).isoformat()

    if isinstance(
        value,
        Path,
    ):
        return str(
            value,
        )

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
            ] = clone_json_value(
                item,
            )

        return cloned_mapping

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return [
            clone_json_value(
                item,
            )
            for item in value
        ]

    raise TypeError(
        (
            "JSONへ保存できない値です："
            f"{type(value).__name__}"
        )
    )


# ============================================================
# response_id取得
# ============================================================
def extract_response_id(
    response_data: Mapping[str, Any],
) -> str | None:
    raw_response_id = response_data.get(
        "response_id",
    )

    if raw_response_id is None:
        return None

    normalized = str(
        raw_response_id,
    ).strip()

    return normalized or None


# ============================================================
# response_revision取得
# ============================================================
def extract_response_revision(
    response_data: Mapping[str, Any],
) -> int | None:
    raw_revision = response_data.get(
        "response_revision",
    )

    if raw_revision is None:
        return None

    try:
        return normalize_saved_response_revision(
            raw_revision,
        )

    except (
        TypeError,
        ValueError,
    ):
        return None

# ============================================================
# 回答保存モード
# ============================================================
RESPONSE_STATUS_DRAFT = "draft"
RESPONSE_STATUS_SUBMITTED = "submitted"


# ============================================================
# public API：下書き回答の保存
# ============================================================
def save_draft_response(
    *,
    survey_root: Path,
    survey_id: str,
    user_sub: str,
    response_data: Mapping[str, Any],
    now: datetime | None = None,
) -> SurveyResponseSaveResult:
    saved_at = normalize_save_datetime(
        now,
    )

    # ------------------------------------------------------------
    # 既存回答の状態を確認する
    #
    # 下書き保存では，既存回答が提出済みの場合も
    # 回答履歴として退避してから保存する
    # ------------------------------------------------------------
    response_path = build_current_response_path(
        responses_root=survey_root,
        survey_id=survey_id,
        user_sub=user_sub,
    )

    existing_response_data = (
        load_existing_response_data_for_save(
            response_path,
        )
    )

    next_revision = resolve_next_response_revision(
        incoming_response_data=response_data,
        existing_response_data=(
            existing_response_data
        ),
    )

    prepared_data = build_draft_response_data(
        response_data=response_data,
        response_revision=next_revision,
        saved_at=saved_at,
    )

    return save_current_response(
        survey_root=survey_root,
        survey_id=survey_id,
        user_sub=user_sub,
        response_data=prepared_data,
        archive_existing=(
            existing_response_data is not None
        ),
        now=saved_at,
    )


# ============================================================
# public API：提出済み回答の保存
# ============================================================
def save_submitted_response(
    *,
    survey_root: Path,
    survey_id: str,
    user_sub: str,
    response_data: Mapping[str, Any],
    now: datetime | None = None,
    allow_resubmit: bool = True,
) -> SurveyResponseSaveResult:
    submitted_at = normalize_save_datetime(
        now,
    )

    response_path = build_current_response_path(
        responses_root=survey_root,
        survey_id=survey_id,
        user_sub=user_sub,
    )

    existing_response_data = (
        load_existing_response_data_for_save(
            response_path,
        )
    )

    # ------------------------------------------------------------
    # 再提出可否
    # ------------------------------------------------------------
    if (
        existing_response_data is not None
        and is_saved_response_submitted(
            existing_response_data,
        )
        and not allow_resubmit
    ):
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

        return SurveyResponseSaveResult(
            success=False,
            message=(
                "このアンケートはすでに提出済みで，"
                "再回答は許可されていません．"
            ),
            survey_id=normalized_survey_id,
            user_sub=normalized_user_sub,
            response_id=extract_response_id(
                existing_response_data,
            ),
            response_revision=(
                extract_response_revision(
                    existing_response_data,
                )
            ),
            response_path=response_path,
            history_path=None,
            saved_at=None,
            response_data=(
                clone_json_value(
                    existing_response_data,
                )
            ),
        )

    next_revision = resolve_next_response_revision(
        incoming_response_data=response_data,
        existing_response_data=(
            existing_response_data
        ),
    )

    prepared_data = build_submitted_response_data(
        response_data=response_data,
        response_revision=next_revision,
        submitted_at=submitted_at,
    )

    return save_current_response(
        survey_root=survey_root,
        survey_id=survey_id,
        user_sub=user_sub,
        response_data=prepared_data,
        archive_existing=(
            existing_response_data is not None
        ),
        now=submitted_at,
    )


# ============================================================
# 下書き回答データの生成
# ============================================================
def build_draft_response_data(
    *,
    response_data: Mapping[str, Any],
    response_revision: int,
    saved_at: datetime,
) -> dict[str, Any]:
    if not isinstance(
        response_data,
        Mapping,
    ):
        raise TypeError(
            "response_dataはMappingで指定してください．"
        )

    normalized_data = clone_json_value(
        response_data,
    )

    if not isinstance(
        normalized_data,
        dict,
    ):
        raise TypeError(
            "response_dataをdictへ変換できません．"
        )

    normalized_data[
        "response_status"
    ] = RESPONSE_STATUS_DRAFT

    normalized_data[
        "response_revision"
    ] = normalize_saved_response_revision(
        response_revision,
    )

    normalized_data[
        "submitted_at"
    ] = None

    normalized_data[
        "updated_at"
    ] = normalize_save_datetime(
        saved_at,
    ).isoformat()

    return normalized_data


# ============================================================
# 提出済み回答データの生成
# ============================================================
def build_submitted_response_data(
    *,
    response_data: Mapping[str, Any],
    response_revision: int,
    submitted_at: datetime,
) -> dict[str, Any]:
    if not isinstance(
        response_data,
        Mapping,
    ):
        raise TypeError(
            "response_dataはMappingで指定してください．"
        )

    normalized_data = clone_json_value(
        response_data,
    )

    # ------------------------------------------------------------
    # response_id
    #
    # 新規提出時はUUIDを採番する
    # ------------------------------------------------------------
    if not normalized_data.get("response_id"):
        normalized_data["response_id"] = str(
            uuid4()
        )

    if not isinstance(
        normalized_data,
        dict,
    ):
        raise TypeError(
            "response_dataをdictへ変換できません．"
        )

    normalized_submitted_at = (
        normalize_save_datetime(
            submitted_at,
        )
    )

    normalized_data[
        "response_status"
    ] = RESPONSE_STATUS_SUBMITTED

    normalized_data[
        "response_revision"
    ] = normalize_saved_response_revision(
        response_revision,
    )

    normalized_data[
        "submitted_at"
    ] = normalized_submitted_at.isoformat()

    normalized_data[
        "updated_at"
    ] = normalized_submitted_at.isoformat()

    return normalized_data


# ============================================================
# 次の回答リビジョンを決定
# ============================================================
def resolve_next_response_revision(
    *,
    incoming_response_data: Mapping[str, Any],
    existing_response_data: Mapping[str, Any] | None,
) -> int:
    # ------------------------------------------------------------
    # 既存回答がある場合
    #
    # 保存データ側のrevisionに依存せず，
    # 既存回答のrevision + 1を使用する
    # ------------------------------------------------------------
    if existing_response_data is not None:
        existing_revision = (
            extract_response_revision(
                existing_response_data,
            )
        )

        if existing_revision is None:
            existing_revision = 1

        return existing_revision + 1

    # ------------------------------------------------------------
    # 新規回答
    # ------------------------------------------------------------
    incoming_revision = extract_response_revision(
        incoming_response_data,
    )

    if incoming_revision is None:
        return 1

    return normalize_saved_response_revision(
        incoming_revision,
    )


# ============================================================
# 保存済み回答の提出状態判定
# ============================================================
def is_saved_response_submitted(
    response_data: Mapping[str, Any],
) -> bool:
    if not isinstance(
        response_data,
        Mapping,
    ):
        return False

    # ------------------------------------------------------------
    # response_statusを優先する
    # ------------------------------------------------------------
    raw_status = response_data.get(
        "response_status",
    )

    if raw_status is not None:
        normalized_status = str(
            raw_status,
        ).strip().lower()

        if (
            normalized_status
            == RESPONSE_STATUS_SUBMITTED
        ):
            return True

        if (
            normalized_status
            == RESPONSE_STATUS_DRAFT
        ):
            return False

    # ------------------------------------------------------------
    # 旧形式との互換性
    #
    # submitted_atが設定されていれば提出済みとする
    # ------------------------------------------------------------
    submitted_at = response_data.get(
        "submitted_at",
    )

    if submitted_at is None:
        return False

    if isinstance(
        submitted_at,
        datetime,
    ):
        return True

    if isinstance(
        submitted_at,
        str,
    ):
        return bool(
            submitted_at.strip()
        )

    return False


# ============================================================
# 保存済み回答の下書き状態判定
# ============================================================
def is_saved_response_draft(
    response_data: Mapping[str, Any],
) -> bool:
    if not isinstance(
        response_data,
        Mapping,
    ):
        return False

    return not is_saved_response_submitted(
        response_data,
    )


# ============================================================
# 現在回答JSONの保存前読み込み
# ============================================================
def load_existing_response_data_for_save(
    response_path: Path,
) -> dict[str, Any] | None:
    if not response_path.exists():
        return None

    if not response_path.is_file():
        raise ValueError(
            (
                "現在回答の保存先が"
                "ファイルではありません："
                f"{response_path}"
            )
        )

    try:
        with response_path.open(
            mode="r",
            encoding="utf-8",
        ) as file_object:
            loaded_data = json.load(
                file_object,
            )

    except json.JSONDecodeError as exc:
        raise ValueError(
            (
                "既存回答JSONを読み込めません："
                f"{response_path}"
            )
        ) from exc

    except OSError as exc:
        raise OSError(
            (
                "既存回答ファイルの読み込みに"
                "失敗しました："
                f"{response_path}"
            )
        ) from exc

    if not isinstance(
        loaded_data,
        dict,
    ):
        raise ValueError(
            (
                "既存回答JSONのルートは"
                "objectである必要があります："
                f"{response_path}"
            )
        )

    return clone_json_value(
        loaded_data,
    )


# ============================================================
# 保存済み回答のリビジョン取得
# ============================================================
def get_saved_response_revision(
    response_data: Mapping[str, Any] | None,
) -> int:
    if response_data is None:
        return 0

    revision = extract_response_revision(
        response_data,
    )

    if revision is None:
        return 1

    return revision


# ============================================================
# 保存済み回答の提出日時取得
# ============================================================
def get_saved_submitted_at(
    response_data: Mapping[str, Any] | None,
) -> datetime | None:
    if response_data is None:
        return None

    raw_submitted_at = response_data.get(
        "submitted_at",
    )

    if raw_submitted_at is None:
        return None

    if isinstance(
        raw_submitted_at,
        datetime,
    ):
        return normalize_save_datetime(
            raw_submitted_at,
        )

    if isinstance(
        raw_submitted_at,
        str,
    ):
        normalized = raw_submitted_at.strip()

        if not normalized:
            return None

        parsed = parse_response_datetime(
            normalized,
        )

        if parsed is None:
            return None

        return normalize_save_datetime(
            parsed,
        )

    return None


# ============================================================
# 保存前の現在回答をバイト列で取得
# ============================================================
def read_response_file_bytes(
    response_path: Path,
) -> bytes | None:
    if not response_path.exists():
        return None

    if not response_path.is_file():
        raise ValueError(
            (
                "回答保存先がファイルではありません："
                f"{response_path}"
            )
        )

    return response_path.read_bytes()


# ============================================================
# 保存失敗時に現在回答が維持されているか確認
# ============================================================
def verify_current_response_unchanged(
    *,
    response_path: Path,
    previous_file_bytes: bytes | None,
) -> bool:
    # ------------------------------------------------------------
    # 保存前にファイルがなかった場合
    # ------------------------------------------------------------
    if previous_file_bytes is None:
        return not response_path.exists()

    # ------------------------------------------------------------
    # 保存前にファイルがあった場合
    # ------------------------------------------------------------
    if not response_path.exists():
        return False

    if not response_path.is_file():
        return False

    try:
        current_file_bytes = (
            response_path.read_bytes()
        )

    except OSError:
        return False

    return (
        current_file_bytes
        == previous_file_bytes
    )


# ============================================================
# 現在回答を以前の内容へ復旧
# ============================================================
def restore_current_response(
    *,
    response_path: Path,
    previous_file_bytes: bytes | None,
) -> None:
    # ------------------------------------------------------------
    # 保存前にファイルが存在しなかった場合
    #
    # 保存途中で新しいファイルが作成されていれば削除する
    # ------------------------------------------------------------
    if previous_file_bytes is None:
        response_path.unlink(
            missing_ok=True,
        )

        return

    response_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_descriptor, temporary_name = (
        tempfile.mkstemp(
            prefix=f".{response_path.name}.restore.",
            suffix=".tmp",
            dir=str(
                response_path.parent,
            ),
        )
    )

    temporary_path = Path(
        temporary_name,
    )

    try:
        with os.fdopen(
            file_descriptor,
            mode="wb",
        ) as file_object:
            file_object.write(
                previous_file_bytes,
            )

            file_object.flush()

            os.fsync(
                file_object.fileno(),
            )

        os.replace(
            temporary_path,
            response_path,
        )

    except Exception:
        temporary_path.unlink(
            missing_ok=True,
        )

        raise


# ============================================================
# 回答状態の正規化
# ============================================================
def normalize_response_status(
    value: Any,
) -> str:
    if value is None:
        return RESPONSE_STATUS_DRAFT

    normalized = str(
        value,
    ).strip().lower()

    if not normalized:
        return RESPONSE_STATUS_DRAFT

    supported_statuses = {
        RESPONSE_STATUS_DRAFT,
        RESPONSE_STATUS_SUBMITTED,
    }

    if normalized not in supported_statuses:
        raise ValueError(
            (
                "未対応のresponse_statusです："
                f"{normalized}"
            )
        )

    return normalized  