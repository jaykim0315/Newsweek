# Paper Newspaper – 백엔드 파이프라인

마케팅 트렌드·브랜드 사례 중심의 개인 신문 백엔드.  
RSS 수집 → AI 큐레이션(Claude Haiku 4.5) → 회차별 JSON 발행.

---

## 디렉토리 구조

```
paper-newspaper/
├── main.py                  # 파이프라인 진입점
├── sources.json             # RSS 소스 설정
├── requirements.txt
├── .env / .env.example
└── src/
    ├── collector.py         # RSS 수집 + dedup + 7일 필터
    ├── filter.py            # 사전 필터링 (AI 없음)
    ├── scorer.py            # Claude Haiku 4.5 점수 매기기
    ├── curator.py           # 카테고리별 선정 + 1면 구성
    └── storage.py           # JSON 저장

data/
├── processed_urls.json      # 처리된 URL hash (재처리 방지)
├── latest.json              # 최신 빌드 결과
└── issues/
    └── YYYY-MM-DD.json      # 회차별 결과 보관
```

---

## 설치

```bash
cd paper-newspaper
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## 환경변수 설정

`.env.example`을 복사하여 `.env` 생성:

```bash
cp .env.example .env
```

| 변수 | 필수 | 설명 |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Anthropic API 키 |
| `BRANDERKU_FEED_URL` | 선택 | 브랜더쿠 RSS URL (비공개인 경우) |
| `TAMBANG_FEED_URL` | 선택 | 탐방레터 RSS URL |

---

## 실행

```bash
python main.py
```

결과는 `data/latest.json`과 `data/issues/YYYY-MM-DD.json`에 저장됩니다.

---

## 발행 주기 자동화 (매주 월요일 오전 6시 KST)

```bash
# crontab -e
0 21 * * 0  cd /path/to/paper-newspaper && /path/to/.venv/bin/python main.py >> logs/build.log 2>&1
# (KST 06:00 = UTC 21:00 전날 일요일)
```

---

## 소스 설정 (`sources.json`)

각 소스는 다음 스키마를 따릅니다:

```jsonc
{
  "id": "unique_id",
  "name": "표시 이름",
  "category": "marketing | economy | local",
  "rss_url": "https://... 또는 ${ENV_VAR}",
  "active": true,
  "section_filter": ["S1N4"],   // 선택적: 섹션 필터
  "fallback_urls": ["https://..."]  // 선택적: primary URL 실패 시 시도
}
```

---

## 출력 구조 (`data/latest.json`)

```jsonc
{
  "issue_date": "2026-06-09",
  "issue_number": 1,
  "front_page": {
    "top": { /* 1면 톱 기사 */ },
    "sides": [ /* 1면 사이드 2개 */ ]
  },
  "sections": {
    "marketing": [ /* 상위 8개 */ ],
    "economy":   [ /* 상위 4개 */ ],
    "local":     [ /* 상위 2~3개 */ ]
  },
  "build_meta": {
    "total_articles_collected": 42,
    "ai_processed": 35,
    "estimated_cost_usd": 0.003120,
    "token_usage": { "input_tokens": 3200, "output_tokens": 580 }
  }
}
```

---

## 비용 추정

Claude Haiku 4.5 기준, 주 1회 실행 시:
- 기사 30~40건 × 5건/배치 = 약 7~8 API call
- 추정 $0.003~0.010 / 회차 → **연간 $0.15~0.50**
