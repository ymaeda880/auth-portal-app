# -*- coding: utf-8 -*-
# auth_portal_app/lib/survey/db.py
# ============================================================
# 社内アンケート SQLite管理
#
# 機能：
# - アンケート管理DBを初期化する
# - アンケート定義情報を登録・更新する
# - アンケートの状態と実施期間を管理する
# - ユーザー回答の最新状態を登録・更新する
# - 管理画面用の一覧・件数・集計データを取得する
#
# 方針：
# - SurveyTex原本と回答本文の正本はJSONファイルとする
# - SQLiteには検索・一覧・集計に必要な管理情報を保存する
# - 日時はUTCのISO形式で保存する
# - Streamlitには依存しない
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import (
    SUPPORTED_SURVEY_STATUSES,
    SurveyDefinition,
    SurveyResponse,
    SurveyStatus,
)


# ============================================================
# DBスキーマ
# ============================================================
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS surveys (
    survey_id           TEXT NOT NULL,
    version             INTEGER NOT NULL,
    title               TEXT NOT NULL,
    description         TEXT,
    completion_message  TEXT,
    status              TEXT NOT NULL,
    start_at            TEXT,
    end_at              TEXT,
    source_filename     TEXT,
    source_sha256       TEXT,
    parsed_at           TEXT,
    created_at          TEXT NOT NULL,
    created_by          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    updated_by          TEXT NOT NULL,
    is_current          INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (
        survey_id,
        version
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_surveys_current
    ON surveys (is_current)
    WHERE is_current = 1;

CREATE INDEX IF NOT EXISTS idx_surveys_status
    ON surveys (
        status
    );

CREATE INDEX IF NOT EXISTS idx_surveys_start_end
    ON surveys (
        start_at,
        end_at
    );

CREATE INDEX IF NOT EXISTS idx_surveys_updated_at
    ON surveys (
        updated_at
    );

CREATE TABLE IF NOT EXISTS survey_questions (
    survey_id       TEXT NOT NULL,
    version         INTEGER NOT NULL,
    question_order  INTEGER NOT NULL,
    question_id     TEXT NOT NULL,
    question_type   TEXT NOT NULL,
    question_text   TEXT NOT NULL,
    required        INTEGER NOT NULL DEFAULT 0,
    show_if         TEXT,
    help_text       TEXT,
    placeholder     TEXT,
    options_json    TEXT,
    min_value       REAL,
    max_value       REAL,
    step_value      REAL,
    max_length      INTEGER,
    source_line     INTEGER,
    PRIMARY KEY (
        survey_id,
        version,
        question_id
    ),
    FOREIGN KEY (
        survey_id,
        version
    )
    REFERENCES surveys (
        survey_id,
        version
    )
    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_survey_questions_order
    ON survey_questions (
        survey_id,
        version,
        question_order
    );

CREATE TABLE IF NOT EXISTS survey_responses (
    response_id        TEXT PRIMARY KEY,
    survey_id          TEXT NOT NULL,
    survey_version     INTEGER NOT NULL,
    user_sub           TEXT NOT NULL,
    submitted_at       TEXT NOT NULL,
    response_revision  INTEGER NOT NULL DEFAULT 1,
    is_active          INTEGER NOT NULL DEFAULT 1,
    definition_sha256  TEXT,
    answer_count       INTEGER NOT NULL DEFAULT 0,
    response_path      TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS
    idx_survey_responses_one_active
ON survey_responses (
    survey_id,
    user_sub
)
WHERE is_active = 1;

CREATE INDEX IF NOT EXISTS idx_survey_responses_survey
    ON survey_responses (
        survey_id,
        submitted_at
    );

CREATE INDEX IF NOT EXISTS idx_survey_responses_user
    ON survey_responses (
        user_sub,
        submitted_at
    );

CREATE INDEX IF NOT EXISTS idx_survey_responses_active
    ON survey_responses (
        survey_id,
        is_active
    );

CREATE TABLE IF NOT EXISTS survey_response_history (
    history_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    response_id        TEXT NOT NULL,
    survey_id          TEXT NOT NULL,
    survey_version     INTEGER NOT NULL,
    user_sub           TEXT NOT NULL,
    submitted_at       TEXT NOT NULL,
    response_revision  INTEGER NOT NULL,
    definition_sha256  TEXT,
    answer_count       INTEGER NOT NULL DEFAULT 0,
    response_path      TEXT NOT NULL,
    archived_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_response_history_survey_user
    ON survey_response_history (
        survey_id,
        user_sub,
        archived_at
    );
"""


# ============================================================
# DB接続
# ============================================================
def connect_survey_db(
    db_path: Path,
) -> sqlite3.Connection:
    # ------------------------------------------------------------
    # DB接続
    # ------------------------------------------------------------
    db_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    con = sqlite3.connect(
        str(db_path),
    )

    con.row_factory = sqlite3.Row

    con.execute(
        "PRAGMA foreign_keys = ON;"
    )
    con.execute(
        "PRAGMA journal_mode = WAL;"
    )
    con.execute(
        "PRAGMA synchronous = NORMAL;"
    )

    return con


def init_survey_db(
    db_path: Path,
) -> None:
    # ------------------------------------------------------------
    # DB初期化
    # ------------------------------------------------------------
    with connect_survey_db(
        db_path,
    ) as con:
        con.executescript(
            SCHEMA_SQL,
        )
        con.commit()


# ============================================================
# アンケート定義登録
# ============================================================
def upsert_survey_definition(
    db_path: Path,
    *,
    definition: SurveyDefinition,
    status: SurveyStatus,
    make_current: bool,
) -> None:
    # ------------------------------------------------------------
    # 入力検証
    # ------------------------------------------------------------
    _validate_definition_and_status(
        definition=definition,
        status=status,
    )

    with connect_survey_db(
        db_path,
    ) as con:
        # --------------------------------------------------------
        # currentを切り替える場合は既存currentを解除
        # --------------------------------------------------------
        if make_current:
            con.execute(
                """
                UPDATE surveys
                SET
                    is_current = 0
                WHERE
                    is_current = 1
                """
            )

        # --------------------------------------------------------
        # アンケート本体
        # --------------------------------------------------------
        con.execute(
            """
            INSERT INTO surveys (
                survey_id,
                version,
                title,
                description,
                completion_message,
                status,
                start_at,
                end_at,
                source_filename,
                source_sha256,
                parsed_at,
                created_at,
                created_by,
                updated_at,
                updated_by,
                is_current
            )
            VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?
            )
            ON CONFLICT (
                survey_id,
                version
            )
            DO UPDATE SET
                title = excluded.title,
                description = excluded.description,
                completion_message = excluded.completion_message,
                status = excluded.status,
                start_at = excluded.start_at,
                end_at = excluded.end_at,
                source_filename = excluded.source_filename,
                source_sha256 = excluded.source_sha256,
                parsed_at = excluded.parsed_at,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by,
                is_current = excluded.is_current
            """,
            (
                definition.survey_id,
                definition.version,
                definition.title,
                definition.description,
                definition.completion_message,
                status.status,
                status.start_at,
                status.end_at,
                definition.source_filename,
                definition.source_sha256,
                definition.parsed_at,
                status.created_at,
                status.created_by,
                status.updated_at,
                status.updated_by,
                1 if make_current else 0,
            ),
        )

        # --------------------------------------------------------
        # 質問定義を入れ直す
        # --------------------------------------------------------
        con.execute(
            """
            DELETE FROM survey_questions
            WHERE
                survey_id = ?
                AND version = ?
            """,
            (
                definition.survey_id,
                definition.version,
            ),
        )

        for index, question in enumerate(
            definition.questions,
            start=1,
        ):
            options_json = json.dumps(
                [
                    option.to_dict()
                    for option in question.options
                ],
                ensure_ascii=False,
            )

            con.execute(
                """
                INSERT INTO survey_questions (
                    survey_id,
                    version,
                    question_order,
                    question_id,
                    question_type,
                    question_text,
                    required,
                    show_if,
                    help_text,
                    placeholder,
                    options_json,
                    min_value,
                    max_value,
                    step_value,
                    max_length,
                    source_line
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?
                )
                """,
                (
                    definition.survey_id,
                    definition.version,
                    index,
                    question.question_id,
                    question.question_type,
                    question.text,
                    1 if question.required else 0,
                    question.show_if,
                    question.help_text,
                    question.placeholder,
                    options_json,
                    question.min_value,
                    question.max_value,
                    question.step,
                    question.max_length,
                    question.source_line,
                ),
            )

        con.commit()


# ============================================================
# current切り替え
# ============================================================
def set_current_survey(
    db_path: Path,
    *,
    survey_id: str,
    version: int,
) -> None:
    with connect_survey_db(
        db_path,
    ) as con:
        row = con.execute(
            """
            SELECT
                survey_id,
                version
            FROM surveys
            WHERE
                survey_id = ?
                AND version = ?
            """,
            (
                survey_id,
                int(version),
            ),
        ).fetchone()

        if row is None:
            raise ValueError(
                "指定したアンケートがDBに存在しません．"
            )

        con.execute(
            """
            UPDATE surveys
            SET
                is_current = 0
            WHERE
                is_current = 1
            """
        )

        con.execute(
            """
            UPDATE surveys
            SET
                is_current = 1
            WHERE
                survey_id = ?
                AND version = ?
            """,
            (
                survey_id,
                int(version),
            ),
        )

        con.commit()


def clear_current_survey_db(
    db_path: Path,
) -> None:
    with connect_survey_db(
        db_path,
    ) as con:
        con.execute(
            """
            UPDATE surveys
            SET
                is_current = 0
            WHERE
                is_current = 1
            """
        )
        con.commit()


# ============================================================
# アンケート状態更新
# ============================================================
def update_survey_status(
    db_path: Path,
    *,
    survey_id: str,
    version: int,
    status: str,
    start_at: str | None,
    end_at: str | None,
    updated_at: str,
    updated_by: str,
) -> None:
    if status not in SUPPORTED_SURVEY_STATUSES:
        raise ValueError(
            f"未対応のアンケート状態です：{status}"
        )

    with connect_survey_db(
        db_path,
    ) as con:
        cur = con.execute(
            """
            UPDATE surveys
            SET
                status = ?,
                start_at = ?,
                end_at = ?,
                updated_at = ?,
                updated_by = ?
            WHERE
                survey_id = ?
                AND version = ?
            """,
            (
                status,
                start_at,
                end_at,
                updated_at,
                updated_by,
                survey_id,
                int(version),
            ),
        )

        if cur.rowcount <= 0:
            raise ValueError(
                "更新対象のアンケートが見つかりません．"
            )

        con.commit()


# ============================================================
# アンケート取得
# ============================================================
def get_survey_record(
    db_path: Path,
    *,
    survey_id: str,
    version: int,
) -> dict[str, Any] | None:
    with connect_survey_db(
        db_path,
    ) as con:
        row = con.execute(
            """
            SELECT
                *
            FROM surveys
            WHERE
                survey_id = ?
                AND version = ?
            """,
            (
                survey_id,
                int(version),
            ),
        ).fetchone()

    return (
        dict(row)
        if row is not None
        else None
    )


def get_current_survey_record(
    db_path: Path,
) -> dict[str, Any] | None:
    with connect_survey_db(
        db_path,
    ) as con:
        row = con.execute(
            """
            SELECT
                *
            FROM surveys
            WHERE
                is_current = 1
            LIMIT 1
            """
        ).fetchone()

    return (
        dict(row)
        if row is not None
        else None
    )


def list_survey_records(
    db_path: Path,
    *,
    statuses: list[str] | None = None,
) -> list[dict[str, Any]]:
    where_sql = ""
    params: list[Any] = []

    if statuses:
        invalid = [
            status
            for status in statuses
            if status not in SUPPORTED_SURVEY_STATUSES
        ]

        if invalid:
            raise ValueError(
                "未対応のアンケート状態が含まれています："
                + ", ".join(invalid)
            )

        placeholders = ", ".join(
            "?"
            for _ in statuses
        )

        where_sql = (
            f"WHERE status IN ({placeholders})"
        )
        params.extend(
            statuses,
        )

    with connect_survey_db(
        db_path,
    ) as con:
        rows = con.execute(
            f"""
            SELECT
                *
            FROM surveys
            {where_sql}
            ORDER BY
                updated_at DESC,
                survey_id DESC,
                version DESC
            """,
            params,
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# 質問一覧取得
# ============================================================
def list_survey_question_records(
    db_path: Path,
    *,
    survey_id: str,
    version: int,
) -> list[dict[str, Any]]:
    with connect_survey_db(
        db_path,
    ) as con:
        rows = con.execute(
            """
            SELECT
                *
            FROM survey_questions
            WHERE
                survey_id = ?
                AND version = ?
            ORDER BY
                question_order
            """,
            (
                survey_id,
                int(version),
            ),
        ).fetchall()

    results: list[dict[str, Any]] = []

    for row in rows:
        item = dict(row)

        raw_options = item.get(
            "options_json",
        )

        try:
            item["options"] = (
                json.loads(raw_options)
                if raw_options
                else []
            )
        except json.JSONDecodeError:
            item["options"] = []

        results.append(
            item,
        )

    return results


# ============================================================
# 回答登録
# ============================================================
def upsert_active_response(
    db_path: Path,
    *,
    response: SurveyResponse,
    response_path: Path,
    updated_at: str,
) -> None:
    # ------------------------------------------------------------
    # 有効回答の登録・更新
    # ------------------------------------------------------------
    answer_count = len(
        response.answers,
    )

    with connect_survey_db(
        db_path,
    ) as con:
        existing = con.execute(
            """
            SELECT
                *
            FROM survey_responses
            WHERE
                survey_id = ?
                AND user_sub = ?
                AND is_active = 1
            LIMIT 1
            """,
            (
                response.survey_id,
                response.user_sub,
            ),
        ).fetchone()

        if existing is not None:
            # ----------------------------------------------------
            # 既存回答を履歴テーブルへ退避
            # ----------------------------------------------------
            con.execute(
                """
                INSERT INTO survey_response_history (
                    response_id,
                    survey_id,
                    survey_version,
                    user_sub,
                    submitted_at,
                    response_revision,
                    definition_sha256,
                    answer_count,
                    response_path,
                    archived_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?
                )
                """,
                (
                    existing["response_id"],
                    existing["survey_id"],
                    existing["survey_version"],
                    existing["user_sub"],
                    existing["submitted_at"],
                    existing["response_revision"],
                    existing["definition_sha256"],
                    existing["answer_count"],
                    existing["response_path"],
                    updated_at,
                ),
            )

            # ----------------------------------------------------
            # 既存回答を無効化
            # ----------------------------------------------------
            con.execute(
                """
                UPDATE survey_responses
                SET
                    is_active = 0,
                    updated_at = ?
                WHERE
                    response_id = ?
                """,
                (
                    updated_at,
                    existing["response_id"],
                ),
            )

        # --------------------------------------------------------
        # 新しい有効回答を登録
        # --------------------------------------------------------
        con.execute(
            """
            INSERT INTO survey_responses (
                response_id,
                survey_id,
                survey_version,
                user_sub,
                submitted_at,
                response_revision,
                is_active,
                definition_sha256,
                answer_count,
                response_path,
                updated_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?,
                1, ?, ?, ?, ?
            )
            """,
            (
                response.response_id,
                response.survey_id,
                response.survey_version,
                response.user_sub,
                response.submitted_at,
                response.response_revision,
                response.definition_sha256,
                answer_count,
                str(response_path),
                updated_at,
            ),
        )

        con.commit()


# ============================================================
# ユーザー回答取得
# ============================================================
def get_active_response_record(
    db_path: Path,
    *,
    survey_id: str,
    user_sub: str,
) -> dict[str, Any] | None:
    with connect_survey_db(
        db_path,
    ) as con:
        row = con.execute(
            """
            SELECT
                *
            FROM survey_responses
            WHERE
                survey_id = ?
                AND user_sub = ?
                AND is_active = 1
            LIMIT 1
            """,
            (
                survey_id,
                user_sub,
            ),
        ).fetchone()

    return (
        dict(row)
        if row is not None
        else None
    )


def list_active_response_records(
    db_path: Path,
    *,
    survey_id: str,
) -> list[dict[str, Any]]:
    with connect_survey_db(
        db_path,
    ) as con:
        rows = con.execute(
            """
            SELECT
                *
            FROM survey_responses
            WHERE
                survey_id = ?
                AND is_active = 1
            ORDER BY
                submitted_at DESC,
                user_sub ASC
            """,
            (
                survey_id,
            ),
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


def list_response_history_records(
    db_path: Path,
    *,
    survey_id: str,
    user_sub: str | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = [
        survey_id,
    ]

    user_where = ""

    if user_sub:
        user_where = (
            "AND user_sub = ?"
        )
        params.append(
            user_sub,
        )

    with connect_survey_db(
        db_path,
    ) as con:
        rows = con.execute(
            f"""
            SELECT
                *
            FROM survey_response_history
            WHERE
                survey_id = ?
                {user_where}
            ORDER BY
                archived_at DESC,
                user_sub ASC
            """,
            params,
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# 回答件数
# ============================================================
def count_active_responses(
    db_path: Path,
    *,
    survey_id: str,
) -> int:
    with connect_survey_db(
        db_path,
    ) as con:
        row = con.execute(
            """
            SELECT
                COUNT(*) AS cnt
            FROM survey_responses
            WHERE
                survey_id = ?
                AND is_active = 1
            """,
            (
                survey_id,
            ),
        ).fetchone()

    return int(
        row["cnt"]
        if row is not None
        else 0
    )


def count_response_history(
    db_path: Path,
    *,
    survey_id: str,
) -> int:
    with connect_survey_db(
        db_path,
    ) as con:
        row = con.execute(
            """
            SELECT
                COUNT(*) AS cnt
            FROM survey_response_history
            WHERE
                survey_id = ?
            """,
            (
                survey_id,
            ),
        ).fetchone()

    return int(
        row["cnt"]
        if row is not None
        else 0
    )


# ============================================================
# 管理画面用サマリー
# ============================================================
def get_survey_summary_record(
    db_path: Path,
    *,
    survey_id: str,
    version: int,
) -> dict[str, Any] | None:
    with connect_survey_db(
        db_path,
    ) as con:
        row = con.execute(
            """
            SELECT
                s.survey_id,
                s.version,
                s.title,
                s.status,
                s.start_at,
                s.end_at,
                s.is_current,
                s.created_at,
                s.updated_at,
                COUNT(
                    CASE
                        WHEN r.is_active = 1
                        THEN 1
                    END
                ) AS active_response_count,
                MIN(
                    CASE
                        WHEN r.is_active = 1
                        THEN r.submitted_at
                    END
                ) AS first_response_at,
                MAX(
                    CASE
                        WHEN r.is_active = 1
                        THEN r.submitted_at
                    END
                ) AS last_response_at
            FROM surveys AS s
            LEFT JOIN survey_responses AS r
                ON r.survey_id = s.survey_id
            WHERE
                s.survey_id = ?
                AND s.version = ?
            GROUP BY
                s.survey_id,
                s.version
            """,
            (
                survey_id,
                int(version),
            ),
        ).fetchone()

    return (
        dict(row)
        if row is not None
        else None
    )


def list_survey_summary_records(
    db_path: Path,
) -> list[dict[str, Any]]:
    with connect_survey_db(
        db_path,
    ) as con:
        rows = con.execute(
            """
            SELECT
                s.survey_id,
                s.version,
                s.title,
                s.status,
                s.start_at,
                s.end_at,
                s.is_current,
                s.created_at,
                s.updated_at,
                COUNT(
                    CASE
                        WHEN r.is_active = 1
                        THEN 1
                    END
                ) AS active_response_count,
                MIN(
                    CASE
                        WHEN r.is_active = 1
                        THEN r.submitted_at
                    END
                ) AS first_response_at,
                MAX(
                    CASE
                        WHEN r.is_active = 1
                        THEN r.submitted_at
                    END
                ) AS last_response_at
            FROM surveys AS s
            LEFT JOIN survey_responses AS r
                ON r.survey_id = s.survey_id
            GROUP BY
                s.survey_id,
                s.version
            ORDER BY
                s.is_current DESC,
                s.updated_at DESC,
                s.survey_id DESC,
                s.version DESC
            """
        ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# アンケート削除
# ============================================================
def delete_survey_definition_record(
    db_path: Path,
    *,
    survey_id: str,
    version: int,
) -> None:
    # ------------------------------------------------------------
    # 有効回答がある場合は削除しない
    # ------------------------------------------------------------
    with connect_survey_db(
        db_path,
    ) as con:
        response_row = con.execute(
            """
            SELECT
                COUNT(*) AS cnt
            FROM survey_responses
            WHERE
                survey_id = ?
            """,
            (
                survey_id,
            ),
        ).fetchone()

        response_count = int(
            response_row["cnt"]
            if response_row is not None
            else 0
        )

        if response_count > 0:
            raise ValueError(
                "回答データが存在するアンケートは削除できません．"
            )

        cur = con.execute(
            """
            DELETE FROM surveys
            WHERE
                survey_id = ?
                AND version = ?
            """,
            (
                survey_id,
                int(version),
            ),
        )

        if cur.rowcount <= 0:
            raise ValueError(
                "削除対象のアンケートが見つかりません．"
            )

        con.commit()


# ============================================================
# アンケート完全削除
# ============================================================
def delete_survey_completely_from_db(
    db_path: Path,
    *,
    survey_id: str,
) -> None:
    # ------------------------------------------------------------
    # survey_idの確認
    # ------------------------------------------------------------
    normalized_survey_id = str(
        survey_id or ""
    ).strip()

    if not normalized_survey_id:
        raise ValueError(
            "survey_idが空です．"
        )

    with connect_survey_db(
        db_path,
    ) as con:
        # --------------------------------------------------------
        # 対象アンケート取得
        # --------------------------------------------------------
        rows = con.execute(
            """
            SELECT
                survey_id,
                version,
                status,
                is_current
            FROM surveys
            WHERE
                survey_id = ?
            """,
            (
                normalized_survey_id,
            ),
        ).fetchall()

        if not rows:
            raise ValueError(
                "削除対象のアンケートが見つかりません．"
            )

        # --------------------------------------------------------
        # 終了またはアーカイブ済みだけ削除可能
        # --------------------------------------------------------
        invalid_rows = [
            row
            for row in rows
            if str(
                row["status"] or ""
            )
            not in {
                "closed",
                "archived",
            }
        ]

        if invalid_rows:
            raise ValueError(
                "終了またはアーカイブ済みではない"
                "アンケートは削除できません．"
            )

        try:
            # ----------------------------------------------------
            # 回答履歴DB
            # ----------------------------------------------------
            con.execute(
                """
                DELETE FROM survey_response_history
                WHERE
                    survey_id = ?
                """,
                (
                    normalized_survey_id,
                ),
            )

            # ----------------------------------------------------
            # 現在回答DB
            # ----------------------------------------------------
            con.execute(
                """
                DELETE FROM survey_responses
                WHERE
                    survey_id = ?
                """,
                (
                    normalized_survey_id,
                ),
            )

            # ----------------------------------------------------
            # 質問定義DB
            # ----------------------------------------------------
            con.execute(
                """
                DELETE FROM survey_questions
                WHERE
                    survey_id = ?
                """,
                (
                    normalized_survey_id,
                ),
            )

            # ----------------------------------------------------
            # アンケート定義DB
            # ----------------------------------------------------
            cur = con.execute(
                """
                DELETE FROM surveys
                WHERE
                    survey_id = ?
                """,
                (
                    normalized_survey_id,
                ),
            )

            if cur.rowcount <= 0:
                raise ValueError(
                    "削除対象のアンケートが見つかりません．"
                )

            con.commit()

        except Exception:
            con.rollback()
            raise


# ============================================================
# 内部関数：定義と状態の整合性確認
# ============================================================
def _validate_definition_and_status(
    *,
    definition: SurveyDefinition,
    status: SurveyStatus,
) -> None:
    if not definition.survey_id:
        raise ValueError(
            "survey_idが空です．"
        )

    if definition.version < 1:
        raise ValueError(
            "versionは1以上で指定してください．"
        )

    if not definition.title:
        raise ValueError(
            "titleが空です．"
        )

    if status.survey_id != definition.survey_id:
        raise ValueError(
            "definitionとstatusのsurvey_idが一致しません．"
        )

    if status.version != definition.version:
        raise ValueError(
            "definitionとstatusのversionが一致しません．"
        )

    if status.status not in SUPPORTED_SURVEY_STATUSES:
        raise ValueError(
            f"未対応のアンケート状態です：{status.status}"
        )

    if not status.created_at:
        raise ValueError(
            "created_atが空です．"
        )

    if not status.created_by:
        raise ValueError(
            "created_byが空です．"
        )

    if not status.updated_at:
        raise ValueError(
            "updated_atが空です．"
        )

    if not status.updated_by:
        raise ValueError(
            "updated_byが空です．"
        )