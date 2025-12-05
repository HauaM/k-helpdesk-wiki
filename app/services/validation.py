"""
Validation helpers (FR-9)

LLM 출력이 원문을 벗어나지 않는지 키워드/문장 단위로 검증한다.
"""

from __future__ import annotations

import re
from typing import Iterable


def validate_keywords_in_source(keywords: Iterable[str], source_text: str) -> tuple[bool, list[str]]:
    """모든 키워드가 원문에 포함되는지 검사."""

    lowered = source_text.lower()
    missing: list[str] = []
    for kw in keywords:
        if kw and kw.lower() not in lowered:
            missing.append(kw)
    return len(missing) == 0, missing


def _split_sentences(text: str) -> list[str]:
    # 간단한 문장 분리: 마침표/느낌표/물음표/줄바꿈 기준
    parts = re.split(r"[\.!?\n]+", text)
    return [p.strip() for p in parts if p.strip()]


def validate_sentences_subset_of_source(sentences_text: str, source_text: str) -> tuple[bool, list[str]]:
    """문장들이 원문 서브셋인지 검사."""

    source_lower = source_text.lower()
    missing: list[str] = []
    for sent in _split_sentences(sentences_text):
        if sent.lower() not in source_lower:
            missing.append(sent)
    return len(missing) == 0, missing
