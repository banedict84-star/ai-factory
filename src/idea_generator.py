"""아이디어 생성 — Claude 가 설정을 읽고 오늘 올릴 영상의 컨셉/캡션/해시태그/영상 프롬프트를 만듭니다."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import anthropic

from . import config

MODEL = "claude-opus-4-8"

# Claude 가 반드시 이 형태의 JSON 으로만 답하도록 강제하는 스키마
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "description": "이번 영상의 소재 한 줄"},
        "concept": {"type": "string", "description": "영상 컨셉/연출 설명 (2~3문장)"},
        "video_prompt": {
            "type": "string",
            "description": "영상 생성 AI 에게 넘길 영어 프롬프트. 장면·카메라·조명·분위기를 구체적으로.",
        },
        "caption": {"type": "string", "description": "인스타 캡션 (설정된 톤/길이/CTA 반영)"},
        "hashtags": {
            "type": "array",
            "items": {"type": "string"},
            "description": "해시태그 목록 (각 항목은 # 로 시작)",
        },
    },
    "required": ["topic", "concept", "video_prompt", "caption", "hashtags"],
    "additionalProperties": False,
}


@dataclass
class VideoIdea:
    topic: str
    concept: str
    video_prompt: str
    caption: str
    hashtags: list[str]

    @property
    def full_caption(self) -> str:
        """캡션 + 해시태그를 합친, 인스타에 실제로 올라갈 텍스트."""
        tags = " ".join(self.hashtags)
        return f"{self.caption}\n\n{tags}".strip()


def _build_prompt(content: dict[str, Any]) -> str:
    return (
        "너는 인스타그램 릴스 채널을 운영하는 크리에이티브 디렉터야.\n"
        "아래 채널 설정을 바탕으로, 오늘 올릴 짧은 세로 영상 1개를 기획해줘.\n\n"
        f"[채널 설정]\n{json.dumps(content, ensure_ascii=False, indent=2)}\n\n"
        "요구사항:\n"
        "- topics 목록에서 하나를 고르거나 자연스럽게 변주할 것\n"
        "- caption 은 tone/max_length/call_to_action 설정을 지킬 것\n"
        "- hashtags 는 always_include 를 포함하고 count 개수에 맞출 것\n"
        "- video_prompt 는 영상 생성 AI 용이므로 영어로, 장면을 구체적으로 묘사할 것\n"
    )


def generate_idea(content: dict[str, Any] | None = None) -> VideoIdea:
    """오늘의 영상 아이디어 한 건을 생성합니다."""
    content = content or config.load_content_config()
    client = anthropic.Anthropic(api_key=config.env("ANTHROPIC_API_KEY", required=True))

    response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": _build_prompt(content)}],
        output_config={"format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
    )

    text = next(block.text for block in response.content if block.type == "text")
    data = json.loads(text)
    return VideoIdea(
        topic=data["topic"],
        concept=data["concept"],
        video_prompt=data["video_prompt"],
        caption=data["caption"],
        hashtags=data["hashtags"],
    )
