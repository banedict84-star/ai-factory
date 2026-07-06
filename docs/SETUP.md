# 설정 가이드

인스타그램 자동 게시를 위해 준비해야 할 것들을 순서대로 정리했습니다.
계정 관련 단계는 직접 하셔야 하고, 코드/자동화는 이미 준비돼 있습니다.

## 1. 인스타그램 계정 준비

1. 인스타그램 앱에서 계정 가입
2. **설정 → 계정 유형 및 도구 → 프로페셔널 계정으로 전환** (비즈니스 또는 크리에이터)
   - ⚠️ 개인 계정으로는 공식 자동 게시가 불가능합니다.

## 2. 페이스북 페이지 만들고 연결

1. facebook.com 에서 **페이지(Page)** 생성
2. 인스타그램 앱 → 설정 → **연결된 계정** 에서 위 페이지와 연결

## 3. Meta 개발자 앱 만들기

1. https://developers.facebook.com 접속 (구글 계정으로 로그인 가능)
2. **내 앱 → 앱 만들기** → 유형: 비즈니스
3. 앱에 **Instagram Graph API** 제품 추가
4. **Graph API 탐색기** 또는 비즈니스 설정에서 아래 권한으로 토큰 발급:
   - `instagram_basic`
   - `instagram_content_publish`
   - `pages_read_engagement`
   - (필요 시) `business_management`

> 💡 본인 계정에만 게시하는 경우, 앱을 **개발(Development) 모드**로 두고
> 본인을 앱의 테스터/관리자로 등록하면 앱 심사(App Review) 없이 사용할 수 있습니다.

## 4. 필요한 값 확보

| 값 | 어디서 |
| --- | --- |
| `INSTAGRAM_ACCESS_TOKEN` | Graph API 탐색기에서 발급 (장기 토큰으로 교환 권장) |
| `INSTAGRAM_ACCOUNT_ID` | `GET /me/accounts` → 페이지의 `instagram_business_account.id` |
| `ANTHROPIC_API_KEY` | https://console.anthropic.com |

토큰은 만료됩니다. **60일짜리 장기 토큰(long-lived token)** 으로 교환해두고,
만료 전에 갱신하는 걸 권장합니다.

## 5. 로컬 테스트

```bash
cp .env.example .env   # 위 값들 채우기
pip install -r requirements.txt
python -m src.main --dry-run
```

`--dry-run` 은 실제 게시 없이 아이디어·영상 생성까지만 확인합니다.

## 6. 실제 게시를 위한 남은 2가지

1. **영상 생성 제공자**: 현재 `placeholder`(텍스트 카드)입니다.
   실제 AI 영상을 쓰려면 `src/video_generator.py` 에 제공자를 추가하고
   `VIDEO_PROVIDER` 를 바꾸세요.
2. **공개 URL 업로더**: 인스타는 공개 URL 을 요구합니다.
   `src/uploader.py` 에 S3/GCS 등의 업로더를 구현하고 `UPLOADER` 를 설정하세요.

## 7. 자동 스케줄 (GitHub Actions)

저장소 **Settings → Secrets and variables → Actions** 에 등록:
- Secrets: `ANTHROPIC_API_KEY`, `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_ACCOUNT_ID`, `VIDEO_API_KEY`
- Variables: `VIDEO_PROVIDER`, `UPLOADER`

`.github/workflows/post.yml` 이 하루 2회 자동 실행합니다.
