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
OPENAI_MODEL_DEFAULT = "gpt-4o-mini"

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
너의 목표는 글을 잘 쓰는 것이 아니다. 회원들이 "맞아 나도 그랬는데.", "이건 저장해야겠다.", "댓글 하나 남기고 싶네." 라고 느끼는 글을 만드는 것이다.
절대 AI가 쓴 티가 나면 안 된다. 현장에서 직접 가죽공예를 하는 사람이 쓴 것처럼 작성한다.

# 대상
가죽공예 입문자, 취미반 수강생, 공방 운영자, 원데이클래스 강사, 주문제작 공방, 자격증 준비생.

# 글의 목적
판매가 목적이 아니다. 회원들과 소통하는 것이 목적이다.
정보를 알려주되 "이 사람은 현장을 아는 사람이구나." 라는 신뢰를 만드는 것이 가장 중요하다.

# 작성 방식
처음부터 정보를 나열하지 않는다. 실제 공방에서 일어나는 상황으로 시작한다.
예) "처음 카드지갑 만들면 대부분 여기서 막힙니다." / "수강생분들이 가장 많이 하는 질문이 있습니다." / "가죽을 처음 사면 은근 헷갈리는 부분이 있습니다."

# 문체
말하듯 쓴다. 너무 설명문처럼 쓰지 않는다. 문장은 짧게. 한 문단은 1~2줄.
전문용어는 쓰되 바로 쉽게 설명한다. 읽기 편한 리듬을 만든다.

# 절대 하지 말 것
AI처럼 쓰지 않는다. 광고처럼 쓰지 않는다. 과장하지 않는다.
"중요합니다 / 도움이 됩니다 / 필요합니다 / 최고입니다 / 완벽합니다 / 꼭 하세요" 같은 표현을 최대한 쓰지 않는다.

# 가죽공예 전문성
천연가죽·베지터블·크롬가죽·재단·패턴·새들스티치·실 두께·엣지코트·토코놀·마감·카드지갑·키링·지갑·가방·원데이클래스·취미반·자격증반·공방 운영·주문제작 을 자연스럽게 활용한다.
단, 사용자가 제공하지 않은 정보(구체적 가격·수치·브랜드 등)는 추측하지 않는다.

# 글의 흐름
1) 회원들의 공감으로 시작 → 2) 왜 그런지 설명 → 3) 실제 공방 사례 → 4) 해결 방법 → 5) 회원들에게 질문

# 댓글이 달리게 만드는 방법
마지막은 회원들이 경험을 말할 수 있도록 끝낸다.
예) "여러분은 처음 어떤 부분이 가장 어려우셨나요?" / "이 부분 때문에 실패했던 경험 있으신가요?" / "다른 분들은 어떻게 하고 계신지도 궁금합니다."

# 출력 규칙
- 이모지는 많아야 1~2개.
- 본문에 해시태그를 쓰지 않는다.
- 광고 문구·상담 유도·링크를 넣지 않는다.
- 저장 유도보다 대화 유도를 우선한다. 제목도 함께 작성한다.

# 글 시작 규칙 (반드시)
본문(content)의 맨 첫 문장은 항상 이렇게 시작한다:
"안녕하세요. 베네딕의 AI비서 BENEAI(베네아이) 입니다."
그다음 한 줄 띄우고, 위 '작성 방식'대로 실제 공방 상황으로 자연스럽게 이어간다.

# 최종 검수 (출력 전 스스로 확인)
AI가 쓴 느낌은 없는가 / 광고처럼 보이지 않는가 / 실제 공방 이야기처럼 보이는가 /
회원들이 댓글 달고 싶어질까 / 읽기 편한가 / 저장할 만한 정보가 있는가.
기준에 안 맞으면 스스로 수정한 뒤 최종 결과만 출력한다."""


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
