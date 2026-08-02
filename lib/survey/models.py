# -*- coding: utf-8 -*-
# auth_portal_app/lib/survey/models.py
# ============================================================
# 社内アンケート データモデル
#
# 機能：
# - SurveyTexの解析結果を表すデータクラスを定義する
# - 質問・選択肢・アンケート定義を保持する
# - ユーザー回答と回答履歴を保持する
# - JSON保存用のdict変換を提供する
#
# 方針：
# - Streamlitには依存しない
# - JSONへ保存できる単純な型だけを保持する
# - 可変データはdefault_factoryで初期化する
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from dataclasses import asdict, dataclass, field
from typing import Any


# ============================================================
# 定数
# ============================================================
SUPPORTED_QUESTION_TYPES = {
    "radio",
    "checkbox",
    "select",
    "text",
    "textarea",
    "number",
    "date",
    "rating",
}

SUPPORTED_SURVEY_STATUSES = {
    "draft",
    "scheduled",
    "running",
    "closed",
    "archived",
}


# ============================================================
# 選択肢
# ============================================================
@dataclass(frozen=True)
class SurveyOption:
    # ------------------------------------------------------------
    # 画面表示名
    # ------------------------------------------------------------
    label: str

    # ------------------------------------------------------------
    # 保存値
    # ------------------------------------------------------------
    value: Any

    # ------------------------------------------------------------
    # SurveyTex上の行番号
    # ------------------------------------------------------------
    source_line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> SurveyOption:
        return cls(
            label=str(data.get("label") or ""),
            value=data.get("value"),
            source_line=_to_optional_int(
                data.get("source_line"),
            ),
        )


# ============================================================
# 質問
# ============================================================
@dataclass(frozen=True)
class SurveyQuestion:
    # ------------------------------------------------------------
    # 基本情報
    # ------------------------------------------------------------
    question_id: str
    question_type: str

    # ------------------------------------------------------------
    # 集計用ラベル
    # - Excel・CSVの列見出しに使用する
    # - 同じラベルを複数の質問で使用してよい
    # ------------------------------------------------------------
    label: str

    # ------------------------------------------------------------
    # 回答画面に表示する質問文
    # ------------------------------------------------------------
    text: str

    # ------------------------------------------------------------
    # 回答条件
    # ------------------------------------------------------------
    required: bool = False
    show_if: str | None = None

    # ------------------------------------------------------------
    # 表示設定
    # ------------------------------------------------------------
    help_text: str | None = None
    placeholder: str | None = None

    # ------------------------------------------------------------
    # 回答補助ボタン
    #
    # none_button
    # - 「該当なし」ボタンを表示する
    #
    # skip_button
    # - 「回答しない」ボタンを表示する
    # ------------------------------------------------------------
    none_button: bool = False
    skip_button: bool = False

    # ------------------------------------------------------------
    # 選択肢
    # ------------------------------------------------------------
    options: tuple[SurveyOption, ...] = field(
        default_factory=tuple,
    )

    # ------------------------------------------------------------
    # 入力制約
    # ------------------------------------------------------------
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    max_length: int | None = None

    # ------------------------------------------------------------
    # SurveyTex上の位置
    # ------------------------------------------------------------
    source_line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)

        data["options"] = [
            option.to_dict()
            for option in self.options
        ]

        return data

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> SurveyQuestion:
        raw_options = data.get(
            "options",
        ) or []

        options = tuple(
            SurveyOption.from_dict(
                option,
            )
            for option in raw_options
            if isinstance(
                option,
                dict,
            )
        )

        return cls(
            question_id=str(
                data.get(
                    "question_id",
                )
                or ""
            ),

            question_type=str(
                data.get(
                    "question_type",
                )
                or ""
            ),
            label=str(
                data.get(
                    "label",
                )
                or data.get(
                    "text",
                )
                or ""
            ),
            text=str(
                data.get(
                    "text",
                )
                or ""
            ),

            required=bool(
                data.get(
                    "required",
                    False,
                ),
            ),
            show_if=_to_optional_str(
                data.get(
                    "show_if",
                ),
            ),
            help_text=_to_optional_str(
                data.get(
                    "help_text",
                ),
            ),
            placeholder=_to_optional_str(
                data.get(
                    "placeholder",
                ),
            ),
            none_button=bool(
                data.get(
                    "none_button",
                    False,
                ),
            ),
            skip_button=bool(
                data.get(
                    "skip_button",
                    False,
                ),
            ),
            options=options,
            min_value=_to_optional_float(
                data.get(
                    "min_value",
                ),
            ),
            max_value=_to_optional_float(
                data.get(
                    "max_value",
                ),
            ),
            step=_to_optional_float(
                data.get(
                    "step",
                ),
            ),
            max_length=_to_optional_int(
                data.get(
                    "max_length",
                ),
            ),
            source_line=_to_optional_int(
                data.get(
                    "source_line",
                ),
            ),
        )


# ============================================================
# アンケート定義
# ============================================================
@dataclass(frozen=True)
class SurveyDefinition:
    # ------------------------------------------------------------
    # 基本情報
    # ------------------------------------------------------------
    survey_id: str
    version: int
    title: str

    # ------------------------------------------------------------
    # 説明・完了メッセージ
    # ------------------------------------------------------------
    description: str = ""
    completion_message: str = ""

    # ------------------------------------------------------------
    # 質問
    # ------------------------------------------------------------
    questions: tuple[SurveyQuestion, ...] = field(
        default_factory=tuple,
    )

    # ------------------------------------------------------------
    # 元ファイル情報
    # ------------------------------------------------------------
    source_filename: str = ""
    source_sha256: str = ""
    parsed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["questions"] = [
            question.to_dict()
            for question in self.questions
        ]
        return data

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> SurveyDefinition:
        raw_questions = data.get("questions") or []

        questions = tuple(
            SurveyQuestion.from_dict(question)
            for question in raw_questions
            if isinstance(question, dict)
        )

        return cls(
            survey_id=str(
                data.get("survey_id") or "",
            ),
            version=int(
                data.get("version") or 1,
            ),
            title=str(
                data.get("title") or "",
            ),
            description=str(
                data.get("description") or "",
            ),
            completion_message=str(
                data.get("completion_message") or "",
            ),
            questions=questions,
            source_filename=str(
                data.get("source_filename") or "",
            ),
            source_sha256=str(
                data.get("source_sha256") or "",
            ),
            parsed_at=str(
                data.get("parsed_at") or "",
            ),
        )


# ============================================================
# アンケート管理情報
# ============================================================
@dataclass(frozen=True)
class SurveyStatus:
    survey_id: str
    version: int
    status: str

    start_at: str | None = None
    end_at: str | None = None

    created_at: str = ""
    created_by: str = ""
    updated_at: str = ""
    updated_by: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> SurveyStatus:
        return cls(
            survey_id=str(
                data.get("survey_id") or "",
            ),
            version=int(
                data.get("version") or 1,
            ),
            status=str(
                data.get("status") or "draft",
            ),
            start_at=_to_optional_str(
                data.get("start_at"),
            ),
            end_at=_to_optional_str(
                data.get("end_at"),
            ),
            created_at=str(
                data.get("created_at") or "",
            ),
            created_by=str(
                data.get("created_by") or "",
            ),
            updated_at=str(
                data.get("updated_at") or "",
            ),
            updated_by=str(
                data.get("updated_by") or "",
            ),
        )


# ============================================================
# ユーザー回答
# ============================================================
@dataclass(frozen=True)
class SurveyResponse:
    # ------------------------------------------------------------
    # 識別情報
    # ------------------------------------------------------------
    response_id: str
    survey_id: str
    survey_version: int
    user_sub: str

    # ------------------------------------------------------------
    # 回答内容
    # ------------------------------------------------------------
    answers: dict[str, Any] = field(
        default_factory=dict,
    )

    # ------------------------------------------------------------
    # 送信情報
    # ------------------------------------------------------------
    submitted_at: str = ""
    response_revision: int = 1
    is_active: bool = True

    # ------------------------------------------------------------
    # 定義との対応確認
    # ------------------------------------------------------------
    definition_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> SurveyResponse:
        raw_answers = data.get("answers")

        answers = (
            dict(raw_answers)
            if isinstance(raw_answers, dict)
            else {}
        )

        return cls(
            response_id=str(
                data.get("response_id") or "",
            ),
            survey_id=str(
                data.get("survey_id") or "",
            ),
            survey_version=int(
                data.get("survey_version") or 1,
            ),
            user_sub=str(
                data.get("user_sub") or "",
            ),
            answers=answers,
            submitted_at=str(
                data.get("submitted_at") or "",
            ),
            response_revision=int(
                data.get("response_revision") or 1,
            ),
            is_active=bool(
                data.get("is_active", True),
            ),
            definition_sha256=str(
                data.get("definition_sha256") or "",
            ),
        )


# ============================================================
# 構文チェック結果
# ============================================================
@dataclass(frozen=True)
class SurveyValidationIssue:
    # ------------------------------------------------------------
    # severity
    # - error
    # - warning
    # ------------------------------------------------------------
    severity: str
    message: str

    line: int | None = None
    field_name: str | None = None
    question_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> SurveyValidationIssue:
        return cls(
            severity=str(
                data.get("severity") or "error",
            ),
            message=str(
                data.get("message") or "",
            ),
            line=_to_optional_int(
                data.get("line"),
            ),
            field_name=_to_optional_str(
                data.get("field_name"),
            ),
            question_id=_to_optional_str(
                data.get("question_id"),
            ),
        )


@dataclass(frozen=True)
class SurveyParseResult:
    definition: SurveyDefinition | None = None

    errors: tuple[SurveyValidationIssue, ...] = field(
        default_factory=tuple,
    )
    warnings: tuple[SurveyValidationIssue, ...] = field(
        default_factory=tuple,
    )

    @property
    def is_valid(self) -> bool:
        return (
            self.definition is not None
            and not self.errors
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "definition": (
                self.definition.to_dict()
                if self.definition is not None
                else None
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
        }


# ============================================================
# 内部関数：型変換
# ============================================================
def _to_optional_str(
    value: Any,
) -> str | None:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    return text


def _to_optional_int(
    value: Any,
) -> int | None:
    if value is None or value == "":
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_optional_float(
    value: Any,
) -> float | None:
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None