# 설정 가이드 — 모델 컷 자동 게시 + 반응 조회

AI가 만든 모델 컷(사진)을 인스타에 자동으로 올리고, 사람들의 반응
(좋아요·댓글·도달·저장)을 자동으로 모아 보는 전체 흐름입니다.

```
Claude(컨셉·캡션) → OpenAI(모델 컷 생성) → Imgur(공개 URL) → 인스타 게시 → 반응 조회
```

계정 관련 단계는 직접 하셔야 하고(아래 1~4), 코드/자동화는 이미 준비돼 있습니다.

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
   - `instagram_content_publish`  ← 게시에 필요
   - `instagram_manage_insights`  ← 반응(인사이트) 조회에 필요
   - `pages_read_engagement`

> 💡 본인 계정에만 게시하는 경우, 앱을 **개발(Development) 모드**로 두고
> 본인을 앱의 테스터/관리자로 등록하면 앱 심사(App Review) 없이 사용할 수 있습니다.

## 4. 필요한 값 확보

| 값 | 어디서 |
| --- | --- |
| `INSTAGRAM_ACCESS_TOKEN` | Graph API 탐색기에서 발급 (60일 장기 토큰으로 교환 권장) |
| `INSTAGRAM_ACCOUNT_ID` | `GET /me/accounts` → 페이지의 `instagram_business_account.id` |
| `ANTHROPIC_API_KEY` | https://console.anthropic.com (캡션/컨셉 기획) |
| `OPENAI_API_KEY` | https://platform.openai.com (모델 컷 이미지 생성) |
| `IMGUR_CLIENT_ID` | imgur.com → Settings → **Applications → Register an application** (익명 업로드용, 무료) |

토큰은 만료됩니다. **60일짜리 장기 토큰**으로 교환해두고 만료 전에 갱신하세요.

### 이미지 호스팅은 왜 필요한가요?

인스타 Graph API 는 로컬 파일이 아니라 **공개 URL** 을 요구합니다. 그래서 만든 컷을
어딘가 공개된 곳에 올린 뒤 그 URL 로 게시합니다. `UPLOADER` 로 방식을 고릅니다:

- `imgur` (기본·권장) : 무료. `IMGUR_CLIENT_ID` 만 있으면 됨.
- `public` : 이미 서버(예: Render `/media`)에 파일이 있을 때 → `PUBLIC_MEDIA_BASE_URL` 설정.
- `none` : 업로드 안 함 → 실제 게시는 건너뜀(생성까지만).

## 5. 로컬 테스트

```bash
cp .env.example .env   # 위 값들 채우기
pip install -r requirements.txt

# 실제 게시 없이 기획 + 모델 컷 생성까지만 확인
python -m src.main post --dry-run

# 진짜 게시 (토큰·업로더 설정 필요)
python -m src.main post

# 사람들 반응 조회 (계정에서 최근 게시물 직접 조회)
python -m src.main insights --from-account -n 10

# 잘되는 채널 분석 → 다음 기획부터 그 패턴 반영
python -m src.main benchmark @referenceaccount1 @referenceaccount2
```

`--dry-run` 은 실제 게시 없이 컨셉·캡션·이미지 생성까지만 확인합니다.
키가 하나도 없어도 이미지는 플레이스홀더로 대체되어 흐름을 확인할 수 있습니다.

## 6. 자동 스케줄 (GitHub Actions — 서버 없이)

저장소 **Settings → Secrets and variables → Actions** 에 등록:

- **Secrets**: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
  `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_ACCOUNT_ID`, `IMGUR_CLIENT_ID`
- **Variables** (선택): `UPLOADER`(기본 imgur), `EXECUTOR_IMAGE_MODEL`(기본 dall-e-3)

동작하는 워크플로:

| 파일 | 하는 일 | 기본 스케줄(한국시간) |
| --- | --- | --- |
| `.github/workflows/photo.yml` | 모델 컷 1장 기획→생성→게시 | 매일 09:00, 18:00 |
| `.github/workflows/insights.yml` | 최근 게시물 반응 리포트 | 매일 21:00 |
| `.github/workflows/post.yml` | (예전) 릴스 영상 파이프라인 | 매일 09:00, 18:00 |

각 워크플로는 **Actions 탭 → 수동 실행(Run workflow)** 버튼으로도 바로 돌려볼 수 있습니다.
스케줄이나 게시 방향(컨셉·캡션·해시태그)은 `.github/workflows/*.yml` 의 cron 과
`config/content.yaml` 을 고쳐서 조정합니다.

## 7. 잘되는 채널 따라 만들기 (벤치마크)

이미 잘 나가는 채널의 **패턴을 학습**해서 우리 콘텐츠 기획에 반영합니다.
인스타 공식 **Business Discovery API** 를 쓰므로 합법적이고 계정도 안전합니다.

```bash
# 참고 계정들을 분석 (비즈니스/크리에이터 계정만 가능, 개인 계정 불가)
python -m src.main benchmark @referenceaccount1 @referenceaccount2
```

- 분석 내용: 게시물당 평균 반응, 게시 주기, 반응 좋은 시간대(KST),
  자주 쓰는 해시태그, 반응이 특히 좋았던 게시물의 소재/톤.
- 결과는 `output/benchmark.json` 에 저장되고, 이후 `python -m src.main post` 가
  자동으로 그 패턴을 반영해 기획합니다(우리 브랜드로 **재창조** — 복사 아님).
- 계정을 매번 입력하기 싫으면 `config/content.yaml` 의 `benchmark.accounts` 에
  @아이디를 넣어두면 `benchmark` 명령이 인자 없이도 그 계정들을 씁니다.

> ⚠️ **할 수 있는 것**: 대상 계정의 공개 지표(팔로워·좋아요·댓글·캡션·시간).
> **할 수 없는 것**: 남의 계정의 도달·저장 같은 내부 인사이트, 개인 계정 조회,
> 그리고 이미지·글을 그대로 복사(저작권 + 인스타의 중복 콘텐츠 불이익).
> 필요 권한: 토큰에 `instagram_manage_insights` 가 포함돼 있어야 합니다.
