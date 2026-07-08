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

## 웹 배포 (Firebase / Cloud Run) + 네이버 원클릭 연결

`Dockerfile` 이 있어 컨테이너로 배포됩니다. 앱은 `$PORT`(Cloud Run 기본 8080)를
읽어 `0.0.0.0` 에 바인딩합니다. **Blaze 요금제**(외부 API 호출·Cloud Run 필요)가 켜진
Firebase/GCP 프로젝트가 필요합니다.

### 가장 쉬운 방법 — Google Cloud Shell (설치 불필요)
GCP 콘솔 우측 상단의 **Cloud Shell(터미널 아이콘)** 을 열고:

```bash
git clone https://github.com/banedict84-star/ai-factory
cd ai-factory && git checkout claude/new-conversation-5c681a

gcloud run deploy cafe-agent \
  --source . \
  --project <프로젝트ID> \
  --region asia-northeast3 \
  --allow-unauthenticated
```

- 처음 실행 시 Cloud Build/Run API 활성화 여부를 물으면 **y** 로 진행합니다.
- 완료되면 서비스 URL(예: `https://cafe-agent-xxxx-an.a.run.app`)이 출력됩니다.

### 환경변수 설정 (배포 후)
Cloud Run 콘솔 → `cafe-agent` → **수정 및 새 버전 배포 → 변수 및 보안 비밀** 에 추가:
- `ANTHROPIC_API_KEY`, `APP_PASSWORD`(접속 비번, **강력 권장**)
- `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`
- `NAVER_CAFE_CLUB_ID`(또는 `NAVER_CAFE_URL_NAME`), `NAVER_CAFE_MENU_ID`
- 연결 후 받은 `NAVER_REFRESH_TOKEN`

또는 배포 시 `--set-env-vars KEY=VALUE,KEY2=VALUE2` 로 한 번에 넣어도 됩니다.

### 네이버 연결
1. 네이버 개발자센터 → API 설정 → Callback URL 에 `https://<서비스URL>/oauth/callback` 등록
2. 대시보드 접속 → **🔗 네이버 연결** → 로그인 → 완료
3. 화면의 `refresh_token` 을 Cloud Run 환경변수와 GitHub Secrets 에 저장

### (선택) Firebase Hosting 도메인 붙이기
`firebase.json` 이 모든 요청을 Cloud Run(`cafe-agent`, `asia-northeast3`)으로 rewrite 합니다.
`firebase deploy --only hosting` 하면 `https://<프로젝트>.web.app` 로도 접속됩니다.

## 웹 배포 (Render) + 네이버 원클릭 연결

대시보드를 인터넷에 배포하면, **'네이버 연결' 버튼 한 번**으로 로그인/토큰 발급이 끝납니다
(터미널 `login` 의 URL 복붙이 필요 없음).

### 배포 순서
1. [Render](https://render.com) 가입 → **New + → Blueprint** → 이 저장소 선택
   - `render.yaml` 의 `cafe-agent` 서비스가 자동 인식됩니다.
2. 환경변수 입력 (Render 대시보드에서, 모두 `sync:false` 라 직접 입력):
   - `ANTHROPIC_API_KEY`, `APP_PASSWORD`(대시보드 접속 비번, **강력 권장**)
   - `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`
   - `NAVER_CAFE_CLUB_ID`(또는 `NAVER_CAFE_URL_NAME`), `NAVER_CAFE_MENU_ID`
3. 배포되면 도메인이 나옵니다 (예: `https://cafe-agent.onrender.com`).
4. **네이버 개발자센터 → API 설정 → Callback URL** 에
   `https://<그 도메인>/oauth/callback` 을 등록합니다. ⚠️ 정확히 일치해야 합니다.
5. 대시보드 접속 → **🔗 네이버 연결** 클릭 → 네이버 로그인/동의 → 연결 완료.
6. 화면에 나온 `refresh_token` 을 Render 의 `NAVER_REFRESH_TOKEN` 환경변수와
   (매일 자동 발행용) GitHub Secrets 에도 저장하면, 재배포·재시작 후에도 유지됩니다.

> Render 무료 플랜은 미사용 시 잠들었다가 접속하면 깨어납니다(콜드 스타트).
> 파일에 저장된 토큰은 재시작 시 사라지므로, `NAVER_REFRESH_TOKEN` 을 환경변수로 넣는 것을 권장합니다.

## 관리 대시보드 (웹)

브라우저에서 초안을 생성·검수·발행할 수 있는 대시보드가 있습니다.

```bash
python -m src.cafe.web          # http://127.0.0.1:8010
# 또는: uvicorn src.cafe.web:app --reload
```

화면 구성:
- **대시보드** (`/`) — 검수 대기 / 승인됨 / 최근 발행을 한눈에. 상단에서 새 초안 생성.
- **초안 상세** (`/draft/<id>`) — 본문 미리보기 + 승인 / 반려 / 카페에 발행 버튼.
- **설정** (`/settings`) — `config/cafe.yaml` 의 브랜드·글 규격·소재 풀을 확인.

CLI(`draft`/`approve`/`publish`)와 같은 검수 저장소(`output/cafe_drafts/`)를 공유하므로,
웹과 터미널을 섞어 써도 됩니다. 포트는 `CAFE_WEB_PORT` 로 바꿀 수 있습니다.

## 매일 1회 자동 발행 (GitHub Actions)

`.github/workflows/cafe-daily.yml` 이 **매일 한국시간 12:00(UTC 03:00)** 에
초안 생성 → 자동 발행까지 실행합니다. (검수 없이 바로 게시)

수동 명령으로도 동일하게 실행할 수 있습니다:

```bash
python -m src.cafe.main daily              # 초안 생성 → 자동 승인 → 발행
python -m src.cafe.main daily -t "소재 지정"
```

### GitHub 설정 (Secrets / Variables)

저장소 **Settings → Secrets and variables → Actions** 에 등록:

| 종류 | 이름 | 값 |
|---|---|---|
| Secret | `ANTHROPIC_API_KEY` | Claude 키 |
| Secret | `NAVER_CLIENT_ID` | 네이버 앱 클라이언트 ID |
| Secret | `NAVER_CLIENT_SECRET` | 네이버 앱 시크릿 |
| Secret | `NAVER_REFRESH_TOKEN` | `login` 으로 받은 refresh token |
| Secret | `NAVER_CAFE_CLUB_ID` | 숫자 카페 ID (있으면) |
| Secret | `NAVER_CAFE_MENU_ID` | 게시판(메뉴) ID |
| Variable | `NAVER_CAFE_URL_NAME` | (club_id 대신) 카페 URL 이름 |

- 발행 시각을 바꾸려면 워크플로의 `cron` 값을 수정하세요 (UTC 기준).
- **Actions** 탭에서 **Run workflow** 로 언제든 수동 실행할 수 있습니다.
- 매 실행마다 초안/발행 기록이 아티팩트(`cafe-drafts-*`)로 30일간 보관되어,
  **무엇이 언제 올라갔는지** 나중에 확인할 수 있습니다.

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
