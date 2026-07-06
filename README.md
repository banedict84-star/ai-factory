# AI Factory — 인스타그램 자동 영상 게시 에이전트

설정해 둔 규칙에 따라 **AI가 영상 아이디어 → 영상 → 캡션**을 만들고,
**인스타그램에 자동으로 게시**하는 파이프라인입니다.
하루 2회, 완전 자동 실행을 목표로 합니다.

```
아이디어 생성(AI)  →  영상 생성  →  공개 URL 업로드  →  인스타 게시
   idea_generator     video_generator    uploader        instagram_publisher
                         └──────────── pipeline ────────────┘
                                        │
                              GitHub Actions (cron, 하루 2회)
```

## 전체 흐름

1. **`idea_generator`** — Claude가 `config/content.yaml`의 설정(주제·톤·해시태그 규칙)을 읽고
   오늘 올릴 영상의 **컨셉 · 캡션 · 해시태그 · 영상 프롬프트**를 생성합니다.
2. **`video_generator`** — 영상 프롬프트로 실제 영상을 만듭니다.
   지금은 `placeholder`(텍스트 카드 영상) 제공자가 기본이며, 나중에 실제 AI 영상 서비스로 교체합니다.
3. **`uploader`** — 만든 영상을 **공개적으로 접근 가능한 URL**에 올립니다
   (인스타 API가 파일이 아닌 URL을 요구하기 때문).
4. **`instagram_publisher`** — Instagram Graph API로 릴스(Reels)를 게시합니다.

## 시작하기 전에 준비할 것 (사용자 작업)

자동 게시를 하려면 아래가 필요합니다. **본인 계정에만 올리는 경우 앱 심사는 필요 없습니다.**

1. **인스타그램 프로페셔널 계정** (비즈니스 또는 크리에이터로 전환)
2. **페이스북 페이지** 생성 후 위 인스타 계정과 연결
3. **Meta 개발자 앱** 생성 → Instagram Graph API 제품 추가
4. 아래 값 확보:
   - `INSTAGRAM_ACCESS_TOKEN` (장기 토큰 권장)
   - `INSTAGRAM_ACCOUNT_ID` (IG 비즈니스 계정 ID)
5. 영상 AI 제공자 키 (선택, 실제 영상 생성 시)
6. Claude API 키 (`ANTHROPIC_API_KEY`) — 아이디어·캡션 생성용

자세한 단계는 `docs/SETUP.md`를 참고하세요.

## 로컬 실행

```bash
pip install -r requirements.txt
cp .env.example .env      # 값 채우기
python -m src.main --dry-run    # 실제 게시 없이 흐름만 확인
python -m src.main              # 실제 실행
```

## 자동 스케줄

`.github/workflows/post.yml`이 하루 2회 실행됩니다.
GitHub 저장소 Settings → Secrets에 `ANTHROPIC_API_KEY`,
`INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_ACCOUNT_ID` 등을 등록하세요.

## 지금 동작하는 것 / 아직인 것

- ✅ 아이디어·캡션·해시태그 생성 (Claude)
- ✅ 파이프라인·스케줄 뼈대, dry-run
- ✅ 인스타그램 릴스 게시 로직 (토큰만 있으면 동작)
- 🔧 영상 생성: 현재 placeholder(텍스트 카드). 실제 AI 영상 제공자 연결 필요
- 🔧 업로더: 공개 URL 호스팅 연결 필요 (S3/GCS 등)
