#!/usr/bin/env python3
"""Paper Newspaper – 백엔드 파이프라인 (수집 → 필터 → AI 점수 → 큐레이션 → 저장)."""

import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# data/issues 디렉토리 사전 생성 (모듈 import 전)
(Path(__file__).parent / "data" / "issues").mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from src.collector import collect_all_sources
from src.curator import curate_issue
from src.filter import apply_prefilter
from src.scorer import score_articles
from src.storage import save_issue, update_processed_urls

LATEST_PATH = Path(__file__).parent / "data" / "latest.json"
BAR = "=" * 60


def _check_env() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        logging.getLogger("main").error(
            "ANTHROPIC_API_KEY 미설정. .env 파일을 확인하세요. (.env.example 참고)"
        )
        sys.exit(1)


def main() -> None:
    logger = logging.getLogger("main")
    _check_env()

    logger.info(BAR)
    logger.info("  Paper Newspaper 빌드 시작")
    logger.info(BAR)

    # 1단계: RSS 수집
    logger.info("[1/5] RSS 수집")
    articles = collect_all_sources()
    logger.info(f"      → 수집: {len(articles)}개 기사\n")

    if not articles:
        logger.warning("수집된 기사 없음. 네트워크 또는 RSS URL을 확인하세요.")
        sys.exit(0)

    # 2단계: 사전 필터링
    logger.info("[2/5] 사전 필터링 (AI 없음)")
    filtered = apply_prefilter(articles)
    logger.info(f"      → 필터 후: {len(filtered)}개\n")

    # 3단계: AI 점수 매기기
    logger.info("[3/5] AI 점수 매기기 (Claude Haiku 4.5)")
    scored = score_articles(filtered)
    logger.info(f"      → 점수 완료: {len(scored)}개\n")

    # 4단계: 큐레이션
    logger.info("[4/5] 큐레이션")
    issue = curate_issue(
        scored,
        total_collected=len(articles),
        ai_processed=len(scored),
    )
    logger.info(f"      → 이슈 #{issue['issue_number']} ({issue['issue_date']}) 구성\n")

    # 5단계: 저장
    logger.info("[5/5] 결과 저장")
    save_issue(issue)
    update_processed_urls(articles)

    meta = issue["build_meta"]
    logger.info("")
    logger.info(BAR)
    logger.info("  빌드 완료!")
    logger.info(f"  수집: {meta['total_articles_collected']}개  |  AI 처리: {meta['ai_processed']}개")
    logger.info(
        f"  토큰: 입력 {meta['token_usage']['input_tokens']:,}  / "
        f"출력 {meta['token_usage']['output_tokens']:,}"
    )
    logger.info(f"  추정 비용: ${meta['estimated_cost_usd']:.6f} USD")
    logger.info(BAR)

    # 결과 출력
    print(f"\n{'─' * 60}")
    print("  data/latest.json")
    print(f"{'─' * 60}\n")
    with open(LATEST_PATH, "r", encoding="utf-8") as f:
        print(json.dumps(json.load(f), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
