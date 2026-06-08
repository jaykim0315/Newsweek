"""결과 저장 – issues/*.json, latest.json, processed_urls.json 갱신."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
ISSUES_DIR = DATA_DIR / "issues"
LATEST_PATH = DATA_DIR / "latest.json"
PROCESSED_URLS_PATH = DATA_DIR / "processed_urls.json"


def save_issue(issue: dict) -> None:
    ISSUES_DIR.mkdir(parents=True, exist_ok=True)

    issue_path = ISSUES_DIR / f"{issue['issue_date']}.json"
    with open(issue_path, "w", encoding="utf-8") as f:
        json.dump(issue, f, ensure_ascii=False, indent=2)
    logger.info(f"회차 저장: {issue_path}")

    with open(LATEST_PATH, "w", encoding="utf-8") as f:
        json.dump(issue, f, ensure_ascii=False, indent=2)
    logger.info("latest.json 업데이트 완료")


def update_processed_urls(articles: list[dict]) -> None:
    existing: set[str] = set()
    if PROCESSED_URLS_PATH.exists():
        with open(PROCESSED_URLS_PATH, "r", encoding="utf-8") as f:
            existing = set(json.load(f))

    new_ids = {a["id"] for a in articles}
    merged = existing | new_ids

    with open(PROCESSED_URLS_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(merged), f, ensure_ascii=False)
    logger.info(
        f"처리 URL 기록 갱신: 총 {len(merged)}개 (신규 {len(new_ids - existing)}개)"
    )
