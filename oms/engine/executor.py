"""업무 실행기 — '완료했습니다'가 아니라 실제로 산출물을 만든다.

교체 가능한 이음새 (DecisionEngine·DialogueEngine 과 같은 철학):
  - MockExecutor  : 가짜 산출물 (지금까지의 시뮬레이션 동작, 기본값)
  - ClaudeExecutor: 텍스트 산출물(기획/프롬프트/캡션 등)을 Claude 로 실제 생성

이미지·영상 생성과 업로드는 별도 미디어 제공자/계정이 필요하므로 아직 mock 으로 둔다.
ANTHROPIC_API_KEY 가 없으면 자동으로 mock 으로 폴백하여 OS 는 계속 돌아간다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..domain.models import Employee, Task
from .catalog import ARTIFACT_LABEL

# Claude 로 실제 생성할 수 있는 '텍스트' 산출물들 (나머지는 미연결 → mock)
TEXT_NEEDS = {
    "concept", "prompt", "caption",
    "brand_definition", "audience_research", "direction_proposal",
}


@dataclass
class ExecutionContext:
    task: Task
    actor: Employee
    need: str
    brand: str = ""                       # 미션/브랜드 방향
    memories: list[str] = field(default_factory=list)  # 직원·팀 기억
    artifacts: dict = field(default_factory=dict)      # 지금까지 만든 것(컨셉 등)
    persona: str = ""                     # 직원 성격


class ExecutorEngine(Protocol):
    def execute(self, ctx: ExecutionContext) -> str: ...


class MockExecutor:
    """지금까지의 동작 — 실제로 만들지 않고 '완료' 표시만."""
    kind = "mock"

    def execute(self, ctx: ExecutionContext) -> str:
        label = ARTIFACT_LABEL.get(ctx.need, ctx.need)
        return f"[{ctx.actor.name}] {label} 완료"


def _prompt_for(ctx: ExecutionContext) -> str:
    label = ARTIFACT_LABEL.get(ctx.need, ctx.need)
    mem = "\n".join(f"- {m}" for m in ctx.memories) or "- (없음)"
    concept = ctx.artifacts.get("concept", "")
    head = (
        f"너는 인스타그램 콘텐츠 팀의 '{ctx.actor.name}'이다. 성격: {ctx.persona}.\n"
        f"브랜드/미션: {ctx.brand}\n참고 기억:\n{mem}\n\n"
    )
    if ctx.need == "concept":
        return head + "위 브랜드로 올릴 인스타 릴스 1개의 컨셉을 3~4문장으로 기획해줘. 장면과 무드를 구체적으로, 담백하고 감각적으로. 한국어."
    if ctx.need == "brand_definition":
        return head + "이 계정의 리브랜딩 방향(브랜드 정의)을 4줄 이내로 정리해줘. 한국어."
    if ctx.need == "prompt":
        return head + f"아래 컨셉으로 텍스트→영상 생성 AI에 넣을 영어 프롬프트 1개를 만들어줘. 장면·카메라·조명·무드를 구체적으로.\n\n[컨셉]\n{concept}"
    if ctx.need == "caption":
        return head + f"아래 컨셉에 어울리는 인스타 캡션과 해시태그(최대 8개)를 써줘. 짧고 담백하게, 한국어.\n\n[컨셉]\n{concept}"
    if ctx.need in ("audience_research", "direction_proposal"):
        return head + "최근 성과를 가정해 간단한 인사이트와 다음 콘텐츠 방향 제안을 4줄 이내로 정리해줘. 한국어."
    return head + f"{label} 결과물을 간단히 작성해줘. 한국어."


class ClaudeExecutor:
    """텍스트 산출물을 Claude 로 실제 생성. 실패 시 mock 으로 폴백."""
    kind = "claude"

    def __init__(self, model: str = "claude-opus-4-8", fallback: ExecutorEngine | None = None):
        self.model = model
        self.fallback = fallback or MockExecutor()
        self._client = None  # 지연 초기화

    def _client_or_none(self):
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic()
            except Exception:
                self._client = False  # 키/패키지 없음
        return self._client or None

    def execute(self, ctx: ExecutionContext) -> str:
        if ctx.need not in TEXT_NEEDS:
            return self.fallback.execute(ctx)  # 영상/게시는 아직 미연결
        client = self._client_or_none()
        if client is None:
            return self.fallback.execute(ctx)
        try:
            resp = client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": _prompt_for(ctx)}],
            )
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            return text or self.fallback.execute(ctx)
        except Exception:
            return self.fallback.execute(ctx)


def build_executor(kind: str = "mock", model: str = "claude-opus-4-8") -> ExecutorEngine:
    if kind == "claude":
        return ClaudeExecutor(model=model)
    return MockExecutor()
