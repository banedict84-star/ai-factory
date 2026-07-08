"""초안 생성 — OpenAI 또는 Claude 가 cafe.yaml 설정을 읽고 카페 글(제목+본문)을 씁니다.

제공자 선택: 환경변수 CAFE_LLM(openai/anthropic). 없으면 있는 키로 자동 선택
(OPENAI_API_KEY 있으면 openai, 아니면 ANTHROPIC_API_KEY 로 anthropic).
"""
from __future__ import annotations

import json
from typing import Any

from .. import config
from .models import CafePost

ANTHROPIC_MODEL = "claude-opus-4-8"
OPENAI_MODEL_DEFAULT = "gpt-4o"  # 사람 같은 글 품질 위해 기본을 4o 로 (env CAFE_OPENAI_MODEL 로 변경 가능)

# Claude 가 반드시 이 형태의 JSON 으로만 답하도록 강제하는 스키마
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "description": "이번 글의 소재 한 줄"},
        "subject": {
            "type": "string",
            "description": "게시글 제목. 낚시성 금지, 내용을 정확히 담되 클릭하고 싶게.",
        },
        "content": {
            "type": "string",
            "description": (
                "게시글 본문. use_html=true 면 <p>, <h3>, <ul><li> 등 간단한 HTML 로 "
                "문단/소제목 구조를 만들 것. false 면 순수 텍스트에 줄바꿈만 사용."
            ),
        },
        "summary": {
            "type": "string",
            "description": "대표가 빠르게 검수할 수 있게 한두 문장으로 요약",
        },
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "글의 핵심 키워드 3~6개 (참고용)",
        },
    },
    "required": ["topic", "subject", "content", "summary", "tags"],
    "additionalProperties": False,
}


PERSONA = """# 역할
너는 10년 이상 가죽공예 업계에서 활동한 공방 운영자이자, 6만 명 규모의 가죽공예 커뮤니티를 운영하는 전문 커뮤니티 매니저다.
현장에서 직접 가죽공예를 하는 사람이 쓴 것처럼, 그러나 '실제로 배울 수 있는 알맹이'가 있는 글을 쓴다. 절대 AI가 쓴 티가 나면 안 된다.

# 대상
가죽공예 입문자, 취미반 수강생, 공방 운영자, 원데이클래스 강사, 주문제작 공방, 자격증 준비생.

# 글의 목적
회원들과 편하게 소통하면서도, 읽고 나면 '실제로 뭔가 배우는' 정보성 글을 쓴다.
"이 사람 현장 아는 사람이네" + "이건 저장해두면 진짜 쓸모 있겠다" 를 동시에 만든다.

# ★ 반드시 담을 것 (알맹이) — 가장 중요
공감·격려·분위기만으로 채우지 마라. 아래를 '구체적으로' 담아야 한다:
1) 그게 무엇인지 — 초보도 이해되게 명확한 정의/원리.
2) 어떻게 하는지 — 실제로 따라 할 수 있는 구체적 순서·방법을 단계로. 각 단계에 '왜 그렇게 하는지' 이유까지.
3) 필요한 도구·재료 — 구체적으로. 고를 때 기준까지(예: 실 두께, 가죽 두께(온스) 범위, 바늘·엣지코트·토코놀 등 실제 품목).
4) 자주 하는 실수와 해결법 — 현장에서 진짜 겪는 것과 그 대처.
"반복하면 됩니다 / 중요합니다 / 신경 쓰세요" 같은 말로 때우지 말고, 읽는 사람이 바로 써먹을 실전 정보를 넣어라. 알맹이가 글의 60% 이상이어야 한다.

# 글의 흐름
1) 공감 한두 줄로 짧게 시작 → 2) 정의/원리(그게 뭔지) → 3) 구체적 방법·순서 → 4) 필요한 도구·재료(고르는 기준까지) → 5) 자주 하는 실수와 해결 → 6) 회원들에게 질문

# 문체
말하듯 편하게. 문장은 짧게, 한 문단 1~3줄. 전문용어는 쓰되 바로 쉽게 풀어준다.
설명은 구체적으로 하되 딱딱한 설명문이 아니라, 공방에서 옆에서 알려주듯.

# 가죽공예 전문성
천연가죽·베지터블·크롬가죽·재단·패턴·새들스티치·실 두께·엣지코트·토코놀·마감·카드지갑·키링·지갑·가방 등 실제 지식을 구체적으로 활용한다.
널리 알려진 일반 지식(정의·기법·도구 종류·일반적 두께/치수 범위 등)은 구체적으로 설명해도 된다.
단, 확인되지 않은 '특정 가격·특정 브랜드 스펙·통계·수강 일정'은 지어내지 않는다.

# 절대 하지 말 것
AI처럼/광고처럼 쓰지 않는다. 과장하지 않는다.
"중요합니다 / 도움이 됩니다 / 필요합니다 / 최고입니다 / 완벽합니다 / 꼭 하세요" 같은 공허한 표현으로 문단을 때우지 않는다.

# 출력 규칙
- 이모지는 많아야 1~2개. 본문에 해시태그·링크·광고·상담유도 금지. 제목도 함께 작성.

# 글 시작 규칙 (반드시)
본문(content)의 맨 첫 문장은 항상 "안녕하세요. 베네딕의 AI비서 BENEAI(베네아이) 입니다." 로 시작하고, 한 줄 띄운 뒤 공감 한두 줄 → 곧바로 본격 정보로 들어간다.

# 댓글 유도
마지막은 회원들이 자기 경험을 말할 수 있게 질문으로 끝낸다.

# 최종 검수 (출력 전 스스로 확인)
- 읽고 나면 실제로 배우는 게 있는가? (정의·방법(단계)·도구(기준)·실수해결이 '구체적으로' 담겼는가)
- 공감/격려로만 때우지 않았는가? 알맹이가 60% 이상인가?
- AI/광고 티는 없는가? 읽기 편한가?
기준에 안 맞으면 스스로 보강한 뒤 최종 결과만 출력한다."""


def _build_prompt(
    cfg: dict[str, Any],
    topic_hint: str | None,
    recent_topics: list[str] | None,
) -> str:
    hint_line = (
        f"\n[이번 글 소재 지정] {topic_hint}\n" if topic_hint else ""
    )
    recent_line = ""
    if recent_topics:
        joined = "\n".join(f"- {t}" for t in recent_topics)
        recent_line = (
            "\n[최근 이미 올린 소재 — 겹치지 않게 다른 소재를 고르거나 새 각도로]\n"
            f"{joined}\n"
        )
    return (
        f"{PERSONA}\n\n"
        "너는 네이버 카페를 운영하는 커뮤니티 매니저야.\n"
        "아래 카페 설정을 바탕으로, 회원들에게 올릴 게시글 1개를 작성해줘.\n\n"
        f"[카페 설정]\n{json.dumps(cfg, ensure_ascii=False, indent=2)}\n"
        f"{hint_line}{recent_line}\n"
        "요구사항:\n"
        "- brand.tone 말투를 지킬 것 (친근하되 정보는 정확하게)\n"
        "- topics 목록에서 하나를 고르거나 자연스럽게 변주할 것 (소재 지정이 있으면 그것 우선)\n"
        "- 본문 길이는 post.target_length 글자 안팎으로\n"
        "- post.structured=true 면 소제목·문단으로 읽기 쉽게 구성\n"
        "- post.use_html=true 면 <p>/<h3>/<ul> 같은 간단한 HTML 태그 사용, false 면 순수 텍스트\n"
        "- 마지막에 post.call_to_action 을 자연스럽게 녹일 것\n"
        "- avoid 항목(과장 광고·낚시 제목·미확인 정보 단정·개인정보 노출)은 절대 하지 말 것\n"
    )


def _provider() -> str:
    """사용할 LLM 제공자('openai' 또는 'anthropic')를 결정합니다."""
    p = config.env("CAFE_LLM")
    if p:
        return p.strip().lower()
    if config.env("OPENAI_API_KEY"):
        return "openai"
    if config.env("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "openai"  # 기본. 키가 없으면 아래에서 안내와 함께 에러


def _generate_openai(prompt: str) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(api_key=config.env("OPENAI_API_KEY", required=True))
    model = config.env("CAFE_OPENAI_MODEL") or OPENAI_MODEL_DEFAULT
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "cafe_post",
                "schema": OUTPUT_SCHEMA,
                "strict": True,
            },
        },
    )
    return json.loads(resp.choices[0].message.content)


def _generate_anthropic(prompt: str) -> dict[str, Any]:
    import anthropic

    client = anthropic.Anthropic(api_key=config.env("ANTHROPIC_API_KEY", required=True))
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
    )
    text = next(block.text for block in response.content if block.type == "text")
    return json.loads(text)


def _complete_text_openai(prompt: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=config.env("OPENAI_API_KEY", required=True))
    model = config.env("CAFE_OPENAI_MODEL") or OPENAI_MODEL_DEFAULT
    resp = client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": prompt}]
    )
    return (resp.choices[0].message.content or "").strip()


def _complete_text_anthropic(prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=config.env("ANTHROPIC_API_KEY", required=True))
    r = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in r.content if b.type == "text").strip()


def rewrite_snippet(
    text: str, instruction: str, cfg: dict[str, Any] | None = None
) -> str:
    """드래그로 선택한 본문 일부를 지시에 맞게 고쳐 '순수 텍스트'로 반환합니다."""
    cfg = cfg or config.load_cafe_config()
    tone = cfg.get("brand", {}).get("tone", "친근하게")
    prompt = (
        "너는 가죽공예 카페 글을 다듬는 편집자야. 아래 [원문]을 [지시]에 맞게 고쳐줘.\n"
        "규칙: 고친 결과 '텍스트만' 출력(설명·따옴표·머리말 없이). "
        "HTML 태그는 넣지 말고 순수 텍스트로. 원문의 의미와 분량은 크게 벗어나지 않게. "
        f"말투는 '{tone}'.\n\n[지시] {instruction}\n\n[원문]\n{text}"
    )
    if _provider() == "anthropic":
        return _complete_text_anthropic(prompt)
    return _complete_text_openai(prompt)


def generate_post(
    topic_hint: str | None = None,
    cfg: dict[str, Any] | None = None,
    recent_topics: list[str] | None = None,
) -> CafePost:
    """카페 게시글 초안 한 건을 생성합니다.

    topic_hint 를 주면 그 소재로, 없으면 설정의 topics 풀에서 고릅니다.
    recent_topics 를 주면 최근 올린 소재와 겹치지 않게 유도합니다.
    """
    cfg = cfg or config.load_cafe_config()
    prompt = _build_prompt(cfg, topic_hint, recent_topics)

    if _provider() == "anthropic":
        data = _generate_anthropic(prompt)
    else:
        data = _generate_openai(prompt)
    return CafePost.from_dict(data)
