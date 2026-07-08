# 네이버 카페 자동 발행 에이전트 (`src/cafe`)

카페 게시글을 **AI 가 초안 작성 → 대표가 검수 → 네이버 카페 공식 OpenAPI 로 발행**하는 에이전트입니다.
바로 올리지 않고 검수 단계를 거치므로, AI 가 쓴 글을 확인한 뒤 승인한 것만 실제로 게시됩니다.

## 흐름 한눈에 보기

```
draft   →  초안 생성(AI)         → output/cafe_drafts/ 에 pending 으로 저장
review  →  대표가 내용 확인        → approve(승인) / reject(반려)
publish →  승인된 초안만 발행       → 네이버 카페에 실제 게시
```

## 1. 사전 준비 — 네이버 앱 등록

1. [네이버 개발자센터](https://developers.naver.com/apps) 에서 **애플리케이션 등록**
2. 사용 API 에 **네이버 카페** 추가
3. **서비스 URL / Callback URL** 등록 (예: `http://localhost`)
4. 발급된 **Client ID / Client Secret** 을 `.env` 에 저장

> 카페 글쓰기 API 는 **본인이 회원이고 글쓰기 권한이 있는 카페/게시판**에만 동작합니다.

## 2. `.env` 설정

`.env.example` 을 복사해 채웁니다.

```bash
cp .env.example .env
```

```ini
ANTHROPIC_API_KEY=sk-ant-...        # 초안 생성용(Claude)
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
NAVER_CAFE_CLUB_ID=                  # 숫자 카페 ID (모르면 아래 URL_NAME 사용)
# NAVER_CAFE_URL_NAME=mycafe        # cafe.naver.com/mycafe 의 'mycafe'
NAVER_CAFE_MENU_ID=                  # 게시판(메뉴) ID
```

`config/cafe.yaml` 에서 카페 정체성·말투·소재 풀·글 규칙을 바꿀 수 있습니다.

## 3. 로그인 — refresh_token 받기

카페 글쓰기는 **로그인한 회원 토큰**이 필요합니다. 한 번만 로그인해서 장기 토큰을 받습니다.

```bash
python -m src.cafe.main login
```

- 출력된 URL 을 브라우저에서 열어 네이버 로그인/동의
- Callback URL 로 리다이렉트되면, **주소창의 전체 주소**를 복사해 터미널에 붙여넣기
- 출력된 `NAVER_REFRESH_TOKEN=...` 값을 `.env` 에 저장

## 4. 초안 생성 → 검수 → 발행

```bash
# 초안 생성 (설정 topics 에서 소재 선택)
python -m src.cafe.main draft

# 소재 직접 지정
python -m src.cafe.main draft -t "이번 주 동네 맛집 소개"

# 저장된 초안 목록 / 내용 확인
python -m src.cafe.main list
python -m src.cafe.main show 20260708-153000

# 검수: 승인 또는 반려
python -m src.cafe.main approve 20260708-153000
python -m src.cafe.main reject  20260708-153000 -n "정보 확인 필요"

# 승인된 초안 발행
python -m src.cafe.main publish 20260708-153000
```

초안을 만들면 `output/cafe_drafts/<id>.html` 미리보기 파일도 함께 생성되어
브라우저로 완성된 모습을 확인할 수 있습니다.

### 한 번에 (생성 → 대화식 승인 → 발행)

```bash
python -m src.cafe.main draft --publish
```

## 안전장치

- `publish` 는 기본적으로 **승인(approved) 된 초안만** 발행합니다. (`--force` 로만 우회)
- 이미 발행된 초안은 다시 발행되지 않습니다.
- 발행 결과(글 ID/URL, 발행 시각)는 초안 JSON 에 기록됩니다.

## 파일 구성

| 파일 | 역할 |
|---|---|
| `config/cafe.yaml` | 카페 정체성·톤·소재·규칙 설정 |
| `src/cafe/content_generator.py` | Claude 로 제목+본문 초안 생성 |
| `src/cafe/review.py` | 초안 저장/조회/승인 (검수) |
| `src/cafe/auth.py` | 네이버 OAuth 토큰 (refresh → access) |
| `src/cafe/publisher.py` | 네이버 카페 글쓰기 OpenAPI |
| `src/cafe/pipeline.py` | 초안 → 검수 → 발행 흐름 |
| `src/cafe/main.py` | CLI 진입점 |
