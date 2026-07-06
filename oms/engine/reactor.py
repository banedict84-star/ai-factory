"""OrganizationEngine — 이벤트에 반응하며 조직을 굴리는 심장.

Workflow Engine 이 아닙니다. 정해진 순서를 실행하지 않습니다.
Mission 이 생기면 팀장이 분해하고, 각 직원이 자기 몫을 한 뒤
DecisionEngine 에게 '다음은 누구?'를 물어 넘깁니다. 그 결과로 Event 와 Decision 이 쌓입니다.
"""
from __future__ import annotations

from ..domain.models import (
    DecisionAction,
    Employee,
    EmployeeStatus,
    Event,
    EventType,
    MemoryEntry,
    Mission,
    MissionStatus,
    Mode,
    Task,
    TaskStatus,
    now,
)
from ..repository.base import Repository
from .catalog import ARTIFACT_LABEL, REQUIRED_ARTIFACTS, plan_mission
from .decision import (
    DecisionContext,
    DecisionEngine,
    OrgSnapshot,
    RuleBasedDecisionEngine,
    record_decision,
)


class OrganizationEngine:
    def __init__(self, repo: Repository, decision: DecisionEngine | None = None):
        self.repo = repo
        self.decision = decision or RuleBasedDecisionEngine()

    # ── 대표의 입력: Mission 생성 ─────────────────────────
    def create_mission(self, team_id: int, intent: str, mode: Mode) -> Mission:
        mission = Mission(team_id=team_id, intent=intent, mode=mode)
        self.repo.add_mission(mission)
        self._emit(EventType.mission_created, team_id, mission_id=mission.id,
                   payload={"intent": intent, "mode": mode.value})
        return mission

    # ── 한 스텝 진행: 조직이 한 번 반응 ────────────────────
    def tick(self) -> str | None:
        """다음으로 반응할 일이 있으면 한 번 처리하고 설명을 반환. 없으면 None.

        한 스텝 = 한 직원의 한 동작. 업무는 '시작' → '완료+인계' 두 스텝으로 진행되어
        지켜보는 사람에게 '직원이 일하고 있다'는 흐름이 보입니다.
        """
        # 1) 아직 분해되지 않은 Mission → 팀장이 분해
        open_missions = self.repo.list_missions(status=MissionStatus.open)
        if open_missions:
            return self._decompose(open_missions[0])

        # 2) 이미 시작한 업무(in_progress) → 완료하고 다음을 결정
        working = [
            t for t in self.repo.list_tasks(status=TaskStatus.in_progress)
            if t.assignee_id is not None
        ]
        if working:
            working.sort(key=lambda t: (t.updated_at, t.id or 0))
            return self._work(working[0])

        # 3) 방금 인계받은 업무(handed_off) → 담당 직원이 착수
        handed = [
            t for t in self.repo.list_tasks(status=TaskStatus.handed_off)
            if t.assignee_id is not None
        ]
        if handed:
            handed.sort(key=lambda t: (t.updated_at, t.id or 0))
            return self._start(handed[0])

        return None

    def run_until_idle(self, max_steps: int = 100) -> list[str]:
        steps = []
        for _ in range(max_steps):
            msg = self.tick()
            if msg is None:
                break
            steps.append(msg)
        return steps

    # ── 대표의 승인 ───────────────────────────────────────
    def approve_task(self, task_id: int) -> str | None:
        task = self.repo.get_task(task_id)
        if task is None or task.status != TaskStatus.awaiting_approval:
            return None
        task.artifacts["_approved"] = True
        task.status = TaskStatus.in_progress  # 이미 착수한 상태 → 게시 마무리로 재개
        task.updated_at = now()
        self.repo.update_task(task)
        self._emit(EventType.approval_granted, task.team_id, mission_id=task.mission_id,
                   task_id=task.id, payload={})
        return f"대표가 '{task.title}' 게시를 승인했습니다."

    # ── 내부: Mission 분해 ────────────────────────────────
    def _decompose(self, mission: Mission) -> str:
        leads = self.repo.find_employees_by_capability("decompose", mission.team_id)
        lead = leads[0]
        lead.status = EmployeeStatus.working
        self.repo.update_employee(lead)

        plan = plan_mission(mission.intent)
        for kind, title in plan:
            task = Task(
                mission_id=mission.id,
                team_id=mission.team_id,
                title=title,
                kind=kind,
                status=TaskStatus.created,
            )
            self.repo.add_task(task)
            self._emit(EventType.task_created, mission.team_id, mission_id=mission.id,
                       task_id=task.id, actor_id=lead.id,
                       payload={"kind": kind, "title": title})
            # 팀장이 첫 담당자를 '결정'해서 인계
            self._route(task, lead)

        self._emit(EventType.mission_decomposed, mission.team_id, mission_id=mission.id,
                   actor_id=lead.id, payload={"count": len(plan)})
        mission.status = MissionStatus.in_progress
        self.repo.update_mission(mission)
        return f"🧭 팀장 {lead.name}이(가) 미션을 {len(plan)}개 업무로 분해했습니다."

    # ── 내부: 담당 직원이 업무에 착수 (시작) ────────────────
    def _start(self, task: Task) -> str:
        actor = self.repo.get_employee(task.assignee_id)
        required = REQUIRED_ARTIFACTS.get(task.kind, [])
        missing = [a for a in required if a not in task.artifacts]
        if not missing:
            return self._work(task)  # 착수할 게 없으면 바로 마무리 판단

        need = missing[0]
        label = ARTIFACT_LABEL.get(need, need)
        actor.status = EmployeeStatus.working
        self.repo.update_employee(actor)
        task.status = TaskStatus.in_progress
        task.updated_at = now()
        self.repo.update_task(task)
        self._emit(EventType.task_started, task.team_id, mission_id=task.mission_id,
                   task_id=task.id, actor_id=actor.id,
                   payload={"need": need, "label": label})
        return f"{actor.emoji} {actor.name}: {label} 착수"

    # ── 내부: 업무를 완료하고 다음을 결정 ──────────────────
    def _work(self, task: Task) -> str:
        actor = self.repo.get_employee(task.assignee_id)
        mission = self.repo.get_mission(task.mission_id)

        required = REQUIRED_ARTIFACTS.get(task.kind, [])
        missing = [a for a in required if a not in task.artifacts]

        # 완성됨 → 결정(완료)로
        if not missing:
            return self._route_desc(task, actor)

        need = missing[0]

        # 승인 게이트: 게시 직전 + 승인 모드 + 아직 미승인
        if (
            need == "published"
            and mission.mode == Mode.approval
            and not task.artifacts.get("_approved")
        ):
            task.status = TaskStatus.awaiting_approval
            task.updated_at = now()
            self.repo.update_task(task)
            actor.status = EmployeeStatus.waiting
            self.repo.update_employee(actor)
            self._emit(EventType.approval_requested, task.team_id,
                       mission_id=task.mission_id, task_id=task.id, actor_id=actor.id,
                       payload={"awaiting": "게시 승인"})
            return f"⏳ {actor.name}이(가) 게시 전 대표 승인을 요청했습니다."

        # 직원이 자기 역량으로 산출물을 만든다
        label = ARTIFACT_LABEL.get(need, need)
        task.artifacts[need] = f"[{actor.name}] {label} 완료"
        task.updated_at = now()
        self.repo.update_task(task)
        self._emit(EventType.task_worked, task.team_id, mission_id=task.mission_id,
                   task_id=task.id, actor_id=actor.id,
                   payload={"produced": need, "label": label})

        # 다음을 결정
        desc = self._route_desc(task, actor)
        self._recompute_status(actor)
        return f"{actor.emoji} {actor.name}: {label} 완료 → {desc}"

    # ── 내부: DecisionEngine 에게 다음을 물어 적용 ──────────
    def _route(self, task: Task, actor: Employee) -> None:
        self._route_desc(task, actor)

    def _route_desc(self, task: Task, actor: Employee) -> str:
        ctx = self._context(task, actor)
        result = self.decision.decide(ctx)
        decision = record_decision(ctx, result, getattr(self.decision, "made_by", "rule"))
        self.repo.add_decision(decision)

        if result.action == DecisionAction.handoff:
            nxt = self.repo.get_employee(result.next_assignee_id)
            task.assignee_id = nxt.id
            task.status = TaskStatus.handed_off
            task.updated_at = now()
            self.repo.update_task(task)
            self._emit(EventType.task_handed_off, task.team_id,
                       mission_id=task.mission_id, task_id=task.id, actor_id=actor.id,
                       payload={"to": nxt.id, "to_name": nxt.name, "reason": result.reason})
            return f"{nxt.name}에게 인계"

        if result.action == DecisionAction.complete:
            task.status = TaskStatus.completed
            task.completed_at = now()
            task.updated_at = now()
            self.repo.update_task(task)
            self._emit(EventType.task_completed, task.team_id,
                       mission_id=task.mission_id, task_id=task.id, actor_id=actor.id,
                       payload={"reason": result.reason})
            self._recompute_status(actor)
            self._check_mission_done(task.mission_id)
            return "업무 완료 ✅"

        # escalate
        target_id = result.next_assignee_id or actor.reports_to_id
        task.assignee_id = target_id
        task.status = TaskStatus.blocked
        task.updated_at = now()
        self.repo.update_task(task)
        self._emit(EventType.employee_blocked, task.team_id,
                   mission_id=task.mission_id, task_id=task.id, actor_id=actor.id,
                   payload={"reason": result.reason, "to": target_id})
        return "상급자에게 에스컬레이션 ⚠️"

    # ── 내부: Mission 완료 확인 ───────────────────────────
    def _check_mission_done(self, mission_id: int) -> None:
        tasks = self.repo.list_tasks(mission_id=mission_id)
        if tasks and all(t.status == TaskStatus.completed for t in tasks):
            mission = self.repo.get_mission(mission_id)
            mission.status = MissionStatus.done
            self.repo.update_mission(mission)
            self._emit(EventType.mission_done, mission.team_id, mission_id=mission_id,
                       payload={"tasks": len(tasks)})
            # 팀장의 기억에 남긴다
            leads = self.repo.find_employees_by_capability("report", mission.team_id)
            if leads:
                self.repo.add_memory(MemoryEntry(
                    content=f"미션 완료: '{mission.intent[:40]}...' — 업무 {len(tasks)}건 처리.",
                    employee_id=leads[0].id,
                    source="decision",
                ))

    # ── 내부: 직원 상태 재계산 ────────────────────────────
    def _recompute_status(self, employee: Employee) -> None:
        active = self.repo.list_tasks(assignee_id=employee.id)
        busy = any(
            t.status in (TaskStatus.handed_off, TaskStatus.in_progress,
                         TaskStatus.awaiting_approval, TaskStatus.blocked)
            for t in active
        )
        employee.status = EmployeeStatus.working if busy else EmployeeStatus.idle
        self.repo.update_employee(employee)

    # ── 내부 헬퍼 ─────────────────────────────────────────
    def _context(self, task: Task, actor: Employee) -> DecisionContext:
        employees = self.repo.list_employees(task.team_id)
        roles_by_id = {r.id: r for r in self.repo.list_roles()}
        org = OrgSnapshot(employees=employees, roles_by_id=roles_by_id)
        memory = self.repo.list_memory(actor.id)
        return DecisionContext(task=task, actor=actor, org=org, memory=memory)

    def _emit(self, type_: EventType, team_id: int, **kwargs) -> Event:
        event = Event(type=type_, team_id=team_id, **kwargs)
        return self.repo.add_event(event)
