# -*- coding: utf-8 -*-
# auth_portal_app/lib/survey/svtex_parser.py
# ============================================================
# SurveyTex パーサー
#
# 機能：
# - SurveyTex（.svtex）の文字列を解析する
# - アンケート基本情報を読み取る
# - \begin{形式,...}～\end{形式} の質問ブロックを読み取る
# - label属性を集計ラベルとして読み取る
# - \question{...} を質問文として読み取る
# - \options{...} を選択肢として読み取る
# - SurveyDefinitionを生成する
# - 構文エラーと警告を行番号付きで返す
#
# 対応命令：
# - \id{...}
# - \version{...}
# - \title{...}
# - \description{...}
# - \completion_message{...}
# - \begin{radio,...}
# - \begin{checkbox,...}
# - \begin{select,...}
# - \begin{text,...}
# - \begin{textarea,...}
# - \begin{number,...}
# - \begin{date,...}
# - \begin{rating,...}
# - \label{...}
# - \options{...}
# - \end{...}
#
# 方針：
# - Streamlitには依存しない
# - 任意のPythonコードは実行しない
# - show_ifは文字列として保持する
# - UTF-8 BOMは除去する
# - id省略時はファイル名から自動生成する
# - version省略時は1とする
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
import ast
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import (
    SUPPORTED_QUESTION_TYPES,
    SurveyDefinition,
    SurveyOption,
    SurveyParseResult,
    SurveyQuestion,
    SurveyValidationIssue,
)


# ============================================================
# 定数
# ============================================================
ID_PATTERN = re.compile(
    r"^[A-Za-z][A-Za-z0-9_-]*$"
)

COMMAND_NAME_PATTERN = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*"
)

METADATA_COMMANDS = {
    "id",
    "version",
    "title",
    "description",
    "completion_message",
}

SUPPORTED_COMMANDS = (
    METADATA_COMMANDS
    | {
        "begin",
        "question",
        "options",
        "end",
    }
)

CHOICE_QUESTION_TYPES = {
    "radio",
    "checkbox",
    "select",
}

BEGIN_ATTRIBUTE_NAMES = {
    "id",
    "label",
    "required",
    "show_if",
    "help",
    "placeholder",
    "min",
    "max",
    "step",
    "max_length",
    "none_button",
    "skip_button",
}


# ============================================================
# 内部モデル
# ============================================================
@dataclass(frozen=True)
class ParsedCommand:
    name: str
    body: str
    start_line: int
    end_line: int


@dataclass
class MutableQuestionBlock:
    question_type: str
    attributes: dict[str, Any]
    start_line: int

    question: str = ""
    question_line: int | None = None

    options: list[SurveyOption] | None = None
    options_line: int | None = None


# ============================================================
# public API
# ============================================================
def parse_svtex(
    svtex_text: str,
    *,
    source_filename: str = "",
) -> SurveyParseResult:
    normalized_text = _normalize_svtex_text(
        svtex_text,
    )

    errors: list[SurveyValidationIssue] = []
    warnings: list[SurveyValidationIssue] = []

    if not normalized_text.strip():
        return SurveyParseResult(
            definition=None,
            errors=(
                _error(
                    "SurveyTexファイルが空です．",
                    line=1,
                ),
            ),
            warnings=(),
        )

    commands, tokenize_errors = _parse_commands(
        normalized_text,
    )

    errors.extend(
        tokenize_errors,
    )

    if errors:
        return SurveyParseResult(
            definition=None,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    metadata: dict[str, str] = {}
    metadata_lines: dict[str, int] = {}
    questions: list[SurveyQuestion] = []
    question_ids: set[str] = set()
    current_block: MutableQuestionBlock | None = None

    for command in commands:
        if command.name not in SUPPORTED_COMMANDS:
            errors.append(
                _error(
                    f"未対応の命令です：\\{command.name}",
                    line=command.start_line,
                )
            )
            continue

        if command.name in METADATA_COMMANDS:
            if current_block is not None:
                errors.append(
                    _error(
                        (
                            f"\\{command.name} は質問ブロックの"
                            "外側に記述してください．"
                        ),
                        line=command.start_line,
                    )
                )
                continue

            if command.name in metadata:
                errors.append(
                    _error(
                        (
                            f"\\{command.name} が重複しています．"
                            f"最初の定義は"
                            f"{metadata_lines[command.name]}行目です．"
                        ),
                        line=command.start_line,
                    )
                )
                continue

            metadata[command.name] = _normalize_multiline_body(
                command.body,
            )
            metadata_lines[command.name] = command.start_line
            continue

        if command.name == "begin":
            if current_block is not None:
                errors.append(
                    _error(
                        "質問ブロックの途中で新しい\\beginが開始されています．",
                        line=command.start_line,
                    )
                )
                continue

            question_type, attributes = _parse_begin_body(
                command.body,
                line=command.start_line,
                errors=errors,
            )

            if question_type is None:
                continue

            current_block = MutableQuestionBlock(
                question_type=question_type,
                attributes=attributes,
                start_line=command.start_line,
            )
            continue

        if command.name == "question":
            if current_block is None:
                errors.append(
                    _error(
                        "\\questionの前に\\beginがありません．",
                        line=command.start_line,
                    )
                )
                continue

            if current_block.question:
                errors.append(
                    _error(
                        "1つの質問に\\questionを複数指定できません．",
                        line=command.start_line,
                        question_id=_block_question_id(
                            current_block,
                        ),
                    )
                )
                continue

            current_block.question = _normalize_multiline_body(
                command.body,
            )

            current_block.question_line = command.start_line

            continue



        if command.name == "options":
            if current_block is None:
                errors.append(
                    _error(
                        "\\optionsの前に\\beginがありません．",
                        line=command.start_line,
                    )
                )
                continue

            if current_block.options is not None:
                errors.append(
                    _error(
                        "1つの質問に\\optionsを複数指定できません．",
                        line=command.start_line,
                        question_id=_block_question_id(
                            current_block,
                        ),
                    )
                )
                continue

            current_block.options = _parse_option_lines(
                command.body,
            )
            current_block.options_line = command.start_line
            continue

        if command.name == "end":
            if current_block is None:
                errors.append(
                    _error(
                        "\\endの前に\\beginがありません．",
                        line=command.start_line,
                    )
                )
                continue

            end_type = command.body.strip().lower()

            if end_type != current_block.question_type:
                errors.append(
                    _error(
                        (
                            "\\beginと\\endの質問形式が一致しません："
                            f"{current_block.question_type} / {end_type}"
                        ),
                        line=command.start_line,
                        question_id=_block_question_id(
                            current_block,
                        ),
                    )
                )
                current_block = None
                continue

            question = _build_question(
                current_block,
                errors=errors,
                warnings=warnings,
            )

            if question is not None:
                if question.question_id in question_ids:
                    errors.append(
                        _error(
                            (
                                "質問IDが重複しています："
                                f"{question.question_id}"
                            ),
                            line=current_block.start_line,
                            field_name="id",
                            question_id=question.question_id,
                        )
                    )
                else:
                    question_ids.add(
                        question.question_id,
                    )
                    questions.append(
                        question,
                    )

            current_block = None

    if current_block is not None:
        errors.append(
            _error(
                (
                    "\\beginに対応する\\endがありません："
                    f"{current_block.question_type}"
                ),
                line=current_block.start_line,
                question_id=_block_question_id(
                    current_block,
                ),
            )
        )

    title = str(
        metadata.get("title") or "",
    ).strip()

    if not title:
        errors.append(
            _error(
                "\\titleが指定されていません．",
                line=1,
                field_name="title",
            )
        )

    if not questions:
        errors.append(
            _error(
                "質問が1件も定義されていません．",
                line=1,
            )
        )

    survey_id = str(
        metadata.get("id") or "",
    ).strip()

    if not survey_id:
        survey_id = _build_default_survey_id(
            source_filename=source_filename,
            title=title,
        )

    if not ID_PATTERN.fullmatch(
        survey_id,
    ):
        errors.append(
            _error(
                (
                    "アンケートIDは英字で始まり，"
                    "英数字・ハイフン・アンダースコアだけで"
                    "指定してください："
                    f"{survey_id}"
                ),
                line=metadata_lines.get(
                    "id",
                    1,
                ),
                field_name="id",
            )
        )

    version = _parse_version(
        metadata.get("version"),
        line=metadata_lines.get(
            "version",
            1,
        ),
        errors=errors,
    )

    if errors:
        return SurveyParseResult(
            definition=None,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    definition = SurveyDefinition(
        survey_id=survey_id,
        version=version,
        title=title,
        description=str(
            metadata.get("description") or "",
        ).strip(),
        completion_message=str(
            metadata.get("completion_message") or "",
        ).strip(),
        questions=tuple(
            questions,
        ),
        source_filename=source_filename,
        source_sha256=_calculate_sha256(
            normalized_text,
        ),
        parsed_at=_now_utc_iso(),
    )

    return SurveyParseResult(
        definition=definition,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


# ============================================================
# 入力正規化
# ============================================================
def _normalize_svtex_text(
    text: str,
) -> str:
    normalized = str(
        text or "",
    ).lstrip(
        "\ufeff",
    )

    normalized = normalized.replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    )

    return _remove_comments(
        normalized,
    )


def _remove_comments(
    text: str,
) -> str:
    output_lines: list[str] = []

    for line in text.splitlines(
        keepends=True,
    ):
        quote: str | None = None
        escaped = False
        comment_index: int | None = None

        for index, char in enumerate(
            line,
        ):
            if escaped:
                escaped = False
                continue

            if char == "\\":
                escaped = True
                continue

            if quote is not None:
                if char == quote:
                    quote = None
                continue

            if char in {
                '"',
                "'",
            }:
                quote = char
                continue

            if char == "%":
                comment_index = index
                break

        if comment_index is None:
            output_lines.append(
                line,
            )
            continue

        line_ending = (
            "\n"
            if line.endswith("\n")
            else ""
        )

        output_lines.append(
            line[:comment_index]
            + line_ending
        )

    return "".join(
        output_lines,
    )


# ============================================================
# 命令解析
# ============================================================
def _parse_commands(
    text: str,
) -> tuple[
    list[ParsedCommand],
    list[SurveyValidationIssue],
]:
    commands: list[ParsedCommand] = []
    errors: list[SurveyValidationIssue] = []
    index = 0

    while index < len(text):
        slash_index = text.find(
            "\\",
            index,
        )

        if slash_index < 0:
            break

        name_match = COMMAND_NAME_PATTERN.match(
            text,
            slash_index + 1,
        )

        if name_match is None:
            index = slash_index + 1
            continue

        command_name = name_match.group(
            0,
        )

        cursor = name_match.end()

        while (
            cursor < len(text)
            and text[cursor].isspace()
        ):
            cursor += 1

        if (
            cursor >= len(text)
            or text[cursor] != "{"
        ):
            errors.append(
                _error(
                    (
                        f"\\{command_name} の直後に"
                        "{...}が必要です．"
                    ),
                    line=_line_number(
                        text,
                        slash_index,
                    ),
                )
            )
            index = name_match.end()
            continue

        body, closing_index = _read_braced_body(
            text,
            opening_index=cursor,
        )

        if closing_index is None:
            errors.append(
                _error(
                    (
                        f"\\{command_name} の"
                        "閉じ波括弧がありません．"
                    ),
                    line=_line_number(
                        text,
                        slash_index,
                    ),
                )
            )
            break

        commands.append(
            ParsedCommand(
                name=command_name,
                body=body,
                start_line=_line_number(
                    text,
                    slash_index,
                ),
                end_line=_line_number(
                    text,
                    closing_index,
                ),
            )
        )

        index = closing_index + 1

    return (
        commands,
        errors,
    )


def _read_braced_body(
    text: str,
    *,
    opening_index: int,
) -> tuple[str, int | None]:
    depth = 0
    quote: str | None = None
    escaped = False

    for index in range(
        opening_index,
        len(text),
    ):
        char = text[index]

        if escaped:
            escaped = False
            continue

        if char == "\\":
            escaped = True
            continue

        if quote is not None:
            if char == quote:
                quote = None
            continue

        if char in {
            '"',
            "'",
        }:
            quote = char
            continue

        if char == "{":
            depth += 1
            continue

        if char == "}":
            depth -= 1

            if depth == 0:
                return (
                    text[
                        opening_index + 1:index
                    ],
                    index,
                )

    return (
        "",
        None,
    )


# ============================================================
# begin解析
# ============================================================
def _parse_begin_body(
    body: str,
    *,
    line: int,
    errors: list[SurveyValidationIssue],
) -> tuple[
    str | None,
    dict[str, Any],
]:
    parts = _split_comma_separated(
        body,
    )

    if not parts:
        errors.append(
            _error(
                "\\beginに質問形式がありません．",
                line=line,
            )
        )
        return (
            None,
            {},
        )

    question_type = parts[0].strip().lower()

    if question_type not in SUPPORTED_QUESTION_TYPES:
        errors.append(
            _error(
                f"未対応の質問形式です：{question_type}",
                line=line,
                field_name="type",
            )
        )
        return (
            None,
            {},
        )

    attributes: dict[str, Any] = {}

    for raw_attribute in parts[1:]:
        normalized = raw_attribute.strip()

        if not normalized:
            continue

        if "=" not in normalized:
            errors.append(
                _error(
                    (
                        "属性は name=value 形式で"
                        "指定してください："
                        f"{normalized}"
                    ),
                    line=line,
                )
            )
            continue

        name, raw_value = normalized.split(
            "=",
            maxsplit=1,
        )

        attribute_name = name.strip()

        if attribute_name not in BEGIN_ATTRIBUTE_NAMES:
            errors.append(
                _error(
                    f"未対応の質問属性です：{attribute_name}",
                    line=line,
                    field_name=attribute_name,
                )
            )
            continue

        if attribute_name in attributes:
            errors.append(
                _error(
                    f"質問属性が重複しています：{attribute_name}",
                    line=line,
                    field_name=attribute_name,
                )
            )
            continue

        attributes[attribute_name] = _parse_attribute_value(
            raw_value.strip(),
        )

    return (
        question_type,
        attributes,
    )


def _split_comma_separated(
    text: str,
) -> list[str]:
    parts: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    escaped = False

    for char in text:
        if escaped:
            buffer.append(
                char,
            )
            escaped = False
            continue

        if char == "\\":
            buffer.append(
                char,
            )
            escaped = True
            continue

        if quote is not None:
            buffer.append(
                char,
            )

            if char == quote:
                quote = None

            continue

        if char in {
            '"',
            "'",
        }:
            quote = char
            buffer.append(
                char,
            )
            continue

        if char == ",":
            parts.append(
                "".join(
                    buffer,
                ).strip()
            )
            buffer = []
            continue

        buffer.append(
            char,
        )

    parts.append(
        "".join(
            buffer,
        ).strip()
    )

    return parts


def _parse_attribute_value(
    text: str,
) -> Any:
    normalized = str(
        text,
    ).strip()
    lowered = normalized.lower()

    if lowered == "true":
        return True

    if lowered == "false":
        return False

    if lowered == "none":
        return None

    try:
        return ast.literal_eval(
            normalized,
        )

    except (
        SyntaxError,
        ValueError,
    ):
        return normalized


# ============================================================
# 質問生成
# ============================================================
def _build_question(
    block: MutableQuestionBlock,
    *,
    errors: list[SurveyValidationIssue],
    warnings: list[SurveyValidationIssue],
) -> SurveyQuestion | None:
    error_count_before = len(
        errors,
    )

    question_id = str(
        block.attributes.get("id") or "",
    ).strip()

    if not question_id:
        errors.append(
            _error(
                "質問属性idが指定されていません．",
                line=block.start_line,
                field_name="id",
            )
        )

    elif not ID_PATTERN.fullmatch(
        question_id,
    ):
        errors.append(
            _error(
                (
                    "質問IDは英字で始まり，"
                    "英数字・ハイフン・アンダースコアだけで"
                    "指定してください："
                    f"{question_id}"
                ),
                line=block.start_line,
                field_name="id",
                question_id=question_id,
            )
        )

    label = str(
        block.attributes.get("label") or "",
    ).strip()

    if not label:
        errors.append(
            _error(
                "label属性が指定されていません．",
                line=block.start_line,
                question_id=question_id or None,
                field_name="label",
            )
        )

    question_text = block.question.strip()

    if not question_text:
        errors.append(
            _error(
                "\\questionが指定されていません．",
                line=block.start_line,
                question_id=question_id or None,
            )
        )

    option_labels = block.options or []

    if (
        block.question_type in CHOICE_QUESTION_TYPES
        and not option_labels
    ):
        errors.append(
            _error(
                (
                    f"{block.question_type}形式には"
                    "\\optionsが必要です．"
                ),
                line=block.start_line,
                question_id=question_id or None,
            )
        )

    if (
        block.question_type not in CHOICE_QUESTION_TYPES
        and option_labels
    ):
        warnings.append(
            _warning(
                (
                    f"{block.question_type}形式の"
                    "\\optionsは使用されません．"
                ),
                line=block.options_line or block.start_line,
                question_id=question_id or None,
            )
        )

    min_value = _optional_float(
        block.attributes.get("min"),
        field_name="min",
        line=block.start_line,
        question_id=question_id,
        errors=errors,
    )

    max_value = _optional_float(
        block.attributes.get("max"),
        field_name="max",
        line=block.start_line,
        question_id=question_id,
        errors=errors,
    )

    step = _optional_float(
        block.attributes.get("step"),
        field_name="step",
        line=block.start_line,
        question_id=question_id,
        errors=errors,
    )

    max_length = _optional_int(
        block.attributes.get("max_length"),
        field_name="max_length",
        line=block.start_line,
        question_id=question_id,
        errors=errors,
    )

    if (
        min_value is not None
        and max_value is not None
        and min_value > max_value
    ):
        errors.append(
            _error(
                "minはmax以下にしてください．",
                line=block.start_line,
                question_id=question_id or None,
            )
        )

    if step is not None and step <= 0:
        errors.append(
            _error(
                "stepは0より大きい値にしてください．",
                line=block.start_line,
                field_name="step",
                question_id=question_id or None,
            )
        )

    if max_length is not None and max_length <= 0:
        errors.append(
            _error(
                "max_lengthは1以上にしてください．",
                line=block.start_line,
                field_name="max_length",
                question_id=question_id or None,
            )
        )

    options: list[SurveyOption] = []
    seen_options: set[str] = set()

    if block.question_type in CHOICE_QUESTION_TYPES:
        for option_index, option in enumerate(
            option_labels,
            start=1,
        ):
            if option.label in seen_options:
                errors.append(
                    _error(
                        f"選択肢が重複しています：{option.label}",
                        line=block.options_line or block.start_line,
                        question_id=question_id or None,
                    )
                )
                continue

            seen_options.add(
                option.label,
            )

            options.append(
                SurveyOption(
                    label=option.label,
                    value=option.value,
                    source_line=(
                        (block.options_line or block.start_line)
                        + option_index
                    ),
                )
            )


    if len(errors) > error_count_before:
        return None

    return SurveyQuestion(
        question_id=question_id,
        question_type=block.question_type,
        label=label,
        text=question_text,
        required=_to_bool(
            block.attributes.get("required"),
            default=False,
        ),
        show_if=_optional_str(
            block.attributes.get("show_if"),
        ),
        help_text=_optional_str(
            block.attributes.get("help"),
        ),
        placeholder=_optional_str(
            block.attributes.get("placeholder"),
        ),
        none_button=_to_bool(
            block.attributes.get("none_button"),
            default=False,
        ),
        skip_button=_to_bool(
            block.attributes.get("skip_button"),
            default=False,
        ),
        options=tuple(
            options,
        ),
        min_value=min_value,
        max_value=max_value,
        step=step,
        max_length=max_length,
        source_line=block.start_line,
    )


# ============================================================
# 選択肢
# ============================================================
def _parse_option_lines(
    body: str,
) -> list[SurveyOption]:
    results: list[SurveyOption] = []

    for line in body.splitlines():
        normalized = line.strip()

        if not normalized:
            continue

        if normalized.startswith("-"):
            normalized = normalized[1:].strip()

        if not normalized:
            continue

        # --------------------------------------------
        # score|label 形式
        # 例：
        # 5|大変使いやすい
        # 4.5|かなり良い
        # --------------------------------------------
        if "|" in normalized:
            raw_value, raw_label = normalized.split(
                "|",
                maxsplit=1,
            )

            raw_value = raw_value.strip()
            raw_label = raw_label.strip()

            try:
                if "." in raw_value:
                    value: Any = float(raw_value)
                else:
                    value = int(raw_value)
            except ValueError:
                value = raw_value

            results.append(
                SurveyOption(
                    value=value,
                    label=raw_label,
                    source_line=0,
                ),
            )
            continue

        # --------------------------------------------
        # 従来形式
        # --------------------------------------------
        results.append(
            SurveyOption(
                value=normalized,
                label=normalized,
                source_line=0,
            ),
        )

    return results


# ============================================================
# ID・version
# ============================================================
def _build_default_survey_id(
    *,
    source_filename: str,
    title: str,
) -> str:
    filename_stem = Path(
        str(source_filename or "")
    ).stem

    ascii_candidate = re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        filename_stem,
    ).strip("_-")

    if ascii_candidate:
        if not ascii_candidate[0].isalpha():
            ascii_candidate = (
                "survey_"
                + ascii_candidate
            )

        return ascii_candidate

    digest_source = (
        source_filename
        or title
        or "survey"
    )

    digest = hashlib.sha256(
        digest_source.encode("utf-8")
    ).hexdigest()[:12]

    return (
        "survey_"
        + digest
    )


def _parse_version(
    value: Any,
    *,
    line: int,
    errors: list[SurveyValidationIssue],
) -> int:
    if value is None or not str(value).strip():
        return 1

    try:
        version = int(
            str(value).strip(),
        )

    except (
        TypeError,
        ValueError,
    ):
        errors.append(
            _error(
                "\\versionは整数で指定してください．",
                line=line,
                field_name="version",
            )
        )
        return 1

    if version <= 0:
        errors.append(
            _error(
                "\\versionは1以上で指定してください．",
                line=line,
                field_name="version",
            )
        )
        return 1

    return version


# ============================================================
# 型変換
# ============================================================
def _to_bool(
    value: Any,
    *,
    default: bool,
) -> bool:
    if value is None:
        return default

    if isinstance(
        value,
        bool,
    ):
        return value

    normalized = str(
        value,
    ).strip().lower()

    if normalized in {
        "true",
        "1",
        "yes",
        "on",
    }:
        return True

    if normalized in {
        "false",
        "0",
        "no",
        "off",
    }:
        return False

    return default


def _optional_str(
    value: Any,
) -> str | None:
    if value is None:
        return None

    normalized = str(
        value,
    ).strip()

    return normalized or None


def _optional_float(
    value: Any,
    *,
    field_name: str,
    line: int,
    question_id: str,
    errors: list[SurveyValidationIssue],
) -> float | None:
    if value is None or value == "":
        return None

    try:
        return float(
            value,
        )

    except (
        TypeError,
        ValueError,
    ):
        errors.append(
            _error(
                f"{field_name}は数値で指定してください．",
                line=line,
                field_name=field_name,
                question_id=question_id or None,
            )
        )
        return None


def _optional_int(
    value: Any,
    *,
    field_name: str,
    line: int,
    question_id: str,
    errors: list[SurveyValidationIssue],
) -> int | None:
    if value is None or value == "":
        return None

    try:
        return int(
            value,
        )

    except (
        TypeError,
        ValueError,
    ):
        errors.append(
            _error(
                f"{field_name}は整数で指定してください．",
                line=line,
                field_name=field_name,
                question_id=question_id or None,
            )
        )
        return None


# ============================================================
# 共通
# ============================================================
def _normalize_multiline_body(
    body: str,
) -> str:
    lines = body.splitlines()

    while lines and not lines[0].strip():
        lines.pop(
            0,
        )

    while lines and not lines[-1].strip():
        lines.pop()

    return "\n".join(
        line.rstrip()
        for line in lines
    ).strip()


def _block_question_id(
    block: MutableQuestionBlock,
) -> str | None:
    return _optional_str(
        block.attributes.get("id"),
    )


def _line_number(
    text: str,
    index: int,
) -> int:
    return (
        text.count(
            "\n",
            0,
            index,
        )
        + 1
    )


def _calculate_sha256(
    text: str,
) -> str:
    return hashlib.sha256(
        text.encode(
            "utf-8",
        )
    ).hexdigest()


def _now_utc_iso() -> str:
    return datetime.now(
        timezone.utc,
    ).isoformat(
        timespec="seconds",
    )


def _error(
    message: str,
    *,
    line: int | None = None,
    field_name: str | None = None,
    question_id: str | None = None,
) -> SurveyValidationIssue:
    return SurveyValidationIssue(
        severity="error",
        message=message,
        line=line,
        field_name=field_name,
        question_id=question_id,
    )


def _warning(
    message: str,
    *,
    line: int | None = None,
    field_name: str | None = None,
    question_id: str | None = None,
) -> SurveyValidationIssue:
    return SurveyValidationIssue(
        severity="warning",
        message=message,
        line=line,
        field_name=field_name,
        question_id=question_id,
    )
