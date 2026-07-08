"""초안 생성 — Claude 가 cafe.yaml 설정을 읽고 카페에 올릴 글(제목+본문)을 씁니다."""
from __future__ import annotations

import json
from typing import Any

import anthropic

from .. import config
from .models import CafePost

MODEL = "claude-opus-4-8"

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


def _build_prompt(cfg: dict[str, Any], topic_hint: str | None) -> str:
    hint_line = (
        f"\n[이번 글 소재 지정] {topic_hint}\n" if topic_hint else ""
    )
    return (
        "너는 네이버 카페를 운영하는 커뮤니티 매니저야.\n"
        "아래 카페 설정을 바탕으로, 회원들에게 올릴 게시글 1개를 작성해줘.\n\n"
        f"[카페 설정]\n{json.dumps(cfg, ensure_ascii=False, indent=2)}\n"
        f"{hint_line}\n"
        "요구사항:\n"
        "- brand.tone 말투를 지킬 것 (친근하되 정보는 정확하게)\n"
        "- topics 목록에서 하나를 고르거나 자연스럽게 변주할 것 (소재 지정이 있으면 그것 우선)\n"
        "- 본문 길이는 post.target_length 글자 안팎으로\n"
        "- post.structured=true 면 소제목·문단으로 읽기 쉽게 구성\n"
        "- post.use_html=true 면 <p>/<h3>/<ul> 같은 간단한 HTML 태그 사용, false 면 순수 텍스트\n"
        "- 마지막에 post.call_to_action 을 자연스럽게 녹일 것\n"
        "- avoid 항목(과장 광고·낚시 제목·미확인 정보 단정·개인정보 노출)은 절대 하지 말 것\n"
    )


def generate_post(
    topic_hint: str | None = None,
    cfg: dict[str, Any] | None = None,
) -> CafePost:
    """카페 게시글 초안 한 건을 생성합니다.

    topic_hint 를 주면 그 소재로, 없으면 설정의 topics 풀에서 고릅니다.
    """
    cfg = cfg or config.load_cafe_config()
    client = anthropic.Anthropic(api_key=config.env("ANTHROPIC_API_KEY", required=True))

    response = client.messages.create(
        model=MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": _build_prompt(cfg, topic_hint)}],
        output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
    )

    text = next(block.text for block in response.content if block.type == "text")
    data = json.loads(text)
    return CafePost.from_dict(data)
