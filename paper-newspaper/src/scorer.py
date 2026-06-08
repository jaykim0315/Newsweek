"""AI 점수 매기기 – Claude Haiku 4.5, 5건 배치, JSON 응답 파싱."""

import json
import logging
import os
import re

import anthropic
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"
BATCH_SIZE = 5

# Claude Haiku 4.5 단가 (per token)
_INPUT_PRICE = 0.80 / 1_000_000   # $0.80 / MTok
_OUTPUT_PRICE = 4.00 / 1_000_000  # $4.00 / MTok

_total_input_tokens: int = 0
_total_output_tokens: int = 0


# ---------------------------------------------------------------------------
# 클라이언트
# ---------------------------------------------------------------------------

def _get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요."
        )
    return anthropic.Anthropic(api_key=api_key)


# ---------------------------------------------------------------------------
# 프롬프트 구성
# ---------------------------------------------------------------------------

def _build_prompt(batch: list[dict]) -> str:
    articles_block = ""
    for i, a in enumerate(batch, 1):
        img_hint = "있음" if a.get("has_lead_image") else "없음"
        articles_block += (
            f"\n[{i}]\n"
            f"제목: {a['title']}\n"
            f"출처: {a['source_name']} / 카테고리: {a['category']}\n"
            f"발행일: {a['published'][:10]}\n"
            f"RSS 이미지: {img_hint}\n"
            f"내용:\n{a['summary'][:500]}\n"
            f"---"
        )

    return (
        f"다음 {len(batch)}개 기사를 평가하세요. "
        f"JSON 배열만 출력하고 다른 텍스트는 쓰지 마세요.\n\n"
        f"평가 기준 (합계 100점):\n"
        f"- relevance 0~40: 마케팅/브랜드 직접 관련성\n"
        f"- timeliness 0~15: 최신 캠페인·사건의 시의성\n"
        f"- originality 0~15: 사례 분석·인터뷰·인사이트 독창성\n"
        f"- depth 0~15: 분석이 들어간 본문 깊이\n"
        f"- newsworthy 0~15: 신문 1면에 올려도 묵직한 가치\n\n"
        f"출력 형식 (정확히 {len(batch)}개 객체 배열, 다른 텍스트 없이):\n"
        f"[\n"
        f"  {{\n"
        f'    "headline": "12자 이내 신문 헤드라인",\n'
        f'    "summary": "3줄 요약.\\n신문 기사 톤.\\n한국어로.",\n'
        f'    "keywords": ["키워드1", "키워드2", "키워드3"],\n'
        f'    "score_total": 75,\n'
        f'    "score_breakdown": {{"relevance": 30, "timeliness": 12, "originality": 12, "depth": 11, "newsworthy": 10}},\n'
        f'    "has_lead_image": true\n'
        f"  }}\n"
        f"]\n\n"
        f"기사:\n{articles_block}"
    )


# ---------------------------------------------------------------------------
# 응답 파싱
# ---------------------------------------------------------------------------

def _clean_json(text: str) -> str:
    """마크다운 펜스, 주석, trailing comma 제거 후 파싱 가능한 JSON 반환."""
    text = text.strip()
    # 마크다운 코드 펜스 제거
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:] if lines[0].startswith("```") else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        text = "\n".join(inner).strip()
    # 단일행 주석 제거 (// ...)
    text = re.sub(r"//[^\n]*", "", text)
    # 블록 주석 제거 (/* ... */)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    # trailing comma 제거 (],  })
    text = re.sub(r",\s*([}\]])", r"\1", text)
    return text.strip()


def _parse_response(text: str) -> list[dict]:
    return json.loads(_clean_json(text))


def _default_scored(article: dict) -> dict:
    return {
        **article,
        "headline": article["title"][:12],
        "summary": article["summary"][:300],
        "keywords": [],
        "score_total": 0,
        "score_breakdown": {
            "relevance": 0, "timeliness": 0, "originality": 0,
            "depth": 0, "newsworthy": 0,
        },
    }


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def score_articles(articles: list[dict]) -> list[dict]:
    """기사 리스트를 BATCH_SIZE 묶음으로 Claude Haiku에 전송, 점수 반환."""
    global _total_input_tokens, _total_output_tokens

    if not articles:
        return []

    client = _get_client()
    scored: list[dict] = []
    batches = [articles[i : i + BATCH_SIZE] for i in range(0, len(articles), BATCH_SIZE)]

    for idx, batch in enumerate(batches, 1):
        logger.info(f"  배치 {idx}/{len(batches)} – {len(batch)}개 기사 평가 중...")
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=2048,
                messages=[{"role": "user", "content": _build_prompt(batch)}],
            )

            _total_input_tokens += response.usage.input_tokens
            _total_output_tokens += response.usage.output_tokens

            scores = _parse_response(response.content[0].text)

            for article, score_data in zip(batch, scores):
                merged = {**article, **score_data}
                merged.setdefault("score_total", 0)
                merged.setdefault("headline", article["title"][:12])
                merged.setdefault("summary", article["summary"][:300])
                merged.setdefault("keywords", [])
                merged.setdefault("score_breakdown", {})
                scored.append(merged)

        except json.JSONDecodeError as exc:
            logger.error(f"  배치 {idx} JSON 파싱 실패: {exc}")
            scored.extend(_default_scored(a) for a in batch)
        except Exception as exc:
            logger.error(f"  배치 {idx} API 오류: {exc}")
            scored.extend(_default_scored(a) for a in batch)

    logger.info(
        f"토큰 사용 – 입력: {_total_input_tokens:,} / 출력: {_total_output_tokens:,}"
    )
    return scored


def get_estimated_cost_usd() -> float:
    cost = _total_input_tokens * _INPUT_PRICE + _total_output_tokens * _OUTPUT_PRICE
    return round(cost, 6)


def get_token_stats() -> dict:
    return {
        "input_tokens": _total_input_tokens,
        "output_tokens": _total_output_tokens,
    }
