"""이미지 보강 모듈 – RSS/og:image로 image_url + image_width_hint를 issue dict에 채운다."""

import logging
import os
import re
from collections import Counter
from pathlib import Path

import feedparser
import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

SOURCES_PATH = Path(__file__).parent.parent / "sources.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

BLOCKED_URL_PARTS = [
    "event.stibee.com",
    "/v2/open/",
    "unsubscribe",
    "subscribe",
    "1x1",
    "pixel.",
    "spacer",
    "tracking",
    "beacon",
    "analytics",
    "logo.",
    "icon.",
    "favicon",
    "button",
    ".gif",
]

MIN_DIM = 50
MIN_WIDTH = 200
FRONT_TOP_MIN_WIDTH = 400
CARD_MIN_WIDTH = 300


def _is_bad_url(url: str, width: int = 0, height: int = 0) -> bool:
    if not url or not url.startswith("http"):
        return True
    ul = url.lower()
    if any(part in ul for part in BLOCKED_URL_PARTS):
        return True
    if 0 < width < MIN_DIM:
        return True
    if 0 < height < MIN_DIM:
        return True
    return False


def _extract_rss_candidates(entry) -> list[tuple[str, int]]:
    """RSS entry에서 (image_url, width_hint) 후보 리스트 반환. 너비 내림차순."""
    candidates: list[tuple[str, int]] = []

    for m in getattr(entry, "media_content", []):
        url = m.get("url", "")
        if not url:
            continue
        w = int(m.get("width", 0) or 0)
        h = int(m.get("height", 0) or 0)
        is_img = m.get("medium") == "image" or "image" in m.get("type", "")
        if is_img and not _is_bad_url(url, w, h):
            candidates.append((url, w if w >= MIN_DIM else 600))

    for t in getattr(entry, "media_thumbnail", []):
        url = t.get("url", "")
        w = int(t.get("width", 0) or 0)
        if url and not _is_bad_url(url, w):
            candidates.append((url, w if w >= MIN_DIM else 200))

    for enc in getattr(entry, "enclosures", []):
        if enc.get("type", "").startswith("image"):
            url = enc.get("url", "")
            if url and not _is_bad_url(url):
                candidates.append((url, 600))

    raw = ""
    if hasattr(entry, "content") and entry.content:
        raw = entry.content[0].value
    elif hasattr(entry, "summary"):
        raw = entry.summary or ""

    if raw:
        for img_m in re.finditer(r"<img([^>]+)>", raw, re.IGNORECASE):
            attrs = img_m.group(1)
            src_m = re.search(r'src=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
            if not src_m:
                continue
            url = src_m.group(1)
            w_m = re.search(r"width=[\"']?(\d+)", attrs, re.IGNORECASE)
            h_m = re.search(r"height=[\"']?(\d+)", attrs, re.IGNORECASE)
            w = int(w_m.group(1)) if w_m else 0
            h = int(h_m.group(1)) if h_m else 0
            if not _is_bad_url(url, w, h) and (w == 0 or w >= MIN_WIDTH):
                candidates.append((url, w if w >= MIN_WIDTH else 300))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates


def _fetch_og_image(article_url: str, timeout: int = 8) -> tuple[str, int]:
    """기사 페이지의 og:image 추출. 실패 시 ('', 0) 반환."""
    try:
        resp = requests.get(article_url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        html = resp.text
        for pat in [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
        ]:
            m = re.search(pat, html, re.IGNORECASE | re.DOTALL)
            if m:
                url = m.group(1).strip()
                if url.startswith("//"):
                    url = "https:" + url
                if url.startswith("http") and not _is_bad_url(url):
                    return url, 800
    except Exception as e:
        logger.debug(f"og:image 실패 [{article_url[:50]}]: {e}")
    return "", 0


def _load_sources() -> list[dict]:
    import json
    with open(SOURCES_PATH, encoding="utf-8") as f:
        sources = json.load(f)
    for s in sources:
        url = s.get("rss_url", "")
        if url.startswith("${") and url.endswith("}"):
            s["rss_url"] = os.getenv(url[2:-1], "")
    return sources


def _collect_rss_candidates(source: dict) -> dict[str, list[tuple[str, int]]]:
    """소스 RSS에서 {article_url: [(img_url, width)]} 반환."""
    urls = [source.get("rss_url", "")] + source.get("fallback_urls", [])
    for feed_url in filter(None, urls):
        try:
            resp = requests.get(feed_url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            if not feed.entries:
                continue
            result: dict[str, list[tuple[str, int]]] = {}
            for entry in feed.entries:
                art_url = entry.get("link", "").strip()
                if art_url:
                    result[art_url] = _extract_rss_candidates(entry)
            has_imgs = sum(1 for v in result.values() if v)
            logger.info(f"  [{source['name']}] {len(feed.entries)}개 항목, {has_imgs}개 이미지 후보")
            return result
        except Exception as e:
            logger.warning(f"  [{source['name']}] {feed_url} 실패: {e}")
    return {}


def _find_duplicate_urls(rss_map: dict[str, list[tuple[str, int]]]) -> set[str]:
    counter: Counter = Counter()
    for candidates in rss_map.values():
        for url, _ in candidates:
            counter[url] += 1
    duplicates = {url for url, cnt in counter.items() if cnt >= 2}
    if duplicates:
        logger.info(f"공통 헤더 이미지 제외 ({len(duplicates)}개)")
    return duplicates


def _validate_image_url(url: str, timeout: int = 5) -> bool:
    """URL이 실제로 접근 가능한 이미지인지 검증. HEAD → GET stream fallback."""
    if not url:
        return False
    try:
        resp = requests.head(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if resp.status_code == 405:
            resp = requests.get(url, headers=HEADERS, timeout=timeout, stream=True)
            resp.close()
        if resp.status_code != 200:
            logger.debug(f"  이미지 검증 실패 HTTP {resp.status_code}: {url[:70]}")
            return False
        ct = resp.headers.get("content-type", "")
        if not ct.startswith("image/"):
            logger.debug(f"  이미지 검증 실패 content-type={ct!r}: {url[:70]}")
            return False
        return True
    except Exception as e:
        logger.debug(f"  이미지 검증 예외: {url[:70]} – {e}")
        return False


def _gather_articles(data: dict) -> list[dict]:
    articles = []
    top = data.get("front_page", {}).get("top")
    if top:
        articles.append(top)
    articles.extend(data.get("front_page", {}).get("sides", []))
    for section in data.get("sections", {}).values():
        articles.extend(section)
    return articles


def enrich_images(data: dict) -> None:
    """issue dict의 모든 기사에 image_url + image_width_hint를 인플레이스로 채운다."""
    sources = _load_sources()

    logger.info("[이미지] STEP 1: RSS 이미지 후보 수집")
    global_rss: dict[str, list[tuple[str, int]]] = {}
    for source in sources:
        if not source.get("active", True) or not source.get("rss_url"):
            continue
        logger.info(f"  RSS 수집: {source['name']}")
        global_rss.update(_collect_rss_candidates(source))

    logger.info("[이미지] STEP 2: 공통 헤더 이미지 탐지")
    bad_urls = _find_duplicate_urls(global_rss)

    logger.info("[이미지] STEP 3: 기사별 이미지 선택 + 유효성 검증")
    articles = _gather_articles(data)
    need_og: list[dict] = []

    for article in articles:
        art_url = article.get("url", "")
        candidates = global_rss.get(art_url, [])
        good = [(u, w) for u, w in candidates if u not in bad_urls]

        # 후보를 너비 내림차순으로 순서대로 검증 — 첫 번째 유효한 것 사용
        selected_url, selected_w = "", 0
        for url, w in good:
            if _validate_image_url(url):
                selected_url, selected_w = url, w
                break

        if selected_url:
            article["image_url"] = selected_url
            article["image_width_hint"] = selected_w
        else:
            article["image_url"] = None
            article["image_width_hint"] = 0
            need_og.append(article)

    logger.info(f"[이미지] STEP 4: og:image fallback ({len(need_og)}개 기사)")
    for article in need_og:
        og_url, og_w = _fetch_og_image(article.get("url", ""))
        if og_url and _validate_image_url(og_url):
            article["image_url"] = og_url
            article["image_width_hint"] = og_w
            logger.info(f"  → og:image: {article.get('headline','')[:30]} (w={og_w})")
        else:
            article["image_url"] = None
            article["image_width_hint"] = 0
            if og_url:
                logger.debug(f"  → og:image 검증 실패: {article.get('headline','')[:30]}")
            else:
                logger.debug(f"  → 이미지 없음: {article.get('headline','')[:30]}")

    has_img = sum(1 for a in articles if a.get("image_url"))
    logger.info(f"[이미지] 완료: {len(articles)}개 기사 중 {has_img}개 이미지 확보")
