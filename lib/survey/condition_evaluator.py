# -*- coding: utf-8 -*-
# auth_portal_app/lib/survey/condition_evaluator.py
# ============================================================
# 社内アンケート 条件式評価
#
# 機能：
# - show_if条件式の構文を検証する
# - ASTを使用して条件式を安全に評価する
# - 回答内容から表示対象の質問を判定する
# - 実際に表示される質問一覧を生成する
# - 次へ・戻るの移動先を取得する
# - 表示質問に基づく進捗を計算する
#
# 対応する条件式：
# - ==
# - !=
# - and
# - or
# - not
# - in
# - not in
# - is None
# - is not None
#
# 使用しないもの：
# - eval
# - exec
# - 関数呼び出し
# - 属性アクセス
# - 添字アクセス
# - 算術演算
# - lambda
# - 内包表記
#
# 方針：
# - Streamlitには依存しない
# - show_ifがない質問は常に表示する
# - show_if評価時に未回答の質問はNoneとして扱う
# - 戻る先は実際に表示されている質問から決定する
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
import ast
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .models import (
    SurveyDefinition,
    SurveyQuestion,
)


# ============================================================
# 定数
# ============================================================
ALLOWED_COMPARE_OPERATORS = (
    ast.Eq,
    ast.NotEq,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
)

ALLOWED_BOOLEAN_OPERATORS = (
    ast.And,
    ast.Or,
)

ALLOWED_UNARY_OPERATORS = (
    ast.Not,
)

ALLOWED_LITERAL_CONTAINER_NODES = (
    ast.List,
    ast.Tuple,
    ast.Set,
)

RESERVED_NAMES = {
    "True",
    "False",
    "None",
}


# ============================================================
# 検証結果
# ============================================================
@dataclass(frozen=True)
class ConditionValidationIssue:
    # ------------------------------------------------------------
    # severity
    # - error
    # - warning
    # ------------------------------------------------------------
    severity: str
    message: str

    line: int | None = None
    column: int | None = None
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "name": self.name,
        }


@dataclass(frozen=True)
class ConditionValidationResult:
    expression: str

    errors: tuple[ConditionValidationIssue, ...] = ()
    warnings: tuple[ConditionValidationIssue, ...] = ()

    referenced_question_ids: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "expression": self.expression,
            "errors": [
                issue.to_dict()
                for issue in self.errors
            ],
            "warnings": [
                issue.to_dict()
                for issue in self.warnings
            ],
            "referenced_question_ids": list(
                self.referenced_question_ids,
            ),
            "is_valid": self.is_valid,
        }


# ============================================================
# 条件式評価結果
# ============================================================
@dataclass(frozen=True)
class ConditionEvaluationResult:
    expression: str
    value: bool

    error_message: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.error_message is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "expression": self.expression,
            "value": self.value,
            "error_message": self.error_message,
            "succeeded": self.succeeded,
        }


# ============================================================
# 質問進捗
# ============================================================
@dataclass(frozen=True)
class SurveyQuestionProgress:
    # ------------------------------------------------------------
    # current_number
    # - 表示質問内での現在位置
    # - 1始まり
    # - 現在質問が見つからない場合は0
    # ------------------------------------------------------------
    current_number: int
    total_count: int

    current_question_id: str | None = None
    previous_question_id: str | None = None
    next_question_id: str | None = None

    @property
    def is_first(self) -> bool:
        return (
            self.total_count > 0
            and self.current_number == 1
        )

    @property
    def is_last(self) -> bool:
        return (
            self.total_count > 0
            and self.current_number == self.total_count
        )

    @property
    def label(self) -> str:
        if self.total_count <= 0:
            return "0 / 0"

        if self.current_number <= 0:
            return f"0 / {self.total_count}"

        return (
            f"{self.current_number}"
            f" / "
            f"{self.total_count}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_number": self.current_number,
            "total_count": self.total_count,
            "current_question_id": self.current_question_id,
            "previous_question_id": self.previous_question_id,
            "next_question_id": self.next_question_id,
            "is_first": self.is_first,
            "is_last": self.is_last,
            "label": self.label,
        }


# ============================================================
# public API：条件式検証
# ============================================================
def validate_show_if(
    expression: str | None,
    *,
    allowed_question_ids: Iterable[str] | None = None,
) -> ConditionValidationResult:
    # ------------------------------------------------------------
    # 空のshow_ifは有効
    # ------------------------------------------------------------
    normalized_expression = str(
        expression or "",
    ).strip()

    if not normalized_expression:
        return ConditionValidationResult(
            expression="",
        )

    errors: list[ConditionValidationIssue] = []
    warnings: list[ConditionValidationIssue] = []

    # ------------------------------------------------------------
    # Python式として解析
    # ------------------------------------------------------------
    try:
        parsed = ast.parse(
            normalized_expression,
            mode="eval",
        )

    except SyntaxError as exc:
        errors.append(
            ConditionValidationIssue(
                severity="error",
                message=(
                    "show_ifの構文が不正です："
                    f"{exc.msg}"
                ),
                line=exc.lineno,
                column=exc.offset,
            )
        )

        return ConditionValidationResult(
            expression=normalized_expression,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    # ------------------------------------------------------------
    # AST構造を検証
    # ------------------------------------------------------------
    validator = _ConditionAstValidator()

    validator.visit(
        parsed,
    )

    errors.extend(
        validator.errors,
    )

    warnings.extend(
        validator.warnings,
    )

    referenced_ids = tuple(
        sorted(
            validator.referenced_names,
        )
    )

    # ------------------------------------------------------------
    # 質問IDの存在確認
    # ------------------------------------------------------------
    if allowed_question_ids is not None:
        allowed_ids = {
            str(question_id)
            for question_id in allowed_question_ids
        }

        for question_id in referenced_ids:
            if question_id not in allowed_ids:
                errors.append(
                    ConditionValidationIssue(
                        severity="error",
                        message=(
                            "show_ifが存在しない質問IDを"
                            f"参照しています：{question_id}"
                        ),
                        name=question_id,
                    )
                )

    return ConditionValidationResult(
        expression=normalized_expression,
        errors=tuple(errors),
        warnings=tuple(warnings),
        referenced_question_ids=referenced_ids,
    )


# ============================================================
# public API：条件式評価
# ============================================================
def evaluate_show_if(
    expression: str | None,
    answers: Mapping[str, Any],
    *,
    allowed_question_ids: Iterable[str] | None = None,
    raise_on_error: bool = False,
) -> ConditionEvaluationResult:
    # ------------------------------------------------------------
    # 条件指定がない場合は表示
    # ------------------------------------------------------------
    normalized_expression = str(
        expression or "",
    ).strip()

    if not normalized_expression:
        return ConditionEvaluationResult(
            expression="",
            value=True,
        )

    # ------------------------------------------------------------
    # 構文検証
    # ------------------------------------------------------------
    validation = validate_show_if(
        normalized_expression,
        allowed_question_ids=allowed_question_ids,
    )

    if not validation.is_valid:
        error_message = " / ".join(
            issue.message
            for issue in validation.errors
        )

        if raise_on_error:
            raise ValueError(
                error_message,
            )

        return ConditionEvaluationResult(
            expression=normalized_expression,
            value=False,
            error_message=error_message,
        )

    # ------------------------------------------------------------
    # AST評価
    # ------------------------------------------------------------
    try:
        parsed = ast.parse(
            normalized_expression,
            mode="eval",
        )

        raw_value = _evaluate_node(
            parsed.body,
            answers=answers,
        )

        return ConditionEvaluationResult(
            expression=normalized_expression,
            value=bool(raw_value),
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        if raise_on_error:
            raise

        return ConditionEvaluationResult(
            expression=normalized_expression,
            value=False,
            error_message=str(exc),
        )


# ============================================================
# public API：質問表示判定
# ============================================================
def is_question_visible(
    question: SurveyQuestion,
    answers: Mapping[str, Any],
    *,
    allowed_question_ids: Iterable[str] | None = None,
    raise_on_error: bool = False,
) -> bool:
    # ------------------------------------------------------------
    # show_ifがない質問は常に表示
    # ------------------------------------------------------------
    if not question.show_if:
        return True

    result = evaluate_show_if(
        question.show_if,
        answers,
        allowed_question_ids=allowed_question_ids,
        raise_on_error=raise_on_error,
    )

    return result.value


# ============================================================
# public API：表示質問一覧
# ============================================================
def get_visible_questions(
    questions_or_definition: (
        Sequence[SurveyQuestion]
        | SurveyDefinition
    ),
    answers: Mapping[str, Any],
    *,
    raise_on_error: bool = False,
) -> tuple[SurveyQuestion, ...]:
    # ------------------------------------------------------------
    # 質問一覧取得
    # ------------------------------------------------------------
    questions = _resolve_questions(
        questions_or_definition,
    )

    question_ids = tuple(
        question.question_id
        for question in questions
    )

    visible_questions: list[SurveyQuestion] = []

    # ------------------------------------------------------------
    # 定義順に表示判定
    # ------------------------------------------------------------
    for question in questions:
        visible = is_question_visible(
            question,
            answers,
            allowed_question_ids=question_ids,
            raise_on_error=raise_on_error,
        )

        if visible:
            visible_questions.append(
                question,
            )

    return tuple(
        visible_questions,
    )


def get_visible_question_ids(
    questions_or_definition: (
        Sequence[SurveyQuestion]
        | SurveyDefinition
    ),
    answers: Mapping[str, Any],
    *,
    raise_on_error: bool = False,
) -> tuple[str, ...]:
    visible_questions = get_visible_questions(
        questions_or_definition,
        answers,
        raise_on_error=raise_on_error,
    )

    return tuple(
        question.question_id
        for question in visible_questions
    )


# ============================================================
# public API：非表示回答の除去
# ============================================================
def remove_hidden_answers(
    questions_or_definition: (
        Sequence[SurveyQuestion]
        | SurveyDefinition
    ),
    answers: Mapping[str, Any],
    *,
    raise_on_error: bool = False,
) -> dict[str, Any]:
    # ------------------------------------------------------------
    # 現在表示される質問の回答だけを残す
    #
    # 注意：
    # - show_if判定に必要な回答を順番に評価するため，
    #   元のanswersを使って表示質問を判定する
    # - 条件変更により非表示となった質問の回答を削除する
    # ------------------------------------------------------------
    visible_ids = set(
        get_visible_question_ids(
            questions_or_definition,
            answers,
            raise_on_error=raise_on_error,
        )
    )

    return {
        question_id: value
        for question_id, value in answers.items()
        if question_id in visible_ids
    }


# ============================================================
# public API：次の質問
# ============================================================
def get_next_visible_question_id(
    questions_or_definition: (
        Sequence[SurveyQuestion]
        | SurveyDefinition
    ),
    answers: Mapping[str, Any],
    *,
    current_question_id: str,
    raise_on_error: bool = False,
) -> str | None:
    visible_ids = get_visible_question_ids(
        questions_or_definition,
        answers,
        raise_on_error=raise_on_error,
    )

    try:
        current_index = visible_ids.index(
            current_question_id,
        )
    except ValueError:
        return (
            visible_ids[0]
            if visible_ids
            else None
        )

    next_index = current_index + 1

    if next_index >= len(
        visible_ids,
    ):
        return None

    return visible_ids[
        next_index
    ]


# ============================================================
# public API：前の質問
# ============================================================
def get_previous_visible_question_id(
    questions_or_definition: (
        Sequence[SurveyQuestion]
        | SurveyDefinition
    ),
    answers: Mapping[str, Any],
    *,
    current_question_id: str,
    raise_on_error: bool = False,
) -> str | None:
    visible_ids = get_visible_question_ids(
        questions_or_definition,
        answers,
        raise_on_error=raise_on_error,
    )

    try:
        current_index = visible_ids.index(
            current_question_id,
        )
    except ValueError:
        return (
            visible_ids[-1]
            if visible_ids
            else None
        )

    previous_index = current_index - 1

    if previous_index < 0:
        return None

    return visible_ids[
        previous_index
    ]


# ============================================================
# public API：先頭質問
# ============================================================
def get_first_visible_question_id(
    questions_or_definition: (
        Sequence[SurveyQuestion]
        | SurveyDefinition
    ),
    answers: Mapping[str, Any],
    *,
    raise_on_error: bool = False,
) -> str | None:
    visible_ids = get_visible_question_ids(
        questions_or_definition,
        answers,
        raise_on_error=raise_on_error,
    )

    if not visible_ids:
        return None

    return visible_ids[0]


# ============================================================
# public API：最終質問
# ============================================================
def get_last_visible_question_id(
    questions_or_definition: (
        Sequence[SurveyQuestion]
        | SurveyDefinition
    ),
    answers: Mapping[str, Any],
    *,
    raise_on_error: bool = False,
) -> str | None:
    visible_ids = get_visible_question_ids(
        questions_or_definition,
        answers,
        raise_on_error=raise_on_error,
    )

    if not visible_ids:
        return None

    return visible_ids[-1]


# ============================================================
# public API：進捗
# ============================================================
def calculate_question_progress(
    questions_or_definition: (
        Sequence[SurveyQuestion]
        | SurveyDefinition
    ),
    answers: Mapping[str, Any],
    *,
    current_question_id: str | None,
    raise_on_error: bool = False,
) -> SurveyQuestionProgress:
    visible_ids = get_visible_question_ids(
        questions_or_definition,
        answers,
        raise_on_error=raise_on_error,
    )

    total_count = len(
        visible_ids,
    )

    if (
        not current_question_id
        or current_question_id not in visible_ids
    ):
        return SurveyQuestionProgress(
            current_number=0,
            total_count=total_count,
            current_question_id=None,
            previous_question_id=None,
            next_question_id=(
                visible_ids[0]
                if visible_ids
                else None
            ),
        )

    current_index = visible_ids.index(
        current_question_id,
    )

    previous_question_id = (
        visible_ids[current_index - 1]
        if current_index > 0
        else None
    )

    next_question_id = (
        visible_ids[current_index + 1]
        if current_index + 1 < total_count
        else None
    )

    return SurveyQuestionProgress(
        current_number=current_index + 1,
        total_count=total_count,
        current_question_id=current_question_id,
        previous_question_id=previous_question_id,
        next_question_id=next_question_id,
    )


# ============================================================
# public API：現在質問の補正
# ============================================================
def resolve_current_question_id(
    questions_or_definition: (
        Sequence[SurveyQuestion]
        | SurveyDefinition
    ),
    answers: Mapping[str, Any],
    *,
    requested_question_id: str | None,
    fallback: str = "first",
    raise_on_error: bool = False,
) -> str | None:
    # ------------------------------------------------------------
    # 条件変更で現在質問が非表示になった場合に補正する
    #
    # fallback
    # - first：先頭の表示質問
    # - last：最後の表示質問
    # ------------------------------------------------------------
    visible_ids = get_visible_question_ids(
        questions_or_definition,
        answers,
        raise_on_error=raise_on_error,
    )

    if not visible_ids:
        return None

    if (
        requested_question_id
        and requested_question_id in visible_ids
    ):
        return requested_question_id

    if fallback == "last":
        return visible_ids[-1]

    if fallback != "first":
        raise ValueError(
            f"未対応のfallbackです：{fallback}"
        )

    return visible_ids[0]


# ============================================================
# public API：定義内のshow_if一括検証
# ============================================================
def validate_definition_conditions(
    definition: SurveyDefinition,
) -> dict[str, ConditionValidationResult]:
    # ------------------------------------------------------------
    # 質問ごとにshow_ifを検証する
    # ------------------------------------------------------------
    results: dict[
        str,
        ConditionValidationResult,
    ] = {}

    question_ids = tuple(
        question.question_id
        for question in definition.questions
    )

    question_order = {
        question.question_id: index
        for index, question in enumerate(
            definition.questions,
        )
    }

    for current_index, question in enumerate(
        definition.questions,
    ):
        if not question.show_if:
            continue

        result = validate_show_if(
            question.show_if,
            allowed_question_ids=question_ids,
        )

        additional_errors = list(
            result.errors,
        )

        # --------------------------------------------------------
        # 後続質問・自分自身への参照を禁止
        # --------------------------------------------------------
        for referenced_id in (
            result.referenced_question_ids
        ):
            referenced_index = question_order.get(
                referenced_id,
            )

            if referenced_index is None:
                continue

            if referenced_index >= current_index:
                additional_errors.append(
                    ConditionValidationIssue(
                        severity="error",
                        message=(
                            "show_ifは現在の質問より前の"
                            "質問だけを参照できます："
                            f"{referenced_id}"
                        ),
                        name=referenced_id,
                    )
                )

        results[
            question.question_id
        ] = ConditionValidationResult(
            expression=result.expression,
            errors=tuple(additional_errors),
            warnings=result.warnings,
            referenced_question_ids=(
                result.referenced_question_ids
            ),
        )

    return results


# ============================================================
# AST検証
# ============================================================
class _ConditionAstValidator(
    ast.NodeVisitor,
):
    def __init__(self) -> None:
        self.errors: list[
            ConditionValidationIssue
        ] = []

        self.warnings: list[
            ConditionValidationIssue
        ] = []

        self.referenced_names: set[str] = set()

    # ------------------------------------------------------------
    # 式ルート
    # ------------------------------------------------------------
    def visit_Expression(
        self,
        node: ast.Expression,
    ) -> None:
        self.visit(
            node.body,
        )

    # ------------------------------------------------------------
    # 論理演算
    # ------------------------------------------------------------
    def visit_BoolOp(
        self,
        node: ast.BoolOp,
    ) -> None:
        if not isinstance(
            node.op,
            ALLOWED_BOOLEAN_OPERATORS,
        ):
            self._add_error(
                node,
                "使用できない論理演算子です．",
            )
            return

        if len(node.values) < 2:
            self._add_error(
                node,
                "論理演算の値が不足しています．",
            )
            return

        for value in node.values:
            self.visit(
                value,
            )

    # ------------------------------------------------------------
    # not
    # ------------------------------------------------------------
    def visit_UnaryOp(
        self,
        node: ast.UnaryOp,
    ) -> None:
        if not isinstance(
            node.op,
            ALLOWED_UNARY_OPERATORS,
        ):
            self._add_error(
                node,
                "not以外の単項演算子は使用できません．",
            )
            return

        self.visit(
            node.operand,
        )

    # ------------------------------------------------------------
    # 比較
    # ------------------------------------------------------------
    def visit_Compare(
        self,
        node: ast.Compare,
    ) -> None:
        self.visit(
            node.left,
        )

        for operator in node.ops:
            if not isinstance(
                operator,
                ALLOWED_COMPARE_OPERATORS,
            ):
                self._add_error(
                    node,
                    (
                        "使用できない比較演算子が"
                        "含まれています．"
                    ),
                )

        for comparator in node.comparators:
            self.visit(
                comparator,
            )

    # ------------------------------------------------------------
    # 質問ID
    # ------------------------------------------------------------
    def visit_Name(
        self,
        node: ast.Name,
    ) -> None:
        if node.id in RESERVED_NAMES:
            return

        if node.id.startswith(
            "__",
        ):
            self._add_error(
                node,
                (
                    "アンダースコア2文字から始まる名前は"
                    "使用できません．"
                ),
                name=node.id,
            )
            return

        self.referenced_names.add(
            node.id,
        )

    # ------------------------------------------------------------
    # 定数
    # ------------------------------------------------------------
    def visit_Constant(
        self,
        node: ast.Constant,
    ) -> None:
        if not isinstance(
            node.value,
            (
                str,
                int,
                float,
                bool,
                type(None),
            ),
        ):
            self._add_error(
                node,
                "使用できない定数です．",
            )

    # ------------------------------------------------------------
    # リスト
    # ------------------------------------------------------------
    def visit_List(
        self,
        node: ast.List,
    ) -> None:
        for element in node.elts:
            self.visit(
                element,
            )

    # ------------------------------------------------------------
    # タプル
    # ------------------------------------------------------------
    def visit_Tuple(
        self,
        node: ast.Tuple,
    ) -> None:
        for element in node.elts:
            self.visit(
                element,
            )

    # ------------------------------------------------------------
    # 集合
    # ------------------------------------------------------------
    def visit_Set(
        self,
        node: ast.Set,
    ) -> None:
        for element in node.elts:
            self.visit(
                element,
            )

    # ------------------------------------------------------------
    # 以下は明示的に禁止
    # ------------------------------------------------------------
    def visit_Call(
        self,
        node: ast.Call,
    ) -> None:
        self._add_error(
            node,
            "関数呼び出しは使用できません．",
        )

    def visit_Attribute(
        self,
        node: ast.Attribute,
    ) -> None:
        self._add_error(
            node,
            "属性アクセスは使用できません．",
        )

    def visit_Subscript(
        self,
        node: ast.Subscript,
    ) -> None:
        self._add_error(
            node,
            "添字アクセスは使用できません．",
        )

    def visit_BinOp(
        self,
        node: ast.BinOp,
    ) -> None:
        self._add_error(
            node,
            "算術演算は使用できません．",
        )

    def visit_Lambda(
        self,
        node: ast.Lambda,
    ) -> None:
        self._add_error(
            node,
            "lambdaは使用できません．",
        )

    def visit_Dict(
        self,
        node: ast.Dict,
    ) -> None:
        self._add_error(
            node,
            "辞書は使用できません．",
        )

    def visit_ListComp(
        self,
        node: ast.ListComp,
    ) -> None:
        self._add_error(
            node,
            "リスト内包表記は使用できません．",
        )

    def visit_SetComp(
        self,
        node: ast.SetComp,
    ) -> None:
        self._add_error(
            node,
            "集合内包表記は使用できません．",
        )

    def visit_DictComp(
        self,
        node: ast.DictComp,
    ) -> None:
        self._add_error(
            node,
            "辞書内包表記は使用できません．",
        )

    def visit_GeneratorExp(
        self,
        node: ast.GeneratorExp,
    ) -> None:
        self._add_error(
            node,
            "ジェネレーター式は使用できません．",
        )

    def visit_IfExp(
        self,
        node: ast.IfExp,
    ) -> None:
        self._add_error(
            node,
            "条件演算子は使用できません．",
        )

    def visit_NamedExpr(
        self,
        node: ast.NamedExpr,
    ) -> None:
        self._add_error(
            node,
            "代入式は使用できません．",
        )

    # ------------------------------------------------------------
    # 未対応ノード
    # ------------------------------------------------------------
    def generic_visit(
        self,
        node: ast.AST,
    ) -> None:
        allowed_node_types = (
            ast.Expression,
            ast.BoolOp,
            ast.UnaryOp,
            ast.Compare,
            ast.Name,
            ast.Load,
            ast.Constant,
            ast.List,
            ast.Tuple,
            ast.Set,
            ast.And,
            ast.Or,
            ast.Not,
            ast.Eq,
            ast.NotEq,
            ast.In,
            ast.NotIn,
            ast.Is,
            ast.IsNot,
        )

        if not isinstance(
            node,
            allowed_node_types,
        ):
            self._add_error(
                node,
                (
                    "使用できない構文が含まれています："
                    f"{type(node).__name__}"
                ),
            )
            return

        super().generic_visit(
            node,
        )

    # ------------------------------------------------------------
    # エラー追加
    # ------------------------------------------------------------
    def _add_error(
        self,
        node: ast.AST,
        message: str,
        *,
        name: str | None = None,
    ) -> None:
        self.errors.append(
            ConditionValidationIssue(
                severity="error",
                message=message,
                line=getattr(
                    node,
                    "lineno",
                    None,
                ),
                column=_to_one_based_column(
                    getattr(
                        node,
                        "col_offset",
                        None,
                    )
                ),
                name=name,
            )
        )


# ============================================================
# AST評価
# ============================================================
def _evaluate_node(
    node: ast.AST,
    *,
    answers: Mapping[str, Any],
) -> Any:
    # ------------------------------------------------------------
    # 質問ID
    # ------------------------------------------------------------
    if isinstance(
        node,
        ast.Name,
    ):
        return answers.get(
            node.id,
        )

    # ------------------------------------------------------------
    # 定数
    # ------------------------------------------------------------
    if isinstance(
        node,
        ast.Constant,
    ):
        return node.value

    # ------------------------------------------------------------
    # リスト
    # ------------------------------------------------------------
    if isinstance(
        node,
        ast.List,
    ):
        return [
            _evaluate_node(
                element,
                answers=answers,
            )
            for element in node.elts
        ]

    # ------------------------------------------------------------
    # タプル
    # ------------------------------------------------------------
    if isinstance(
        node,
        ast.Tuple,
    ):
        return tuple(
            _evaluate_node(
                element,
                answers=answers,
            )
            for element in node.elts
        )

    # ------------------------------------------------------------
    # 集合
    # ------------------------------------------------------------
    if isinstance(
        node,
        ast.Set,
    ):
        return {
            _evaluate_node(
                element,
                answers=answers,
            )
            for element in node.elts
        }

    # ------------------------------------------------------------
    # and / or
    # ------------------------------------------------------------
    if isinstance(
        node,
        ast.BoolOp,
    ):
        if isinstance(
            node.op,
            ast.And,
        ):
            for value_node in node.values:
                value = _evaluate_node(
                    value_node,
                    answers=answers,
                )

                if not bool(value):
                    return False

            return True

        if isinstance(
            node.op,
            ast.Or,
        ):
            for value_node in node.values:
                value = _evaluate_node(
                    value_node,
                    answers=answers,
                )

                if bool(value):
                    return True

            return False

        raise ValueError(
            "未対応の論理演算子です．"
        )

    # ------------------------------------------------------------
    # not
    # ------------------------------------------------------------
    if isinstance(
        node,
        ast.UnaryOp,
    ):
        if isinstance(
            node.op,
            ast.Not,
        ):
            return not bool(
                _evaluate_node(
                    node.operand,
                    answers=answers,
                )
            )

        raise ValueError(
            "未対応の単項演算子です．"
        )

    # ------------------------------------------------------------
    # 比較
    # ------------------------------------------------------------
    if isinstance(
        node,
        ast.Compare,
    ):
        left_value = _evaluate_node(
            node.left,
            answers=answers,
        )

        for operator, comparator_node in zip(
            node.ops,
            node.comparators,
        ):
            right_value = _evaluate_node(
                comparator_node,
                answers=answers,
            )

            comparison_result = _evaluate_comparison(
                operator,
                left_value,
                right_value,
            )

            if not comparison_result:
                return False

            left_value = right_value

        return True

    raise ValueError(
        (
            "条件式に未対応の構文が含まれています："
            f"{type(node).__name__}"
        )
    )


# ============================================================
# 比較演算
# ============================================================
def _evaluate_comparison(
    operator: ast.cmpop,
    left_value: Any,
    right_value: Any,
) -> bool:
    if isinstance(
        operator,
        ast.Eq,
    ):
        return left_value == right_value

    if isinstance(
        operator,
        ast.NotEq,
    ):
        return left_value != right_value

    if isinstance(
        operator,
        ast.Is,
    ):
        return left_value is right_value

    if isinstance(
        operator,
        ast.IsNot,
    ):
        return left_value is not right_value

    if isinstance(
        operator,
        ast.In,
    ):
        return _safe_contains(
            container=right_value,
            value=left_value,
        )

    if isinstance(
        operator,
        ast.NotIn,
    ):
        return not _safe_contains(
            container=right_value,
            value=left_value,
        )

    raise ValueError(
        "未対応の比較演算子です．"
    )


# ============================================================
# 安全な包含判定
# ============================================================
def _safe_contains(
    *,
    container: Any,
    value: Any,
) -> bool:
    # ------------------------------------------------------------
    # inの右辺として許可する型
    # ------------------------------------------------------------
    if container is None:
        return False

    if isinstance(
        container,
        (
            str,
            list,
            tuple,
            set,
            frozenset,
        ),
    ):
        try:
            return value in container

        except TypeError:
            return False

    raise ValueError(
        (
            "inまたはnot inの右辺は，"
            "文字列・リスト・タプル・集合で"
            "指定してください．"
        )
    )


# ============================================================
# 質問一覧取得
# ============================================================
def _resolve_questions(
    questions_or_definition: (
        Sequence[SurveyQuestion]
        | SurveyDefinition
    ),
) -> tuple[SurveyQuestion, ...]:
    if isinstance(
        questions_or_definition,
        SurveyDefinition,
    ):
        return tuple(
            questions_or_definition.questions,
        )

    return tuple(
        questions_or_definition,
    )


# ============================================================
# 列番号変換
# ============================================================
def _to_one_based_column(
    zero_based_column: int | None,
) -> int | None:
    if zero_based_column is None:
        return None

    return zero_based_column + 1