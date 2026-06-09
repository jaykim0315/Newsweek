#!/usr/bin/env python3
"""
data/latest.json 기사에 image_url + image_width_hint 필드를 추가한다.
(수동 실행용 래퍼 — 파이프라인은 main.py의 [5/6] 단계에서 자동 실행됨)
"""

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.image_enricher import enrich_images

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
LATEST_PATH = BASE_DIR / "data" / "latest.json"
ISSUES_DIR = BASE_DIR / "data" / "issues"


def main() -> None:
    if not LATEST_PATH.exists():
        logger.error("data/latest.json 없음. 먼저 main.py를 실행하세요.")
        sys.exit(1)

    with open(LATEST_PATH, encoding="utf-8") as f:
        data = json.load(f)

    enrich_images(data)

    with open(LATEST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("data/latest.json 저장 완료")

    issue_date = data.get("issue_date", "")
    if issue_date:
        issue_path = ISSUES_DIR / f"{issue_date}.json"
        if issue_path.exists():
            with open(issue_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"회차 파일 동기화: {issue_path.name}")


if __name__ == "__main__":
    main()
