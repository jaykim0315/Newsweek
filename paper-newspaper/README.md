# Paper Newspaper

마케팅 트렌드·브랜드 사례 중심의 개인 신문.  
RSS 수집 → AI 큐레이션(Claude Haiku 4.5) → 이미지 보강 → Astro 프론트엔드 배포.  
매주 월요일 오전 6시 KST에 GitHub Actions가 자동으로 빌드하고 Vercel에 배포합니다.

---

## 디렉토리 구조

```
paper-newspaper/
├── main.py                  # 파이프라인 진입점 (6단계 자동 실행)
├── sources.json             # RSS 소스 설정
├── requirements.txt
├── .env / .env.example
├── scripts/
│   └── add_images.py        # 이미지 보강 수동 실행용 래퍼
├── src/
│   ├── collector.py         # RSS 수집 + dedup + 7일 필터
│   ├── filter.py            # 사전 필터링 (AI 없음)
│   ├── scorer.py            # Claude Haiku 4.5 점수 매기기
│   ├── curator.py           # 카테고리별 선정 + 1면 구성
│   ├── image_enricher.py    # RSS/og:image 이미지 보강 + URL 검증
│   └── storage.py           # JSON 저장
├── data/
│   ├── processed_urls.json  # 처리된 URL hash (재처리 방지)
│   ├── latest.json          # 최신 빌드 결과 (Vercel 빌드 시 참조)
│   └── issues/
│       └── YYYY-MM-DD.json  # 회차별 결과 보관
└── web/                     # Astro 프론트엔드
    ├── vercel.json
    ├── astro.config.mjs
    ├── tailwind.config.mjs
    └── src/
        ├── pages/index.astro
        ├── layouts/
        └── components/
```

---

## 로컬 설치 및 실행

```bash
cd paper-newspaper

# Python 환경
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 파일에 API 키 입력 (아래 환경변수 표 참조)

# 파이프라인 실행
python main.py
```

### 개발 서버

```bash
cd web
npm install
npm run dev -- --host 0.0.0.0 --port 4321
```

---

## 환경변수

| 변수 | 필수 | 설명 |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Anthropic API 키 |
| `BRANDERKU_FEED_URL` | 선택 | 브랜더쿠 RSS URL (비공개 피드인 경우) |
| `TAMBANG_FEED_URL` | 선택 | 탐방레터 RSS URL (비공개 피드인 경우) |

---

## Phase 3 – GitHub Actions + Vercel 자동 배포 설정

### 전체 흐름

```
[매주 월 06:00 KST]
GitHub Actions (cron)
  → python main.py
      (RSS 수집 → AI 점수 → 이미지 보강 → data/latest.json 저장)
  → data/ 변경사항 자동 commit & push
      → Vercel이 push 감지
          → web/ Astro 빌드 → 자동 배포
```

---

### 1단계: GitHub에 Push

```bash
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

---

### 2단계: GitHub Secrets 등록

`Settings → Secrets and variables → Actions → New repository secret`에서 3개 등록:

| Secret 이름 | 값 |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API 키 (`sk-ant-api03-...`) |
| `BRANDERKU_FEED_URL` | 브랜더쿠 비공개 RSS URL |
| `TAMBANG_FEED_URL` | 탐방레터 비공개 RSS URL |

> `BRANDERKU_FEED_URL`, `TAMBANG_FEED_URL`은 공개 URL이면 `.env`/`sources.json`에 직접 입력해도 됩니다. Secret은 비공개 URL 보호 용도입니다.

---

### 3단계: Vercel에 저장소 연결

1. [vercel.com](https://vercel.com) → **Add New Project** → GitHub 저장소 선택
2. **Configure Project** 화면에서:
   - **Root Directory**: `paper-newspaper/web` 입력 후 체크
   - **Framework Preset**: Astro (자동 감지)
   - **Build Command**: `npm run build` (기본값 유지)
   - **Output Directory**: `dist` (기본값 유지)
3. **Environment Variables**는 필요 없음 (빌드 시 `data/latest.json`만 읽음)
4. **Deploy** 클릭

> `vercel.json`이 이미 `paper-newspaper/web/`에 있어 빌드 설정이 자동으로 반영됩니다.

---

### 4단계: 첫 배포 확인 체크리스트

- [ ] Vercel 대시보드에서 빌드 로그 확인 → `✓ Build Completed`
- [ ] 배포 URL 접속 → 신문 레이아웃 정상 표시
- [ ] 1면 톱 기사 이미지 표시 확인
- [ ] 마케팅·경제·지역 면 섹션 각각 확인
- [ ] 기사 "원문 보기" 링크 클릭 → 원본 페이지 이동 확인

---

### 5단계: 워크플로우 수동 실행 테스트

1. GitHub 저장소 → **Actions** 탭
2. 왼쪽 목록에서 **주간 신문 빌드** 선택
3. **Run workflow** → **Run workflow** 클릭
4. 실행 완료 후:
   - Actions 로그에서 6단계 파이프라인 출력 확인
   - `paper-newspaper/data/latest.json`이 새 commit으로 업데이트됐는지 확인
   - Vercel 대시보드에서 자동 재배포 트리거됐는지 확인

---

## 출력 구조 (`data/latest.json`)

```jsonc
{
  "issue_date": "2026-06-09",
  "issue_number": 1,
  "front_page": {
    "top": { /* 1면 톱 기사 (image_url, image_width_hint 포함) */ },
    "sides": [ /* 1면 사이드 2개 */ ]
  },
  "sections": {
    "marketing": [ /* 상위 8개 */ ],
    "economy":   [ /* 상위 4개 */ ],
    "local":     [ /* 상위 2~3개 */ ]
  },
  "build_meta": {
    "total_articles_collected": 23,
    "ai_processed": 23,
    "estimated_cost_usd": 0.035,
    "token_usage": { "input_tokens": 14165, "output_tokens": 5972 }
  }
}
```

---

## 비용 추정

Claude Haiku 4.5 기준, 주 1회 실행 시:
- 기사 20~30건 × 5건/배치 = 약 5~7 API call
- 추정 $0.010~0.040 / 회차 → **연간 $0.50~2.00**
