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

# 어떤 작업(need)에 어떤 기억이 관련되는지
NEED_STYLE = {"concept", "video", "brand_definition"}   # → style_pref
NEED_TONE = {"caption"}                                 # → tone_pref
NEED_METRIC = {"audience_research", "direction_proposal"}  # → metric_focus

# "~ 나오면" 같은 자연스러운 말에 쓰는 짧은 명사
SHORT_NOUN = {
    "concept": "기획", "video": "영상", "caption": "캡션",
    "brand_definition": "브랜드", "audience_research": "리서치",
    "published": "게시", "direction_proposal": "방향",
}


@dataclass
class DialogueContext:
    """대화를 만들 때 참고하는 상황 + 각 직원의 기억(key→entry)."""
    task: Task
    speaker: Employee                       # 인계하는 사람
    listener: Employee                      # 인계받는 사람
    need: str                               # listener 가 만들 산출물
    next_actor: Optional[Employee] = None   # 그 다음 단계 담당(미리 준비하는 사람)
    next_need: Optional[str] = None
    mem: dict[int, dict[str, MemoryEntry]] = field(default_factory=dict)


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
        sp_mem = ctx.mem.get(sp.id, {})
        li_mem = ctx.mem.get(li.id, {})
        need_label = ARTIFACT_LABEL.get(ctx.need, ctx.need)
        lines: list[Message] = []

        # 1) 인계 요청 — speaker 의 취향 기억이 있으면 반영
        style = sp_mem.get("style_pref")
        if ctx.need in NEED_STYLE and style:
            req = f"{li.name}, 이번에는 {style.value} 느낌으로 부탁합니다."
        else:
            req = f"{li.name}, {need_label} 부탁합니다."
        lines.append(Message(text=req, from_id=sp.id, to_id=li.id, task_id=ctx.task.id))

        # 2) 확인 응답 — listener 의 기억(피드백/취향)이 있으면 반영
        if li_mem.get("past_feedback"):
            conf = "확인했습니다. 지난번 대표님 피드백도 반영하겠습니다."
        elif ctx.need in NEED_STYLE and li_mem.get("style_pref"):
            conf = f"확인했습니다. {li_mem['style_pref'].value} 무드로 만들어보겠습니다."
        elif ctx.need in NEED_TONE and li_mem.get("tone_pref"):
            conf = f"확인했습니다. {li_mem['tone_pref'].value} 문장으로 쓰겠습니다."
        else:
            conf = f"확인했습니다. {need_label} 시작하겠습니다."
        lines.append(Message(text=conf, from_id=li.id, to_id=sp.id, task_id=ctx.task.id))

        # 3) 다음 담당 예고 — 대기 중인 다음 직원이 미리 준비를 말한다
        na = ctx.next_actor
        if na and na.id not in (sp.id, li.id):
            na_mem = ctx.mem.get(na.id, {})
            next_label = ARTIFACT_LABEL.get(ctx.next_need, ctx.next_need or "")
            if ctx.next_need in NEED_TONE and na_mem.get("tone_pref"):
                short = SHORT_NOUN.get(ctx.need, need_label)
                pre = f"{short} 나오면 바로 {na_mem['tone_pref'].value} 캡션으로 작성하겠습니다."
            elif ctx.next_need == "published":
                pre = f"{next_label} 준비되면 예약해두겠습니다."
            else:
                pre = f"{next_label} 이어서 진행하겠습니다."
            lines.append(Message(text=pre, from_id=na.id, to_id=None, task_id=ctx.task.id))

        return lines
