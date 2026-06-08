"""사전 필터링 – AI 호출 없이 AP신문 섹션 우선정렬 + 25건 cap."""

import logging

logger = logging.getLogger(__name__)

# AP신문 기사 중 마케팅 관련 키워드 (제목 기준)
AP_KEYWORDS: list[str] = [
    "광고", "캠페인", "브랜드", "마케팅", "PR", "콜라보", "평론",
    "CF", "TVCF", "광고주", "크리에이티브", "미디어전략",
]
APNEWS_MAX = 25


def _keyword_score(title: str) -> int:
    return sum(1 for kw in AP_KEYWORDS if kw in title)


def apply_prefilter(articles: list[dict]) -> list[dict]:
    """
    AP신문(apnews_*): 제목 키워드 매칭 점수 내림차순 → 최대 25건만 통과.
    나머지 소스: 전량 통과.
    """
    apnews: list[dict] = []
    others: list[dict] = []

    for a in articles:
        (apnews if a["source_id"].startswith("apnews") else others).append(a)

    # 키워드 점수 높은 순 → 발행일 최신 순
    apnews.sort(
        key=lambda a: (_keyword_score(a["title"]), a["published"]),
        reverse=True,
    )
    selected_apnews = apnews[:APNEWS_MAX]

    logger.info(
        f"AP신문 필터: {len(apnews)}개 → {len(selected_apnews)}개 "
        f"(키워드 우선, 최대 {APNEWS_MAX})"
    )

    filtered = others + selected_apnews
    logger.info(f"사전 필터 완료: {len(articles)}개 → {len(filtered)}개")
    return filtered
