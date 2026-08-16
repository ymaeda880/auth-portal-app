# -*- coding: utf-8 -*-
# auth_portal_app/lib/sks_library/ai_search.py
# ============================================================
# SKSライブラリー AI検索
#
# 機能：
# - 蔵書一覧をAIへ送信する
# - AIから蔵書ID・関連度・選択理由を取得する
# - AIが返したIDを元DataFrameで検証する
# - 正式な書誌情報とAI評価を結合する
# - 入力量が大きい場合は分割検索＋最終ランキングを行う
#
# 方針：
# - AI providers は直接呼ばない
# - common_lib.ai.routing.call_text を使用する
# - AIが返した書誌情報は信用しない
# - 正式な書誌情報は必ず元CSVのDataFrameから取得する
# ============================================================

from __future__ import annotations

# ============================================================
# imports
# ============================================================
import json
from typing import Any

import pandas as pd

from common_lib.ai.routing import call_text

from .loader import (
    INTERNAL_ID_COLUMN,
    build_ai_book_line,
    build_ai_catalog_text,
)

from .prompts import (
    build_sks_ai_search_system_prompt,
    build_sks_ai_search_user_prompt,
    build_sks_ai_rerank_prompt,
)


# ============================================================
# 定数
# ============================================================
DEFAULT_MAX_RESULTS = 20

# ------------------------------------------------------------
# 1回のAI検索へ送る蔵書一覧の最大文字数
#
# モデルのコンテキスト上限を超えないように，
# 蔵書一覧が大きい場合は複数のチャンクへ分割する．
#
# 現在のSKS蔵書データは全体で約53万文字あるため，
# 1回あたり約8万文字を上限として分割検索する．
# ------------------------------------------------------------
DEFAULT_MAX_CATALOG_CHARS = 200_000

# ============================================================
# model key解析
# ============================================================
def parse_model_key(
    model_key: str,
) -> tuple[str, str]:
    """
    provider:model 形式を分解する．
    """

    raw = str(
        model_key or ""
    ).strip()

    if ":" not in raw:
        return (
            "openai",
            raw,
        )

    provider, model = raw.split(
        ":",
        1,
    )

    return (
        provider.strip(),
        model.strip(),
    )


# ============================================================
# JSON文字列整理
# ============================================================
def _clean_json_text(
    text: str,
) -> str:
    """
    AIが誤って ```json ... ``` を返した場合も解析できるようにする．
    """

    raw = str(
        text or ""
    ).strip()

    if raw.startswith("```"):
        lines = raw.splitlines()

        if lines:
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        raw = "\n".join(
            lines
        ).strip()

    # ------------------------------------------------------------
    # JSON前後に説明が付いた場合の最低限の救済
    # ------------------------------------------------------------
    first = raw.find("{")
    last = raw.rfind("}")

    if first >= 0 and last >= first:
        raw = raw[
            first:last + 1
        ]

    return raw


# ============================================================
# AI JSON解析
# ============================================================
def parse_ai_search_response(
    text: str,
) -> list[dict[str, Any]]:
    """
    AI回答から results を取り出す．

    JSONのみの返答を基本とするが，
    Markdownコードブロックや前後説明が付いた場合も
    可能な範囲で解析する．
    """

    raw = _clean_json_text(
        text,
    )

    if not raw:
        return []

    # ------------------------------------------------------------
    # 1. 通常のJSON解析
    # ------------------------------------------------------------
    try:
        obj = json.loads(
            raw
        )

    except json.JSONDecodeError:

        # --------------------------------------------------------
        # 2. results配列部分だけを救済
        #
        # AIがJSON前後へ説明を書いたり，
        # JSON全体の外側だけ崩した場合に対応する．
        # --------------------------------------------------------
        results_key_pos = raw.find(
            '"results"'
        )

        if results_key_pos < 0:
            raise ValueError(
                "AI検索結果にresultsが見つかりませんでした．"
            )

        array_start = raw.find(
            "[",
            results_key_pos,
        )

        if array_start < 0:
            raise ValueError(
                "AI検索結果のresults配列を取得できませんでした．"
            )

        # --------------------------------------------------------
        # 対応する ] を探す
        # --------------------------------------------------------
        depth = 0
        in_string = False
        escaped = False
        array_end = -1

        for pos in range(
            array_start,
            len(raw),
        ):

            ch = raw[pos]

            if escaped:
                escaped = False
                continue

            if ch == "\\" and in_string:
                escaped = True
                continue

            if ch == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if ch == "[":
                depth += 1

            elif ch == "]":
                depth -= 1

                if depth == 0:
                    array_end = pos
                    break

        if array_end < 0:
            raise ValueError(
                "AI検索結果のresults配列が途中で切れています．"
            )

        results_raw = raw[
            array_start:array_end + 1
        ]

        try:
            results = json.loads(
                results_raw
            )

        except json.JSONDecodeError as e:
            raise ValueError(
                "AI検索結果のresults配列をJSONとして解析できませんでした．"
            ) from e

        obj = {
            "results": results,
        }

    # ------------------------------------------------------------
    # results取得
    # ------------------------------------------------------------
    results = obj.get(
        "results",
        [],
    )

    if not isinstance(
        results,
        list,
    ):
        raise ValueError(
            "AI検索結果のresultsが配列ではありません．"
        )

    # ------------------------------------------------------------
    # 各結果を整理
    # ------------------------------------------------------------
    cleaned: list[dict[str, Any]] = []

    for item in results:

        if not isinstance(
            item,
            dict,
        ):
            continue

        sks_id = str(
            item.get(
                "id",
                "",
            )
            or ""
        ).strip()

        if not sks_id:
            continue

        # --------------------------------------------------------
        # score
        # --------------------------------------------------------
        raw_score = item.get(
            "score",
            0,
        )

        try:
            score = int(
                round(
                    float(raw_score)
                )
            )

        except Exception:
            score = 0

        score = max(
            0,
            min(
                100,
                score,
            ),
        )

        # --------------------------------------------------------
        # reason
        # --------------------------------------------------------
        reason = str(
            item.get(
                "reason",
                "",
            )
            or ""
        ).strip()

        cleaned.append(
            {
                "id": sks_id,
                "score": score,
                "reason": reason,
            }
        )

    return cleaned

# ============================================================
# AI呼び出し
# ============================================================
def _call_ai(
    *,
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
):
    return call_text(
        provider=provider,
        model=model,
        prompt=user_prompt,
        system=system_prompt,
        temperature=None,
        max_output_tokens=None,
        extra=None,
    )


# ============================================================
# AI検索1回
# ============================================================
def _run_single_ai_search(
    *,
    provider: str,
    model: str,
    query: str,
    catalog_text: str,
    max_results: int,
) -> tuple[
    list[dict[str, Any]],
    Any,
]:
    """
    1つの蔵書一覧を対象としてAI検索を1回実行する．
    """

    system_prompt = (
        build_sks_ai_search_system_prompt()
    )

    user_prompt = (
        build_sks_ai_search_user_prompt(
            query=query,
            catalog_text=catalog_text,
            max_results=max_results,
        )
    )

    res = _call_ai(
        provider=provider,
        model=model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )

    response_text = str(
        getattr(
            res,
            "text",
            "",
        )
        or ""
    ).strip()

    results = parse_ai_search_response(
        response_text,
    )

    return (
        results,
        res,
    )


# ============================================================
# 蔵書一覧分割
# ============================================================
def _split_catalog_dataframe(
    df: pd.DataFrame,
    *,
    max_chars: int,
) -> list[pd.DataFrame]:
    """
    AI送信用文字数を基準としてDataFrameを分割する．
    """

    if df.empty:
        return []

    chunks: list[pd.DataFrame] = []

    current_indices: list[int] = []
    current_chars = 0

    for idx, row in df.iterrows():

        line = build_ai_book_line(
            row,
        )

        line_chars = len(line) + 1

        # ------------------------------------------------------------
        # 現チャンクへ追加すると上限を超える場合
        # ------------------------------------------------------------
        if (
            current_indices
            and current_chars + line_chars > max_chars
        ):
            chunks.append(
                df.loc[
                    current_indices
                ].copy()
            )

            current_indices = []
            current_chars = 0

        current_indices.append(
            idx
        )

        current_chars += line_chars

    # ------------------------------------------------------------
    # 最終チャンク
    # ------------------------------------------------------------
    if current_indices:
        chunks.append(
            df.loc[
                current_indices
            ].copy()
        )

    return chunks


# ============================================================
# AI結果のID検証
# ============================================================
def _validate_ai_results(
    df: pd.DataFrame,
    ai_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    AIが返したIDのうち，
    元DataFrameに存在するものだけを採用する．
    """

    valid_ids = set(
        df[
            INTERNAL_ID_COLUMN
        ]
        .astype(str)
        .tolist()
    )

    validated: list[
        dict[str, Any]
    ] = []

    seen_ids: set[str] = set()

    for item in ai_results:

        sks_id = str(
            item.get(
                "id",
                "",
            )
            or ""
        ).strip()

        if not sks_id:
            continue

        if sks_id not in valid_ids:
            continue

        # ------------------------------------------------------------
        # 同じIDは1件だけ
        # ------------------------------------------------------------
        if sks_id in seen_ids:
            continue

        seen_ids.add(
            sks_id
        )

        validated.append(
            {
                "id": sks_id,
                "score": int(
                    item.get(
                        "score",
                        0,
                    )
                    or 0
                ),
                "reason": str(
                    item.get(
                        "reason",
                        "",
                    )
                    or ""
                ).strip(),
            }
        )

    return validated


# ============================================================
# AI結果 → DataFrame
# ============================================================
def _merge_ai_results_with_books(
    df: pd.DataFrame,
    ai_results: list[dict[str, Any]],
) -> pd.DataFrame:
    """
    AI結果と元の蔵書DataFrameを結合する．
    """

    if not ai_results:
        result = df.iloc[
            0:0
        ].copy()

        result[
            "AI関連度"
        ] = pd.Series(
            dtype="int64",
        )

        result[
            "AI選定理由"
        ] = pd.Series(
            dtype="object",
        )

        return result

    # ------------------------------------------------------------
    # AI結果DataFrame
    # ------------------------------------------------------------
    ai_df = pd.DataFrame(
        ai_results
    )

    ai_df = ai_df.rename(
        columns={
            "id": INTERNAL_ID_COLUMN,
            "score": "AI関連度",
            "reason": "AI選定理由",
        }
    )

    # ------------------------------------------------------------
    # AI側の順序を保持
    # ------------------------------------------------------------
    ai_df[
        "_ai_order"
    ] = range(
        len(ai_df)
    )

    # ------------------------------------------------------------
    # 元CSVと結合
    # ------------------------------------------------------------
    merged = ai_df.merge(
        df,
        on=INTERNAL_ID_COLUMN,
        how="inner",
    )

    # ------------------------------------------------------------
    # 関連度優先
    #
    # 同点ならAIが返した順序を維持する．
    # ------------------------------------------------------------
    merged = merged.sort_values(
        by=[
            "AI関連度",
            "_ai_order",
        ],
        ascending=[
            False,
            True,
        ],
        kind="stable",
    )

    merged.drop(
        columns=[
            "_ai_order",
        ],
        inplace=True,
    )

    merged.reset_index(
        drop=True,
        inplace=True,
    )

    # ------------------------------------------------------------
    # 列順
    # ------------------------------------------------------------
    preferred_columns = [
        INTERNAL_ID_COLUMN,
        "分類: NDC",
        "棚番号-段",
        "タイトル",
        "編著者",
        "発行者",
        "発行年",
        "言語",
        "注記：原著名／仮訳、ISBN等",
        "貴重書",
        "タグ",
        "AI関連度",
        "AI選定理由",
    ]

    existing_columns = [
        col
        for col in preferred_columns
        if col in merged.columns
    ]

    return merged[
        existing_columns
    ].copy()


# ============================================================
# 分割検索候補をDataFrame化
# ============================================================
def _collect_candidate_dataframe(
    df: pd.DataFrame,
    ai_results: list[dict[str, Any]],
) -> pd.DataFrame:
    validated = _validate_ai_results(
        df,
        ai_results,
    )

    if not validated:
        return df.iloc[
            0:0
        ].copy()

    ids = [
        item["id"]
        for item in validated
    ]

    order_map = {
        sks_id: index
        for index, sks_id in enumerate(ids)
    }

    candidate_df = df[
        df[
            INTERNAL_ID_COLUMN
        ].astype(str).isin(ids)
    ].copy()

    candidate_df[
        "_candidate_order"
    ] = (
        candidate_df[
            INTERNAL_ID_COLUMN
        ]
        .map(order_map)
    )

    candidate_df.sort_values(
        "_candidate_order",
        inplace=True,
        kind="stable",
    )

    candidate_df.drop(
        columns=[
            "_candidate_order",
        ],
        inplace=True,
    )

    return candidate_df


# ============================================================
# 公開API：AI検索
# ============================================================
def run_sks_ai_search(
    df: pd.DataFrame,
    *,
    query: str,
    model_key: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    max_catalog_chars: int = DEFAULT_MAX_CATALOG_CHARS,
) -> tuple[
    pd.DataFrame,
    list[Any],
]:
    """
    SKSライブラリーAI検索を実行する．

    戻り値：
        (
            検索結果DataFrame,
            AIレスポンス一覧
        )

    AIレスポンス一覧は，
    usage / cost取得用としてページ側で利用できる．
    """

    query_text = str(
        query or ""
    ).strip()

    if not query_text:
        raise ValueError(
            "AI検索の質問を入力してください．"
        )

    if df.empty:
        return (
            df.copy(),
            [],
        )

    # ------------------------------------------------------------
    # model
    # ------------------------------------------------------------
    provider, model = parse_model_key(
        model_key,
    )

    if not provider or not model:
        raise ValueError(
            f"モデル指定が不正です: {model_key}"
        )

    max_results = max(
        1,
        int(max_results),
    )

    max_catalog_chars = max(
        10_000,
        int(max_catalog_chars),
    )

    # ------------------------------------------------------------
    # 全蔵書一覧を作成
    # ------------------------------------------------------------
    catalog_text = build_ai_catalog_text(
        df,
    )

    ai_responses: list[Any] = []

    # ============================================================
    # 1回で送れる場合
    # ============================================================
    if len(
        catalog_text
    ) <= max_catalog_chars:

        ai_results, res = (
            _run_single_ai_search(
                provider=provider,
                model=model,
                query=query_text,
                catalog_text=catalog_text,
                max_results=max_results,
            )
        )

        ai_responses.append(
            res
        )

        validated = _validate_ai_results(
            df,
            ai_results,
        )

        validated = validated[
            :max_results
        ]

        result_df = (
            _merge_ai_results_with_books(
                df,
                validated,
            )
        )

        return (
            result_df,
            ai_responses,
        )

    # ============================================================
    # 分割検索
    # ============================================================
    chunks = _split_catalog_dataframe(
        df,
        max_chars=max_catalog_chars,
    )

    all_chunk_results: list[
        dict[str, Any]
    ] = []

    # ------------------------------------------------------------
    # 各チャンクから候補抽出
    # ------------------------------------------------------------
    for chunk_df in chunks:

        chunk_catalog = (
            build_ai_catalog_text(
                chunk_df,
            )
        )

        try:

            chunk_results, res = (
                _run_single_ai_search(
                    provider=provider,
                    model=model,
                    query=query_text,
                    catalog_text=chunk_catalog,
                    max_results=max_results,
                )
            )

            ai_responses.append(
                res
            )

            validated_chunk = (
                _validate_ai_results(
                    chunk_df,
                    chunk_results,
                )
            )

            all_chunk_results.extend(
                validated_chunk
            )

        except ValueError:

            # ------------------------------------------------------------
            # 1チャンクのAI返答がJSONとして解析できなくても，
            # 他チャンクの検索は継続する．
            # ------------------------------------------------------------
            continue

    # ------------------------------------------------------------
    # 候補重複除去
    # ------------------------------------------------------------
    unique_candidates: dict[
        str,
        dict[str, Any],
    ] = {}

    for item in all_chunk_results:

        sks_id = str(
            item.get(
                "id",
                "",
            )
            or ""
        ).strip()

        if not sks_id:
            continue

        previous = (
            unique_candidates.get(
                sks_id
            )
        )

        if previous is None:
            unique_candidates[
                sks_id
            ] = item
            continue

        # ------------------------------------------------------------
        # 同じIDなら高いscore側を残す
        # ------------------------------------------------------------
        if int(
            item.get(
                "score",
                0,
            )
            or 0
        ) > int(
            previous.get(
                "score",
                0,
            )
            or 0
        ):
            unique_candidates[
                sks_id
            ] = item

    candidate_items = list(
        unique_candidates.values()
    )

    if not candidate_items:
        return (
            _merge_ai_results_with_books(
                df,
                [],
            ),
            ai_responses,
        )

    # ------------------------------------------------------------
    # 候補蔵書だけ取得
    # ------------------------------------------------------------
    candidate_df = (
        _collect_candidate_dataframe(
            df,
            candidate_items,
        )
    )

    candidates_text = (
        build_ai_catalog_text(
            candidate_df,
        )
    )

    # ============================================================
    # 最終ランキング
    # ============================================================
    system_prompt = (
        build_sks_ai_search_system_prompt()
    )

    rerank_prompt = (
        build_sks_ai_rerank_prompt(
            query=query_text,
            candidates_text=candidates_text,
            max_results=max_results,
        )
    )

    rerank_res = _call_ai(
        provider=provider,
        model=model,
        system_prompt=system_prompt,
        user_prompt=rerank_prompt,
    )

    ai_responses.append(
        rerank_res
    )

    rerank_text = str(
        getattr(
            rerank_res,
            "text",
            "",
        )
        or ""
    ).strip()

    rerank_results = (
        parse_ai_search_response(
            rerank_text,
        )
    )

    validated_final = (
        _validate_ai_results(
            candidate_df,
            rerank_results,
        )
    )

    validated_final = validated_final[
        :max_results
    ]

    result_df = (
        _merge_ai_results_with_books(
            df,
            validated_final,
        )
    )

    return (
        result_df,
        ai_responses,
    )