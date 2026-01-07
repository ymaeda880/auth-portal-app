# -*- coding: utf-8 -*-
# lib/memo/db.py
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Optional


def db_path(index_root: Path) -> Path:
    return index_root / "notes.db"


def connect_db(dbfile: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(dbfile))
    con.row_factory = sqlite3.Row
    return con


def init_db(dbfile: Path) -> None:
    dbfile.parent.mkdir(parents=True, exist_ok=True)
    con = connect_db(dbfile)
    try:
        cur = con.cursor()
        cur.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts
            USING fts5(
                note_id UNINDEXED,
                title,
                content,
                tags,
                created_at UNINDEXED,
                updated_at UNINDEXED
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS notes_meta (
                note_id TEXT PRIMARY KEY,
                relpath TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                content_hash TEXT NOT NULL
            )
            """
        )
        con.commit()
    finally:
        con.close()


def upsert_index(
    dbfile: Path,
    note_id: str,
    relpath: str,
    title: str,
    content: str,
    tags_str: str,        # ← ただの str
    created_at: str,
    updated_at: str,
    content_hash: str,
) -> None:
    con = connect_db(dbfile)
    try:
        cur = con.cursor()
        cur.execute(
            """
            INSERT INTO notes_meta(note_id, relpath, created_at, updated_at, content_hash)
            VALUES(?,?,?,?,?)
            ON CONFLICT(note_id) DO UPDATE SET
                relpath=excluded.relpath,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at,
                content_hash=excluded.content_hash
            """,
            (note_id, relpath, created_at, updated_at, content_hash),
        )
        cur.execute("DELETE FROM notes_fts WHERE note_id = ?", (note_id,))
        cur.execute(
            """
            INSERT INTO notes_fts(note_id, title, content, tags, created_at, updated_at)
            VALUES(?,?,?,?,?,?)
            """,
            (note_id, title, content, tags_str, created_at, updated_at),
        )
        con.commit()
    finally:
        con.close()


def delete_index(dbfile: Path, note_id: str) -> None:
    con = connect_db(dbfile)
    try:
        cur = con.cursor()
        cur.execute("DELETE FROM notes_fts WHERE note_id = ?", (note_id,))
        cur.execute("DELETE FROM notes_meta WHERE note_id = ?", (note_id,))
        con.commit()
    finally:
        con.close()


def list_recent(dbfile: Path, limit: int = 100) -> List[sqlite3.Row]:
    con = connect_db(dbfile)
    try:
        cur = con.cursor()
        cur.execute(
            """
            SELECT note_id, relpath, created_at, updated_at
            FROM notes_meta
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cur.fetchall()
    finally:
        con.close()


def list_all_meta(dbfile: Path) -> List[sqlite3.Row]:
    con = connect_db(dbfile)
    try:
        cur = con.cursor()
        cur.execute(
            """
            SELECT note_id, relpath, created_at, updated_at, content_hash
            FROM notes_meta
            ORDER BY updated_at DESC
            """
        )
        return cur.fetchall()
    finally:
        con.close()


def get_meta_by_note_id(dbfile: Path, note_id: str) -> Optional[sqlite3.Row]:
    con = connect_db(dbfile)
    try:
        cur = con.cursor()
        cur.execute(
            """
            SELECT note_id, relpath, created_at, updated_at
            FROM notes_meta
            WHERE note_id = ?
            """,
            (note_id,),
        )
        return cur.fetchone()
    finally:
        con.close()


# ============================================================
# FTS query helper (prefix search)
# ============================================================

def _prefixify_query(q: str) -> str:
    """
    FTS5 の MATCH はデフォルトで部分一致しないため、
    ユーザー入力を「前方一致（prefix）」に寄せる。
    例:
      山田        -> 山田*
      山田 太郎   -> 山田* 太郎*
      山田 OR 太郎 -> 山田* OR 太郎*
      "山田 太郎" -> "山田 太郎"   （フレーズは壊さない）

    ポリシー（安全寄り）:
    - OR/AND/NOT は保持
    - ダブルクォートで囲まれたフレーズはそのまま（* を付けない）
    - 既に * が付いているトークンはそのまま
    """
    q = (q or "").strip()
    if not q:
        return q

    out: List[str] = []
    token = ""
    in_quote = False

    def flush(tok: str) -> None:
        tok = (tok or "").strip()
        if not tok:
            return

        upper = tok.upper()
        if upper in ("OR", "AND", "NOT"):
            out.append(tok)
            return

        if tok.endswith("*"):
            out.append(tok)
            return

        # 記号しかない場合はそのまま
        if all(not ch.isalnum() for ch in tok):
            out.append(tok)
            return

        out.append(tok + "*")

    for ch in q:
        if ch == '"':
            if in_quote:
                # クォート閉じ：フレーズ全体をそのまま出す
                token += ch
                out.append(token)
                token = ""
                in_quote = False
            else:
                # クォート開始：直前トークンを確定
                if token.strip():
                    flush(token)
                    token = ""
                token = '"'
                in_quote = True
            continue

        if in_quote:
            token += ch
            continue

        # 通常：空白で区切る
        if ch.isspace():
            flush(token)
            token = ""
        else:
            token += ch

    # 最後のトークン
    if in_quote:
        # クォートが閉じていない → 壊さないためそのまま
        out.append(token)
    else:
        flush(token)

    return " ".join(out)


def search_fts(dbfile: Path, query: str, limit: int = 50) -> List[sqlite3.Row]:
    """
    検索:
    - ユーザー入力 query を prefix 検索に変換して MATCH する
    - 返り値は notes_meta の行（note_id, relpath, created_at, updated_at）
    """
    con = connect_db(dbfile)
    try:
        cur = con.cursor()

        # ★ここが修正点：前方一致化
        q2 = _prefixify_query(query)

        cur.execute(
            """
            SELECT note_id, bm25(notes_fts) AS rank
            FROM notes_fts
            WHERE notes_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (q2, limit),
        )
        rows = cur.fetchall()
        if not rows:
            return []

        ids = [r["note_id"] for r in rows]
        placeholders = ",".join(["?"] * len(ids))
        cur.execute(
            f"""
            SELECT note_id, relpath, created_at, updated_at
            FROM notes_meta
            WHERE note_id IN ({placeholders})
            """,
            ids,
        )
        meta = {r["note_id"]: r for r in cur.fetchall()}

        # ランク順維持
        out: List[sqlite3.Row] = []
        for r in rows:
            m = meta.get(r["note_id"])
            if m is not None:
                out.append(m)
        return out

    finally:
        con.close()
