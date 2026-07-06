# AI Employee OS

AI 직원들이 **회사처럼** 일하는 조직 운영체제.
당신은 프로그램을 조작하는 게 아니라 **회사를 운영**합니다 — 대표로서 목표(Mission)를 주면,
AI 직원들이 그것을 업무(Task)로 나누고 서로에게 넘기며 완성합니다.

> ## 🧭 우리의 목표는 Workflow Engine이 아니라 **Organization Engine**이다.
> 워크플로 엔진은 정해진 순서를 실행한다. 조직 엔진은 **역할·이벤트·미션·업무·의사결정·기억**을
> 가진 구성원들이 상호작용하며 일을 완성한다. 그래서 인스타그램 팀뿐 아니라
> 유튜브·CRM·영업팀도 같은 엔진 위에서 운영된다.

첫 부서: **Instagram Automation Team** (고정 5인).

## 핵심 개념 (1급 객체)

| 개념 | 정체 |
|---|---|
| **Role** | 능력의 정의 — 어떤 이벤트에 반응하고 무엇을 할 수 있는지 |
| **Event** | "무슨 일이 일어났다" — 조직이 반응하는 신호이자 감사 로그 |
| **Mission** | 대표가 만드는 상위 목표 (실행 불가) |
| **Task** | 팀장이 분해한 실행 단위. 직원 사이를 이동하는 바통 |
| **Decision** | "이 태스크, 다음은 누구에게?" — **규칙 → AI 로 교체되는 이음새** |
| **Memory** | 직원의 누적된 맥락. 결정할 때 읽고 행동 후 쓴다 |

여기에 **Team**(부서)과 **Employee**(역할·직책·보고대상·상태·기억을 가진 직원).

## 아키텍처 (계층 분리)

```
oms/
  domain/       순수 모델 — DB/프레임워크 몰라도 됨
  repository/   Repository 인터페이스 + SQLite 구현  ← DB는 여기서만 (Postgres/Supabase 교체 지점)
  engine/       Decision 인터페이스 + 규칙엔진 + 반응 루프  ← AI 교체 지점
  web/          FastAPI + 화면 (Task 흐름이 중심)
```

- **DB 직접 호출은 Repository 안에만** 존재합니다. 엔진·화면은 인터페이스에만 의존 → 나중에
  Supabase/PostgreSQL 로 옮길 때 `sqlite_repo.py`만 다시 구현하면 됩니다.
- **의사결정은 `DecisionEngine` 인터페이스로 분리**되어 있습니다. 지금은
  `RuleBasedDecisionEngine`(AI 없음), 나중에 `AIDecisionEngine`으로 한 줄만 교체하면
  AI가 다음 담당자를 판단합니다. **Task 에는 고정 워크플로가 없습니다.**

## 조직이 도는 방식

```
대표 → Mission 생성  ─▶ [MissionCreated]
   팀장이 반응     ─▶ Mission 을 Task 로 분해, 첫 담당자에게
   담당 직원이 반응 ─▶ 작업 → Decision(상태+역할+다음필요) 판단
                     ├▶ 다음 담당자에게 인계  [TaskHandedOff]
                     ├▶ 완료                 [TaskCompleted]
                     └▶ 막힘 → 보고 대상에게   [EmployeeBlocked]
   (승인 모드면) 게시 전 ─▶ [ApprovalRequested] → 대표 승인
```

Task 가 움직일 때마다 **Event 1건 + Decision 1건**이 남습니다.

## 실행

```bash
pip install -r requirements.txt
python -m oms.main serve      # http://127.0.0.1:8000  (첫 실행 시 자동 시드)
# python -m oms.main reset    # DB 초기화 후 재시드
```

화면:
- **🏢 오피스** (`/`) — 첫 화면. 직원들의 하루·대화.
- **🔁 Task 흐름** (`/flow`) — 누가 → 누구에게, 왜 넘겼는지 + 산출물.
- **📡 활동** (`/feed`) — 조직 전체 Event 스트림
- 상단 **▶ 한 스텝 진행 / ⏩ 끝까지** 로 조직을 굴려봅니다.

## 실제 업무 실행 (OpenAI)

키를 넣으면 직원들이 **실제로** 기획·프롬프트·이미지·캡션을 생성합니다.

```bash
cp .env.example .env      # 편집:
#   EXECUTOR=openai
#   OPENAI_API_KEY=sk-...
python -m oms.main serve
```

- 브라우저에서 오피스를 열고 → **한 스텝 진행**을 반복 → **Task 흐름**의 릴스 Task를 클릭
- Task 상세 "산출물"에 `concept · prompt · image · caption` 이 실제로 채워집니다.
- 이미지는 기본 `gpt-image-1`, 실패 시 `dall-e-3` 자동 시도. 터미널에 성공/실패 로그가 찍힙니다.
- 키가 없으면(`EXECUTOR=mock`) 시뮬레이션으로 동작(이미지는 플레이스홀더).
- 영상 생성·인스타 업로드는 아직 미연결(다음 단계).

## 시드 데이터

- 부서: Instagram Automation Team
- 직원 5인: 지호(팀장·콘텐츠 디렉터) · 리나(영상) · 민준(카피) · 수아(게시) · 태오(분석)
- 첫 Mission: *"기존 인스타 계정을 AI Boots / AI Fashion 릴스 계정으로 리브랜딩하고,
  첫 7일 동안 하루 3개 릴스를 운영할 준비를 하라."*

## `src/` — Instagram 실행 파이프라인 (추후 연결)

`src/` 에는 실제 인스타 콘텐츠를 생성·게시하는 파이프라인 초안이 있습니다.
지금 OS 는 **실제 AI/게시 API 를 연결하지 않습니다.** 나중에 직원의 Decision/작업 자리에
이 실행기를 연결하면, AI 직원들이 실제로 콘텐츠를 만들어 올리게 됩니다.
