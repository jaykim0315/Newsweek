"""RSS 수집 모듈 – feedparser + fallback URL + 7일 필터 + URL hash dedup."""

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
SOURCES_PATH = BASE_DIR / "sources.json"
PROCESSED_URLS_PATH = BASE_DIR / "data" / "processed_urls.json"

SEVEN_DAYS = timedelta(days=7)
REQUEST_TIMEOUT = 20
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; PaperNewspaper/1.0; personal RSS reader)"
    )
}


# ---------------------------------------------------------------------------
# 내부 유틸
# ---------------------------------------------------------------------------

def _load_sources() -> list[dict]:
    with open(SOURCES_PATH, "r", encoding="utf-8") as f:
        sources = json.load(f)

    for src in sources:
        url = src.get("rss_url", "")
        if url.startswith("${") and url.endswith("}"):
            env_var = url[2:-1]
            resolved = os.getenv(env_var, "")
            if not resolved:
                logger.warning(f"환경변수 미설정: {env_var} (소스: {src['name']})")
            src["rss_url"] = resolved

    return sources


def _load_processed_urls() -> set[str]:
    if PROCESSED_URLS_PATH.exists():
        with open(PROCESSED_URLS_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def _url_hash(url: str) -> str:
    return hashlib.md5(url.strip().encode()).hexdigest()


def _parse_published(entry) -> datetime:
    """feedparser entry에서 UTC datetime 추출."""
    import calendar

    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
    return datetime.now(tz=timezone.utc)


def _extract_image_url(entry) -> str:
    """RSS entry에서 대표 이미지 URL 추출. 없으면 빈 문자열 반환."""
    # media:content
    for m in getattr(entry, "media_content", []):
        url = m.get("url", "")
        if url and (m.get("medium") == "image" or "image" in m.get("type", "")):
            return url
    # media:thumbnail
    for t in getattr(entry, "media_thumbnail", []):
        url = t.get("url", "")
        if url:
            return url
    # enclosure
    for enc in getattr(entry, "enclosures", []):
        if enc.get("type", "").startswith("image"):
            url = enc.get("url", "")
            if url:
                return url
    # <img> 태그 in content/summary
    raw = ""
    if hasattr(entry, "content") and entry.content:
        raw = entry.content[0].value
    elif hasattr(entry, "summary"):
        raw = entry.summary or ""
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw, re.IGNORECASE)
    if m:
        return m.group(1)
    return ""


def _detect_lead_image(entry) -> bool:
    return bool(_extract_image_url(entry))


def _clean_html(text: str, max_len: int = 800) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


# ---------------------------------------------------------------------------
# 피드 요청
# ---------------------------------------------------------------------------

def _fetch_feed(url: str) -> feedparser.FeedParserDict | None:
    """단일 URL을 요청해 feedparser 결과 반환. 실패 시 None."""
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        if feed.bozo and not feed.entries:
            logger.debug(f"RSS 파싱 오류: {url} – {feed.bozo_exception}")
            return None
        return feed
    except Exception as exc:
        logger.debug(f"요청 실패: {url} – {exc}")
        return None


def _entries_to_articles(
    feed: feedparser.FeedParserDict,
    source: dict,
    processed_urls: set[str],
) -> list[dict]:
    """feedparser entries → article dict 리스트 (dedup + 7일 필터 적용)."""
    cutoff = datetime.now(tz=timezone.utc) - SEVEN_DAYS
    articles = []

    for entry in feed.entries:
        url = entry.get("link", "").strip()
        if not url:
            continue

        h = _url_hash(url)
        if h in processed_urls:
            continue

        pub = _parse_published(entry)
        if pub < cutoff:
            continue

        raw_content = ""
        if hasattr(entry, "content") and entry.content:
            raw_content = entry.content[0].value
        if not raw_content:
            raw_content = getattr(entry, "summary", "") or ""

        image_url = _extract_image_url(entry)
        articles.append(
            {
                "id": h,
                "source_id": source["id"],
                "source_name": source["name"],
                "category": source["category"],
                "title": entry.get("title", "").strip(),
                "url": url,
                "summary": _clean_html(raw_content),
                "published": pub.isoformat(),
                "has_lead_image": bool(image_url),
                "image_url": image_url,
                "section_filter": source.get("section_filter", []),
            }
        )

    return articles


# ---------------------------------------------------------------------------
# 소스별 수집
# ---------------------------------------------------------------------------

def _fetch_source(source: dict, processed_urls: set[str]) -> list[dict]:
    """primary URL 시도 → 실패 시 fallback_urls 순서대로 재시도."""
    if not source.get("active", True):
        logger.info(f"[SKIP] 비활성화: {source['name']}")
        return []

    urls_to_try: list[str] = []
    primary = source.get("rss_url", "")
    if primary:
        urls_to_try.append(primary)
    urls_to_try.extend(source.get("fallback_urls", []))

    for url in urls_to_try:
        if not url:
            continue
        logger.info(f"  시도: {source['name']} → {url}")
        feed = _fetch_feed(url)
        if feed is not None and feed.entries:
            articles = _entries_to_articles(feed, source, processed_urls)
            logger.info(
                f"  [OK] {source['name']}: {len(feed.entries)}개 항목 → "
                f"{len(articles)}개 유효 (7일 이내, 미처리)"
            )
            return articles
        logger.warning(f"  [FAIL] 빈 피드 또는 오류: {url}")

    logger.error(f"  [ERROR] 모든 URL 실패: {source['name']}")
    return []


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def collect_all_sources() -> list[dict]:
    """모든 활성 소스에서 기사 수집. 소스 하나 실패해도 나머지 계속."""
    sources = _load_sources()
    processed_urls = _load_processed_urls()

    all_articles: list[dict] = []
    seen_ids: set[str] = set()

    for source in sources:
        try:
            articles = _fetch_source(source, processed_urls)
            for a in articles:
                if a["id"] not in seen_ids:
                    seen_ids.add(a["id"])
                    all_articles.append(a)
        except Exception as exc:
            logger.error(f"[EXCEPTION] {source.get('name', '?')}: {exc}")

    return all_articles
