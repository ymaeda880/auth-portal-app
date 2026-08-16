# -*- coding: utf-8 -*-
# auth_portal_app/lib/survey/runtime/publication.py
# ============================================================
# 社内アンケート 公開状態判定
#
# 機能：
# - アンケート状態を正規化する
# - 公開開始前・回答受付中・回答終了を判定する
# - start_at・end_atによる公開期間を判定する
# - 一般ユーザーがアンケートを閲覧できるか判定する
# - 一般ユーザーが回答・再回答できるか判定する
# - UTC保存日時をJST表示へ変換する
#
# 状態：
# - draft
# - scheduled
# - open
# - closed
# - archived
#
# 方針：
# - 日時の内部基準はUTCとする
# - timezone未設定のdatetimeはUTCとして扱う
# - 画面表示時だけJSTへ変換する
# - Streamlitには依存しない
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from zoneinfo import ZoneInfo


# ============================================================
# 定数
# ============================================================
UTC = timezone.utc
JST = ZoneInfo(
    "Asia/Tokyo",
)

SURVEY_STATUS_DRAFT = "draft"
SURVEY_STATUS_SCHEDULED = "scheduled"
SURVEY_STATUS_OPEN = "open"
SURVEY_STATUS_CLOSED = "closed"
SURVEY_STATUS_ARCHIVED = "archived"

SUPPORTED_SURVEY_STATUSES = {
    SURVEY_STATUS_DRAFT,
    SURVEY_STATUS_SCHEDULED,
    SURVEY_STATUS_OPEN,
    SURVEY_STATUS_CLOSED,
    SURVEY_STATUS_ARCHIVED,
}


# ============================================================
# 公開段階
# ============================================================
class SurveyPublicationPhase(
    str,
    Enum,
):
    # ------------------------------------------------------------
    # draft
    # - 管理者による作成中
    # ------------------------------------------------------------
    DRAFT = "draft"

    # ------------------------------------------------------------
    # scheduled
    # - 公開予定
    # - start_atより前
    # ------------------------------------------------------------
    SCHEDULED = "scheduled"

    # ------------------------------------------------------------
    # open
    # - 回答受付中
    # ------------------------------------------------------------
    OPEN = "open"

    # ------------------------------------------------------------
    # closed
    # - 回答終了
    # ------------------------------------------------------------
    CLOSED = "closed"

    # ------------------------------------------------------------
    # archived
    # - 保管済み
    # ------------------------------------------------------------
    ARCHIVED = "archived"


# ============================================================
# 公開判定結果
# ============================================================
@dataclass(frozen=True)
class SurveyPublicationResult:
    # ------------------------------------------------------------
    # 定義上の状態
    # ------------------------------------------------------------
    configured_status: str

    # ------------------------------------------------------------
    # 日時を反映した実際の公開段階
    # ------------------------------------------------------------
    phase: SurveyPublicationPhase

    # ------------------------------------------------------------
    # 判定時刻
    # ------------------------------------------------------------
    evaluated_at: datetime

    # ------------------------------------------------------------
    # 公開期間
    # ------------------------------------------------------------
    start_at: datetime | None = None
    end_at: datetime | None = None

    # ------------------------------------------------------------
    # 利用可否
    # ------------------------------------------------------------
    is_visible_to_user: bool = False
    can_submit: bool = False
    can_resubmit: bool = False

    # ------------------------------------------------------------
    # 表示用メッセージ
    # ------------------------------------------------------------
    message: str = ""

    @property
    def is_draft(self) -> bool:
        return (
            self.phase
            == SurveyPublicationPhase.DRAFT
        )

    @property
    def is_scheduled(self) -> bool:
        return (
            self.phase
            == SurveyPublicationPhase.SCHEDULED
        )

    @property
    def is_open(self) -> bool:
        return (
            self.phase
            == SurveyPublicationPhase.OPEN
        )

    @property
    def is_closed(self) -> bool:
        return (
            self.phase
            == SurveyPublicationPhase.CLOSED
        )

    @property
    def is_archived(self) -> bool:
        return (
            self.phase
            == SurveyPublicationPhase.ARCHIVED
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "configured_status": (
                self.configured_status
            ),
            "phase": self.phase.value,
            "evaluated_at": (
                self.evaluated_at.isoformat()
            ),
            "start_at": (
                self.start_at.isoformat()
                if self.start_at is not None
                else None
            ),
            "end_at": (
                self.end_at.isoformat()
                if self.end_at is not None
                else None
            ),
            "is_visible_to_user": (
                self.is_visible_to_user
            ),
            "can_submit": self.can_submit,
            "can_resubmit": self.can_resubmit,
            "message": self.message,
            "is_draft": self.is_draft,
            "is_scheduled": self.is_scheduled,
            "is_open": self.is_open,
            "is_closed": self.is_closed,
            "is_archived": self.is_archived,
        }


# ============================================================
# public API：公開状態判定
# ============================================================
def evaluate_survey_publication(
    *,
    status: Any,
    start_at: Any = None,
    end_at: Any = None,
    now: datetime | None = None,
    allow_resubmission: bool = True,
) -> SurveyPublicationResult:
    # ------------------------------------------------------------
    # 現在日時
    # ------------------------------------------------------------
    evaluated_at = ensure_utc_datetime(
        now or datetime.now(
            UTC,
        )
    )

    # ------------------------------------------------------------
    # 状態と期間の正規化
    # ------------------------------------------------------------
    normalized_status = normalize_survey_status(
        status,
    )

    normalized_start_at = parse_datetime_utc(
        start_at,
    )

    normalized_end_at = parse_datetime_utc(
        end_at,
    )

    # ------------------------------------------------------------
    # draft
    # ------------------------------------------------------------
    if (
        normalized_status
        == SURVEY_STATUS_DRAFT
    ):
        return SurveyPublicationResult(
            configured_status=normalized_status,
            phase=SurveyPublicationPhase.DRAFT,
            evaluated_at=evaluated_at,
            start_at=normalized_start_at,
            end_at=normalized_end_at,
            is_visible_to_user=False,
            can_submit=False,
            can_resubmit=False,
            message=(
                "このアンケートは現在作成中です．"
            ),
        )

    # ------------------------------------------------------------
    # archived
    # ------------------------------------------------------------
    if (
        normalized_status
        == SURVEY_STATUS_ARCHIVED
    ):
        return SurveyPublicationResult(
            configured_status=normalized_status,
            phase=SurveyPublicationPhase.ARCHIVED,
            evaluated_at=evaluated_at,
            start_at=normalized_start_at,
            end_at=normalized_end_at,
            is_visible_to_user=False,
            can_submit=False,
            can_resubmit=False,
            message=(
                "このアンケートは保管済みです．"
            ),
        )

    # ------------------------------------------------------------
    # closed
    # ------------------------------------------------------------
    if (
        normalized_status
        == SURVEY_STATUS_CLOSED
    ):
        return SurveyPublicationResult(
            configured_status=normalized_status,
            phase=SurveyPublicationPhase.CLOSED,
            evaluated_at=evaluated_at,
            start_at=normalized_start_at,
            end_at=normalized_end_at,
            is_visible_to_user=True,
            can_submit=False,
            can_resubmit=False,
            message=(
                "このアンケートの回答受付は"
                "終了しています．"
            ),
        )

    # ------------------------------------------------------------
    # 開始日時前
    #
    # statusがscheduledまたはopenであっても，
    # start_atより前なら公開予定として扱う
    # ------------------------------------------------------------
    if (
        normalized_start_at is not None
        and evaluated_at < normalized_start_at
    ):
        return SurveyPublicationResult(
            configured_status=normalized_status,
            phase=SurveyPublicationPhase.SCHEDULED,
            evaluated_at=evaluated_at,
            start_at=normalized_start_at,
            end_at=normalized_end_at,
            is_visible_to_user=True,
            can_submit=False,
            can_resubmit=False,
            message=build_scheduled_message(
                normalized_start_at,
            ),
        )

    # ------------------------------------------------------------
    # 終了日時後
    #
    # statusがscheduledまたはopenであっても，
    # end_atを過ぎていれば終了として扱う
    # ------------------------------------------------------------
    if (
        normalized_end_at is not None
        and evaluated_at > normalized_end_at
    ):
        return SurveyPublicationResult(
            configured_status=normalized_status,
            phase=SurveyPublicationPhase.CLOSED,
            evaluated_at=evaluated_at,
            start_at=normalized_start_at,
            end_at=normalized_end_at,
            is_visible_to_user=True,
            can_submit=False,
            can_resubmit=False,
            message=(
                "このアンケートの回答受付は"
                "終了しています．"
            ),
        )

    # ------------------------------------------------------------
    # scheduled状態
    #
    # start_atが未設定，または開始日時を過ぎていても，
    # status自体がscheduledなら回答不可
    # ------------------------------------------------------------
    if (
        normalized_status
        == SURVEY_STATUS_SCHEDULED
    ):
        return SurveyPublicationResult(
            configured_status=normalized_status,
            phase=SurveyPublicationPhase.SCHEDULED,
            evaluated_at=evaluated_at,
            start_at=normalized_start_at,
            end_at=normalized_end_at,
            is_visible_to_user=True,
            can_submit=False,
            can_resubmit=False,
            message=build_scheduled_message(
                normalized_start_at,
            ),
        )

    # ------------------------------------------------------------
    # open
    # ------------------------------------------------------------
    if (
        normalized_status
        == SURVEY_STATUS_OPEN
    ):
        return SurveyPublicationResult(
            configured_status=normalized_status,
            phase=SurveyPublicationPhase.OPEN,
            evaluated_at=evaluated_at,
            start_at=normalized_start_at,
            end_at=normalized_end_at,
            is_visible_to_user=True,
            can_submit=True,
            can_resubmit=bool(
                allow_resubmission,
            ),
            message=build_open_message(
                normalized_end_at,
            ),
        )

    # ------------------------------------------------------------
    # 防御的処理
    # ------------------------------------------------------------
    raise ValueError(
        (
            "アンケート状態を判定できません："
            f"{normalized_status}"
        )
    )


# ============================================================
# public API：状態の正規化
# ============================================================
def normalize_survey_status(
    status: Any,
) -> str:
    # ------------------------------------------------------------
    # Enum
    # ------------------------------------------------------------
    if isinstance(
        status,
        Enum,
    ):
        raw_status = status.value

    else:
        raw_status = status

    normalized_status = str(
        raw_status or "",
    ).strip().lower()

    # ------------------------------------------------------------
    # 管理画面との互換
    # running は open と同義
    # ------------------------------------------------------------
    if normalized_status == "running":
        normalized_status = SURVEY_STATUS_OPEN

    if not normalized_status:
        return SURVEY_STATUS_DRAFT

    if (
        normalized_status
        not in SUPPORTED_SURVEY_STATUSES
    ):
        raise ValueError(
            (
                "未対応のアンケート状態です："
                f"{normalized_status}"
            )
        )

    return normalized_status


# ============================================================
# public API：UTC日時解析
# ============================================================
def parse_datetime_utc(
    value: Any,
) -> datetime | None:
    # ------------------------------------------------------------
    # 未設定
    # ------------------------------------------------------------
    if value is None:
        return None

    if isinstance(
        value,
        str,
    ):
        stripped = value.strip()

        if not stripped:
            return None

        normalized_text = stripped

        # --------------------------------------------------------
        # ISO 8601のZ表記をPython対応形式へ変換
        # --------------------------------------------------------
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

        except ValueError as exc:
            raise ValueError(
                (
                    "日時をISO 8601形式として"
                    "解釈できません："
                    f"{stripped}"
                )
            ) from exc

        return ensure_utc_datetime(
            parsed,
        )

    if isinstance(
        value,
        datetime,
    ):
        return ensure_utc_datetime(
            value,
        )

    raise TypeError(
        (
            "日時はdatetime型または"
            "ISO 8601形式の文字列で"
            "指定してください．"
        )
    )


# ============================================================
# public API：UTC保証
# ============================================================
def ensure_utc_datetime(
    value: datetime,
) -> datetime:
    if not isinstance(
        value,
        datetime,
    ):
        raise TypeError(
            "valueはdatetime型で指定してください．"
        )

    # ------------------------------------------------------------
    # timezone未設定の場合
    #
    # 保存済みデータとの互換性を保つため，
    # naive datetimeはUTCとして扱う
    # ------------------------------------------------------------
    if value.tzinfo is None:
        return value.replace(
            tzinfo=UTC,
        )

    return value.astimezone(
        UTC,
    )


# ============================================================
# public API：JST変換
# ============================================================
def to_jst_datetime(
    value: datetime | str | None,
) -> datetime | None:
    parsed = parse_datetime_utc(
        value,
    )

    if parsed is None:
        return None

    return parsed.astimezone(
        JST,
    )


# ============================================================
# public API：JST表示文字列
# ============================================================
def format_datetime_jst(
    value: datetime | str | None,
    *,
    empty_text: str = "未設定",
    include_seconds: bool = False,
) -> str:
    jst_value = to_jst_datetime(
        value,
    )

    if jst_value is None:
        return empty_text

    if include_seconds:
        return jst_value.strftime(
            "%Y年%m月%d日 %H:%M:%S",
        )

    return jst_value.strftime(
        "%Y年%m月%d日 %H:%M",
    )


# ============================================================
# public API：期間設定検証
# ============================================================
def validate_publication_period(
    *,
    start_at: Any = None,
    end_at: Any = None,
) -> tuple[str, ...]:
    errors: list[str] = []

    try:
        normalized_start_at = parse_datetime_utc(
            start_at,
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        errors.append(
            f"公開開始日時が不正です：{exc}"
        )
        normalized_start_at = None

    try:
        normalized_end_at = parse_datetime_utc(
            end_at,
        )

    except (
        TypeError,
        ValueError,
    ) as exc:
        errors.append(
            f"公開終了日時が不正です：{exc}"
        )
        normalized_end_at = None

    if (
        normalized_start_at is not None
        and normalized_end_at is not None
        and normalized_start_at
        >= normalized_end_at
    ):
        errors.append(
            (
                "公開終了日時は，公開開始日時より"
                "後に設定してください．"
            )
        )

    return tuple(
        errors,
    )


# ============================================================
# public API：回答可能判定
# ============================================================
def can_answer_survey(
    *,
    status: Any,
    start_at: Any = None,
    end_at: Any = None,
    now: datetime | None = None,
) -> bool:
    result = evaluate_survey_publication(
        status=status,
        start_at=start_at,
        end_at=end_at,
        now=now,
    )

    return result.can_submit


# ============================================================
# public API：再回答可能判定
# ============================================================
def can_resubmit_survey(
    *,
    status: Any,
    start_at: Any = None,
    end_at: Any = None,
    now: datetime | None = None,
    allow_resubmission: bool = True,
) -> bool:
    result = evaluate_survey_publication(
        status=status,
        start_at=start_at,
        end_at=end_at,
        now=now,
        allow_resubmission=(
            allow_resubmission
        ),
    )

    return result.can_resubmit


# ============================================================
# public API：一般ユーザーへの表示判定
# ============================================================
def is_survey_visible_to_user(
    *,
    status: Any,
    start_at: Any = None,
    end_at: Any = None,
    now: datetime | None = None,
) -> bool:
    result = evaluate_survey_publication(
        status=status,
        start_at=start_at,
        end_at=end_at,
        now=now,
    )

    return result.is_visible_to_user


# ============================================================
# メッセージ生成
# ============================================================
def build_scheduled_message(
    start_at: datetime | None,
) -> str:
    if start_at is None:
        return (
            "このアンケートは現在公開予定です．"
        )

    return (
        "このアンケートは"
        f"{format_datetime_jst(start_at)}"
        "から回答できます．"
    )


def build_open_message(
    end_at: datetime | None,
) -> str:
    if end_at is None:
        return (
            "このアンケートは現在回答受付中です．"
        )

    return (
        "このアンケートは"
        f"{format_datetime_jst(end_at)}"
        "まで回答できます．"
    )