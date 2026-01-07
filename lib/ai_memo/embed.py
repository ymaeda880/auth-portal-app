# -*- coding: utf-8 -*-
# lib/ai_memo/embed.py
from __future__ import annotations

from typing import List, Optional
import os

import streamlit as st

try:
    from openai import OpenAI
except Exception:
    OpenAI = None


def has_openai_key() -> bool:
    if "OPENAI_API_KEY" in st.secrets and str(st.secrets["OPENAI_API_KEY"]).strip():
        return True
    if os.getenv("OPENAI_API_KEY"):
        return True
    return False


def _get_openai_client() -> "OpenAI":
    if OpenAI is None:
        raise RuntimeError("openai パッケージが見つかりません。pip install openai を確認してください。")
    api_key = None
    if "OPENAI_API_KEY" in st.secrets:
        api_key = str(st.secrets["OPENAI_API_KEY"]).strip()
    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY が未設定です。")
    return OpenAI(api_key=api_key)


def embed_texts(texts: List[str], model: str = "text-embedding-3-small") -> List[List[float]]:
    """
    texts をまとめて埋め込み。返り値は list[vector]
    """
    client = _get_openai_client()
    inputs = [t if isinstance(t, str) else "" for t in texts]
    resp = client.embeddings.create(model=model, input=inputs)
    return [d.embedding for d in resp.data]
