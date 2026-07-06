"""Dialogue Engine — 직원들이 '서로 말하게' 만든다.

★ 이번 버전의 심장. 대화는 템플릿으로 만들되, 빈칸을 직원의 '기억(Memory)'으로 채웁니다.
같은 인계라도 기억이 다르면 대사가 달라집니다 → 살아있는 느낌.

지금은 RuleBasedDialogueEngine(규칙+기억). 나중에 AIDialogueEngine 으로
같은 인터페이스로 교체하면 진짜 생성 대화가 됩니다. (AI 미연결)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

from ..domain.models import Employee, MemoryEntry, Message, Task
from .catalog import ARTIFACT_LABEL
from .personas import Persona

# 어떤 작업(need)에 어떤 기억이 관련되는지
NEED_STYLE = {"concept", "prompt", "image", "video", "brand_definition"}  # → style_pref
NEED_TONE = {"caption"}                                 # → tone_pref
NEED_METRIC = {"audience_research", "direction_proposal"}  # → metric_focus

# 자연스러운 호칭·부탁에 쓰는 짧은 명사
SHORT_NOUN = {
    "concept": "기획", "prompt": "프롬프트", "image": "이미지", "video": "영상",
    "caption": "캡션", "brand_definition": "브랜드", "audience_research": "데이터",
    "published": "게시", "direction_proposal": "방향",
}


@dataclass
class DialogueContext:
    """대화를 만들 때 참고하는 상황 + 각 직원의 기억(key→entry) + 성격."""
    task: Task
    speaker: Employee                       # 인계하는 사람
    listener: Employee                      # 인계받는 사람
    need: str                               # listener 가 만들 산출물
    next_actor: Optional[Employee] = None   # 그 다음 단계 담당(미리 준비하는 사람)
    next_need: Optional[str] = None
    mem: dict[int, dict[str, MemoryEntry]] = field(default_factory=dict)
    personas: dict[int, Persona] = field(default_factory=dict)


class DialogueEngine(Protocol):
    """교체 가능한 대화 엔진 인터페이스."""

    def generate(self, ctx: DialogueContext) -> list[Message]: ...


class RuleBasedDialogueEngine:
    """규칙+기억 기반 대화 — AI 없이.

    한 번의 인계에서 보통 3마디를 만든다:
      1) 인계 요청 (speaker → listener)  : speaker 기억으로 채색
      2) 확인 응답 (listener → speaker)  : listener 기억으로 채색
      3) 다음 담당 예고 (next_actor)     : next_actor 기억으로 채색
    """

    made_by = "rule"

    def generate(self, ctx: DialogueContext) -> list[Message]:
        sp, li = ctx.speaker, ctx.listener
        sp_p = ctx.personas.get(sp.id, Persona())
        li_p = ctx.personas.get(li.id, Persona())
        sp_mem = ctx.mem.get(sp.id, {})
        li_mem = ctx.mem.get(li.id, {})
        need_label = ARTIFACT_LABEL.get(ctx.need, ctx.need)
        short = SHORT_NOUN.get(ctx.need, need_label)
        lines: list[Message] = []

        # 1) 인계 요청 — speaker 성격 + 취향 기억
        style = None
        if ctx.need in NEED_STYLE and sp_mem.get("style_pref"):
            style = sp_mem["style_pref"].value
        lines.append(Message(text=sp_p.request(li.name, short, style),
                             from_id=sp.id, to_id=li.id, task_id=ctx.task.id))

        # 2) 확인 응답 — listener 성격 + 기억(피드백/취향)
        li_style = li_mem["style_pref"].value if (
            ctx.need in NEED_STYLE and li_mem.get("style_pref")) else None
        li_tone = li_mem["tone_pref"].value if (
            ctx.need in NEED_TONE and li_mem.get("tone_pref")) else None
        conf = li_p.confirm(short, need_label, "past_feedback" in li_mem, li_style, li_tone)
        lines.append(Message(text=conf, from_id=li.id, to_id=sp.id, task_id=ctx.task.id))

        # 3) 다음 담당 예고 — next_actor 성격
        na = ctx.next_actor
        if na and na.id not in (sp.id, li.id):
            na_p = ctx.personas.get(na.id, Persona())
            na_mem = ctx.mem.get(na.id, {})
            next_label = ARTIFACT_LABEL.get(ctx.next_need, ctx.next_need or "")
            tone = na_mem["tone_pref"].value if na_mem.get("tone_pref") else None
            lines.append(Message(text=na_p.precommit(short, next_label, tone),
                                 from_id=na.id, to_id=None, task_id=ctx.task.id))

        return lines
