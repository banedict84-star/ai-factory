"""Decision Engine — "이 태스크, 다음은 누구에게?"

★ 이 파일이 프로젝트의 핵심 이음새입니다.
지금은 RuleBasedDecisionEngine(규칙)이지만, 같은 인터페이스로
AIDecisionEngine 을 만들어 한 줄만 바꿔 끼우면 AI 조직이 됩니다.

Task 에는 고정 워크플로가 없습니다. 다음 담당자는 오직 여기서 결정됩니다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

from ..domain.models import (
    Decision,
    DecisionAction,
    Employee,
    EmployeeStatus,
    MemoryEntry,
    Role,
    Task,
)
from .catalog import PRODUCED_BY, REQUIRED_ARTIFACTS


@dataclass
class OrgSnapshot:
    """결정을 내릴 때 참고하는 조직 현황."""
    employees: list[Employee]
    roles_by_id: dict[int, Role]

    def capabilities_of(self, emp: Employee) -> list[str]:
        role = self.roles_by_id.get(emp.role_id)
        return role.capabilities if role else []

    def find_by_capability(
        self, capability: str, exclude_id: Optional[int] = None
    ) -> Optional[Employee]:
        matches = [
            e
            for e in self.employees
            if capability in self.capabilities_of(e)
            and e.status != EmployeeStatus.blocked
            and e.id != exclude_id
        ]
        if not matches:
            return None
        # 대기중(idle)인 직원을 우선
        matches.sort(key=lambda e: 0 if e.status == EmployeeStatus.idle else 1)
        return matches[0]


@dataclass
class DecisionContext:
    """결정이 보는 것 = 현재 업무 상태 + 직원의 역할 + 조직 + 기억."""
    task: Task
    actor: Employee
    org: OrgSnapshot
    memory: list[MemoryEntry] = field(default_factory=list)


@dataclass
class DecisionResult:
    action: DecisionAction
    next_assignee_id: Optional[int] = None
    next_need: Optional[str] = None
    reason: str = ""


class DecisionEngine(Protocol):
    """교체 가능한 의사결정 엔진 인터페이스."""

    def decide(self, ctx: DecisionContext) -> DecisionResult: ...


class RuleBasedDecisionEngine:
    """규칙 기반 결정 — AI 없이.

    로직: '이 태스크에 아직 없는 산출물' 을 보고, 그걸 만들 역량을 가진 직원에게 넘긴다.
    없으면 상급자에게 에스컬레이션. 다 있으면 완료.
    """

    made_by = "rule"

    def decide(self, ctx: DecisionContext) -> DecisionResult:
        task = ctx.task
        required = REQUIRED_ARTIFACTS.get(task.kind, [])
        missing = [a for a in required if a not in task.artifacts]

        if not missing:
            return DecisionResult(
                action=DecisionAction.complete,
                reason="필요한 산출물이 모두 완성되어 업무를 완료합니다.",
            )

        next_artifact = missing[0]
        capability = PRODUCED_BY.get(next_artifact)
        candidate = (
            ctx.org.find_by_capability(capability) if capability else None
        )

        if candidate is None:
            return DecisionResult(
                action=DecisionAction.escalate,
                next_assignee_id=ctx.actor.reports_to_id,
                next_need=next_artifact,
                reason=f"'{next_artifact}'를 담당할 직원을 찾지 못해 상급자에게 보고합니다.",
            )

        from .catalog import ARTIFACT_LABEL

        label = ARTIFACT_LABEL.get(next_artifact, next_artifact)
        return DecisionResult(
            action=DecisionAction.handoff,
            next_assignee_id=candidate.id,
            next_need=next_artifact,
            reason=f"다음 필요 작업은 '{label}' → {capability} 역량을 가진 "
            f"{candidate.name}에게 인계합니다.",
        )


def record_decision(
    ctx: DecisionContext, result: DecisionResult, made_by: str
) -> Decision:
    """DecisionResult 를 저장 가능한 Decision 개체로."""
    return Decision(
        task_id=ctx.task.id,
        decided_by_id=ctx.actor.id,
        action=result.action,
        input={
            "task_status": ctx.task.status.value,
            "actor_role": ctx.org.capabilities_of(ctx.actor),
            "artifacts": list(ctx.task.artifacts.keys()),
            "next_need": result.next_need,
        },
        next_assignee_id=result.next_assignee_id,
        reason=result.reason,
        made_by=made_by,
    )
