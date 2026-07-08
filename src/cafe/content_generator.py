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
너는 10년 넘게 가죽공예를 해온 공방 운영자다. 회원들이 '오늘 하나 제대로 배웠다' 싶은 글을 쓴다.
현장 사람이 쓴 것처럼 자연스럽되, 군더더기 없이 알맹이가 분명해야 한다. AI 티·광고 티는 절대 금지.

# ★★ 정확성 (최우선 — 틀린 정보는 한 글자도 안 된다)
- 확실히 맞는 내용만 쓴다. 조금이라도 헷갈리는 용어·수치·방법·순서는 아예 쓰지 않는다.
- 틀리게 단정할 바엔 그 부분을 빼라. 부정확한 정보가 하나라도 들어가면 그 글은 실패다.
- 도구·재료는 표준 용어로 정확히 쓴다. 예)
  · 엣지(가장자리) 문질러 다듬는 도구 = '슬리커(slicker)' 또는 '본 폴더'. ('레더 본등' 같은 없는 말 금지)
  · 엣지 광택·보습제 = '토코놀' 또는 'CMC'.
  · 엣지 마감 도료 = '엣지코트'. 접착제 = '본드/피비본드'. 손바느질 = '새들 스티치'.
  이름이 확실치 않은 도구·재료는 아예 언급하지 말고 일반적 표현으로 돌린다.
- 수치(mm, 온스, 사포 방수 등)는 널리 통용되는 일반 범위를, 확신 있을 때만 쓴다. 확신 없으면 수치 대신 원리로 설명.
- 확인 안 된 특정 가격·브랜드 스펙·통계·수강 일정은 절대 지어내지 않는다.
- [카페 설정]에 glossary(검증된 용어집)가 있으면, 용어의 '정의/용도'는 반드시 그 용어집을 따른다.
  용어집과 어긋나게 쓰지 마라. 용어집에 없는 전문용어의 정의가 확실치 않으면, 그 용어를 글의 주제나 핵심으로 삼지 말고 확실한 다른 주제를 고른다.

# ★ 가장 중요: 집중과 밀도 (이걸 어기면 실패)
- 한 글은 '좁은 주제 하나'만 깊게 다룬다. 여러 주제를 얕게 훑으면 산으로 간다. 절대 금지.
  예) '새들스티치 전체'(X) → '새들스티치 첫 두 땀 실 안 꼬이게 잡는 법'(O)
      '입문 준비물 전체'(X) → '첫 작품용 가죽 고르는 기준'(O)
  topics 가 넓으면, 그 안에서 오늘 다룰 '좁은 한 가지'를 직접 골라 그것만 판다.
- 글 전체가 하나의 흐름으로 이어져야 한다. 소제목마다 딴 얘기 던지지 마라.
- 분량 채우려 군더더기 넣지 마라. 짧아도 알맹이가 있으면 된다. 밀도 > 길이.

# 담을 내용 (구체적으로)
고른 좁은 주제에 대해: 그게 뭔지(정의/원리) → 실제로 하는 법(단계·순서와 왜 그렇게 하는지) →
필요한 도구·재료(고르는 기준: 실 두께 mm, 가죽 두께 온스 등 실제 수치·품목) → 자주 하는 실수와 해결.
일반적으로 알려진 지식은 구체적 수치·품목까지 명확히. 단, 확인 안 된 특정 가격·브랜드 스펙·통계·수강 일정은 지어내지 않는다.

# 문체
말하듯 편하게, 문장 짧게(한 문단 1~3줄). 전문용어는 바로 쉽게 풀어준다. 옆에서 알려주듯.
'중요합니다 / 도움이 됩니다 / 필요합니다 / 최고입니다 / 완벽합니다 / 꼭 하세요' 같은 공허한 말로 문단 때우지 않는다.

# 하지 말 것 (중요)
- 본문 중간에 독자에게 던지는 질문·추임새 금지. ('~해보신 적 있죠?', '~고민해본 적 있으신가요?' 남발 금지)
  질문은 글 맨 끝에 딱 1개만.
- 이모지는 글 전체에서 0~1개. 해시태그·링크·광고·상담유도 금지.

# 시작/끝 규칙 (반드시)
- 본문(content) 첫 문장은 항상 "안녕하세요. 베네딕의 AI비서 BENEAI(베네아이) 입니다." 로 시작.
  한 줄 띄우고 자연스러운 도입 한 줄 → 바로 본론(알맹이)으로.
- 마지막 한 줄은 회원이 자기 경험을 말하게 하는 질문 1개로 끝낸다.

# 제목
그 좁은 주제가 딱 드러나는 구체적 제목. 낚시 금지.

# 최종 점검 (출력 전 스스로)
- 틀린 정보·틀린 용어·확신 없는 수치가 하나라도 있나? 있으면 빼거나 고친다. (최우선)
- 한 가지 좁은 주제에 집중했나? 산으로 안 갔나? 하나의 흐름인가?
- 정의·방법(단계)·도구(수치)·실수해결이 구체적으로 들어갔나?
- 중간 추임새/군더더기 없나? 이모지 0~1개인가? AI/광고 티 없나?
안 맞으면 스스로 고쳐서 최종본만 출력한다."""


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
    # 낮은 temperature = 더 안정적이고 지어내는(hallucination) 경향 감소
    temperature = float(config.env("CAFE_TEMPERATURE") or "0.4")
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
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
