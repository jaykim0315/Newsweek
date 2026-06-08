"""큐레이션 – 카테고리별 top-N 선정, 1면 구성, 중복 제거."""

import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

SECTION_LIMITS = {
    "marketing": 8,
    "economy": 4,
    "local": 3,
}
FRONT_TOP_POOL = 5    # 1면 톱 후보 pool 크기
FRONT_SIDES_COUNT = 2


def _to_output(a: dict) -> dict:
    return {
        "id": a["id"],
        "source_id": a["source_id"],
        "source_name": a["source_name"],
        "category": a["category"],
        "title": a["title"],
        "headline": a.get("headline", a["title"][:12]),
        "url": a["url"],
        "published": a["published"],
        "summary": a.get("summary", ""),
        "keywords": a.get("keywords", []),
        "score_total": a.get("score_total", 0),
        "score_breakdown": a.get("score_breakdown", {}),
        "has_lead_image": a.get("has_lead_image", False),
    }


def curate_issue(scored: list[dict], total_collected: int, ai_processed: int) -> dict:
    from .scorer import get_estimated_cost_usd, get_token_stats

    # 전체 점수 내림차순 정렬
    ranked = sorted(scored, key=lambda x: x.get("score_total", 0), reverse=True)

    # ------------------------------------------------------------------
    # 1면 톱: 상위 5개 중 marketing + has_lead_image 우선, 같으면 점수 1위
    # ------------------------------------------------------------------
    top_pool = ranked[:FRONT_TOP_POOL]
    front_top_candidates = sorted(
        top_pool,
        key=lambda x: (
            x["category"] == "marketing" and x.get("has_lead_image", False),
            x.get("score_total", 0),
        ),
        reverse=True,
    )
    front_top = front_top_candidates[0] if front_top_candidates else None
    used_ids: set[str] = {front_top["id"]} if front_top else set()

    # ------------------------------------------------------------------
    # 1면 사이드 2개: 톱 제외 전체 상위 2개
    # ------------------------------------------------------------------
    sides_pool = [a for a in ranked if a["id"] not in used_ids]
    front_sides = sides_pool[:FRONT_SIDES_COUNT]
    for a in front_sides:
        used_ids.add(a["id"])

    # ------------------------------------------------------------------
    # 카테고리 면: 1면 기사 제외, 카테고리별 top-N
    # ------------------------------------------------------------------
    def pick_section(category: str, limit: int) -> list[dict]:
        picked = []
        for a in ranked:
            if a["id"] in used_ids or a["category"] != category:
                continue
            picked.append(a)
            used_ids.add(a["id"])
            if len(picked) >= limit:
                break
        return picked

    marketing_section = pick_section("marketing", SECTION_LIMITS["marketing"])
    economy_section = pick_section("economy", SECTION_LIMITS["economy"])
    local_section = pick_section("local", SECTION_LIMITS["local"])

    # local 최소 2개 보장 로그
    if 0 < len(local_section) < 2:
        logger.warning(f"지역 면 기사 부족: {len(local_section)}개 (최소 2개 권장)")

    # ------------------------------------------------------------------
    # 회차 번호: issues/ 폴더 내 기존 JSON 파일 수 + 1
    # ------------------------------------------------------------------
    issues_dir = Path(__file__).parent.parent / "data" / "issues"
    issue_number = len(list(issues_dir.glob("*.json"))) + 1
    issue_date = datetime.now().strftime("%Y-%m-%d")

    logger.info(
        f"큐레이션 완료 – 1면(1+{len(front_sides)}), "
        f"마케팅({len(marketing_section)}), "
        f"경제({len(economy_section)}), "
        f"지역({len(local_section)})"
    )

    return {
        "issue_date": issue_date,
        "issue_number": issue_number,
        "front_page": {
            "top": _to_output(front_top) if front_top else None,
            "sides": [_to_output(a) for a in front_sides],
        },
        "sections": {
            "marketing": [_to_output(a) for a in marketing_section],
            "economy": [_to_output(a) for a in economy_section],
            "local": [_to_output(a) for a in local_section],
        },
        "build_meta": {
            "total_articles_collected": total_collected,
            "ai_processed": ai_processed,
            "estimated_cost_usd": get_estimated_cost_usd(),
            "token_usage": get_token_stats(),
        },
    }
