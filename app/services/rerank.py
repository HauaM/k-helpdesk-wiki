"""
Re-ranking utilities (FR-8)

Vector 유사도 점수에 도메인 메타(업무/에러)와 최신성 가중치를 더해 재정렬한다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except Exception:  # noqa: BLE001
        return None


def rerank_results(
    results: Iterable[dict],
    *,
    domain_weight_config: dict | None = None,
    recency_weight_config: dict | None = None,
) -> list[dict]:
    """
    Re-rank vector 검색 결과에 도메인/최신성 보너스를 부여한다.

    Expected result item shape:
    {
        "item": Any,
        "score": float,  # vector similarity
        "metadata": {"business_type": str | None, "error_code": str | None, "created_at": datetime | str | None}
    }
    """

    domain_cfg = domain_weight_config or {}
    recency_cfg = recency_weight_config or {}
    bt_expected = domain_cfg.get("business_type")
    ec_expected = domain_cfg.get("error_code")
    bt_weight = float(domain_cfg.get("business_type_weight", 0.05))
    ec_weight = float(domain_cfg.get("error_code_weight", 0.05))

    recency_weight = float(recency_cfg.get("weight", 0.05))
    half_life_days = float(recency_cfg.get("half_life_days", 30))

    reranked: list[dict] = []

    for result in results:
        metadata = result.get("metadata") or {}
        base_score = float(result.get("score", 0.0))

        domain_bonus = 0.0
        if bt_expected and metadata.get("business_type") == bt_expected:
            domain_bonus += bt_weight
        if ec_expected and metadata.get("error_code") == ec_expected:
            domain_bonus += ec_weight

        recency_bonus = 0.0
        created_at = _parse_datetime(metadata.get("created_at"))
        if created_at:
            age_days = max((datetime.utcnow() - created_at).days, 0)
            recency_bonus = recency_weight / (1 + age_days / max(half_life_days, 1))

        final_score = base_score + domain_bonus + recency_bonus

        reranked.append({
            **result,
            "reranked_score": final_score,
            "domain_bonus": domain_bonus,
            "recency_bonus": recency_bonus,
        })

    reranked.sort(key=lambda x: x.get("reranked_score", x.get("score", 0.0)), reverse=True)
    return reranked
