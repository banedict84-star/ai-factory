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
    Message,
    Mission,
    MissionStatus,
    Mode,
    Task,
    TaskStatus,
    WorldState,
    now,
)
from ..repository.base import Repository
from .catalog import ARTIFACT_LABEL, PRODUCED_BY, REQUIRED_ARTIFACTS, plan_mission
from .decision import (
    DecisionContext,
    DecisionEngine,
    OrgSnapshot,
    RuleBasedDecisionEngine,
    record_decision,
)
from .dialogue import DialogueContext, DialogueEngine, RuleBasedDialogueEngine
from .executor import ExecutionContext, ExecutorEngine, MockExecutor
from .personas import Persona, persona_for


class OrganizationEngine:
    def __init__(
        self,
        repo: Repository,
        decision: DecisionEngine | None = None,
        dialogue: DialogueEngine | None = None,
        executor: ExecutorEngine | None = None,
    ):
        self.repo = repo
        self.decision = decision or RuleBasedDecisionEngine()
        self.dialogue = dialogue or RuleBasedDialogueEngine()
        self.executor = executor or MockExecutor()

    # ── 하루 시뮬레이션: 시계 ──────────────────────────────
    def world(self) -> WorldState:
        w = self.repo.get_world_state()
        if w is None:
            w = self.repo.save_world_state(WorldState())
        return w

    def _save_world(self, w: WorldState) -> None:
        self.repo.save_world_state(w)

    def _hhmm(self, minutes: int) -> str:
        minutes = max(0, min(540, minutes))  # 09:00 ~ 18:00
        return f"{9 + minutes // 60:02d}:{minutes % 60:02d}"

    def _advance_sim(self, mins: int) -> None:
        w = self.world()
        w.sim_minutes = min(540, w.sim_minutes + mins)
        self._save_world(w)

    def _say(self, from_id: int | None, text: str, *, kind: str = "chat",
             to_id: int | None = None, task_id: int | None = None) -> Message:
        w = self.world()
        msg = Message(text=text, from_id=from_id, to_id=to_id, task_id=task_id,
                      kind=kind, sim=self._hhmm(w.sim_minutes))
        return self.repo.add_message(msg)

    def _lead(self, team_id: int) -> Employee:
        return self.repo.find_employees_by_capability("decompose", team_id)[0]

    def _persona(self, emp: Employee) -> Persona:
        role = self.repo.get_role(emp.role_id)
        return persona_for(role.key if role else "")

    # ── 하루 시뮬레이션: 출근 · 아침 ────────────────────────
    def open_office(self) -> None:
        """직원들이 출근하고, 아침 인사를 나눈다. (열면 이미 살아있는 회사)"""
        w = self.world()
        if w.phase != "before":
            return
        team = self.repo.list_teams()[0]
        emps = self.repo.list_employees(team.id)
        lead = self._lead(team.id)
        # 팀장 먼저, 그다음 순서대로 출근
        order = [lead] + [e for e in emps if e.id != lead.id]

        w.sim_minutes = 0
        w.phase = "working"
        self._save_world(w)

        for i, e in enumerate(order):
            if i:
                self._advance_sim(2 + (i % 2))  # 2~3분 간격
            self._say(e.id, "출근했습니다.", kind="life")
            e.status = EmployeeStatus.idle
            self.repo.update_employee(e)

        self._advance_sim(2)
        self._say(lead.id, "좋은 아침입니다. 오늘 하루도 시작하겠습니다.", kind="life")
        self._morning_briefing(team.id, lead)

    def _morning_briefing(self, team_id: int, lead: Employee) -> None:
        """아침 스탠드업 — 각자 자기 성격대로 먼저 말한다."""
        w = self.world()
        reels = [t for t in self.repo.list_tasks(team_id=team_id) if t.kind == "reel"]
        if not reels:
            missions = self.repo.list_missions(
                team_id=team_id, status=MissionStatus.open)
            reels_planned = sum(
                1 for m in missions for k, _ in plan_mission(m.intent) if k == "reel")
        else:
            reels_planned = len(reels)

        # 팀장 먼저(전체 정리), 그다음 분석가/영상/카피/게시 순
        def by_cap(cap):
            got = self.repo.find_employees_by_capability(cap, team_id)
            return got[0] if got else None
        order = [lead, by_cap("research"), by_cap("produce_video"),
                 by_cap("write_caption"), by_cap("publish")]
        seen: set[int] = set()
        for emp in order:
            if emp is None or emp.id in seen:
                continue
            seen.add(emp.id)
            line = self._persona(emp).standup(reels_planned, w.metric)
            if line:
                self._advance_sim(1)
                self._say(emp.id, line)

    # ── 보고 문화: 대표가 물으면 직원마다 자기 스타일로 보고 ──
    def ask_status(self) -> None:
        team = self.repo.list_teams()[0]
        lead = self._lead(team.id)
        self._say(None, "현재 어떻게 되고 있나요?")  # 대표가 묻는다

        reels = [t for t in self.repo.list_tasks(team_id=team.id) if t.kind == "reel"]
        total = len(reels)
        done = sum(1 for t in reels if t.status == TaskStatus.completed)
        doing = total - done
        w = self.world()
        has_feedback = any(m.key == "past_feedback" for m in self.repo.list_memory())

        def by_cap(cap):
            got = self.repo.find_employees_by_capability(cap, team.id)
            return got[0] if got else None

        # 지호: 전체 요약
        self._advance_sim(1)
        self._say(lead.id,
                  self._persona(lead).report_overview(total, done, doing, has_feedback),
                  kind="report")
        # 태오: 데이터 중심
        taeo = by_cap("research")
        if taeo:
            self._advance_sim(1)
            self._say(taeo.id, self._persona(taeo).report_data(w.metric), kind="report")
        # 수아: 일정 중심
        sua = by_cap("publish")
        if sua:
            self._advance_sim(1)
            self._say(sua.id, self._persona(sua).report_schedule(doing), kind="report")

    # ── 퇴근 · 새 하루 ─────────────────────────────────────
    def end_day(self) -> None:
        w = self.world()
        if w.phase != "working":
            return
        team = self.repo.list_teams()[0]
        emps = self.repo.list_employees(team.id)
        lead = self._lead(team.id)
        w.sim_minutes = 540  # 18:00
        self._save_world(w)

        done = sum(1 for t in self.repo.list_tasks(team_id=team.id)
                   if t.status == TaskStatus.completed)
        self._say(lead.id, "오늘 업무를 모두 완료했습니다.", kind="report")
        if done:
            self._say(lead.id, f"완료한 업무 {done}건, 수고 많으셨습니다.", kind="report")

        self._advance_sim(5)  # 18:05
        for e in emps:
            self._say(e.id, self._persona(e).goodbye(), kind="life")
            e.status = EmployeeStatus.off
            self.repo.update_employee(e)
        w.phase = "after"
        self._save_world(w)

    def start_new_day(self) -> None:
        w = self.world()
        if w.phase != "after":
            return
        w.day += 1
        w.sim_minutes = 0
        w.phase = "before"
        w.metric = 10 + (w.day * 3) % 12  # 지표 변동(시뮬레이션)
        self._save_world(w)
        self.open_office()

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
        # 0) 출근 전이면 먼저 출근시킨다 (열면 이미 살아있게)
        w = self.world()
        if w.phase == "before":
            self.open_office()
            return "🟢 직원들이 출근했습니다."
        if w.phase == "after":
            return None  # 퇴근함 — 새 하루가 필요
        self._advance_sim(12)  # 시간이 흐른다

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

        # 직원이 자기 역량으로 산출물을 '실제로' 만든다 (Executor 이음새)
        label = ARTIFACT_LABEL.get(need, need)
        mems = ([m.content for m in self.repo.list_memory(actor.id)]
                + [m.content for m in self.repo.list_memory(None)])
        exec_ctx = ExecutionContext(
            task=task, actor=actor, need=need, brand=mission.intent,
            memories=mems, artifacts=dict(task.artifacts),
            persona=self._persona(actor).traits,
        )
        task.artifacts[need] = self.executor.execute(exec_ctx)
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
            # 직원끼리 실제로 대화하게 (기억 기반)
            self._talk(task, speaker=actor, listener=nxt, need=result.next_need)
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

    # ── 직원 간 대화 생성 (기억 기반) ────────────────────────
    def _talk(self, task: Task, speaker: Employee, listener: Employee,
              need: str | None) -> None:
        if need is None or speaker.id == listener.id:
            return  # 자기 자신에게 넘기는 초기 배정은 대화 없음

        # listener 가 need 를 만든 뒤, 그 다음 단계 담당을 미리 찾는다
        required = REQUIRED_ARTIFACTS.get(task.kind, [])
        have = set(task.artifacts.keys()) | {need}
        remaining = [a for a in required if a not in have]
        next_need = remaining[0] if remaining else None
        next_actor = None
        if next_need:
            cap = PRODUCED_BY.get(next_need)
            cands = self.repo.find_employees_by_capability(cap, task.team_id) if cap else []
            next_actor = cands[0] if cands else None

        # 관련 직원들의 기억(key)과 성격을 모은다
        mem: dict[int, dict[str, MemoryEntry]] = {}
        personas: dict[int, Persona] = {}
        for e in [speaker, listener] + ([next_actor] if next_actor else []):
            mem[e.id] = {m.key: m for m in self.repo.list_memory(e.id) if m.key}
            personas[e.id] = self._persona(e)

        ctx = DialogueContext(
            task=task, speaker=speaker, listener=listener, need=need,
            next_actor=next_actor, next_need=next_need, mem=mem, personas=personas,
        )
        sim = self._hhmm(self.world().sim_minutes)
        for msg in self.dialogue.generate(ctx):
            msg.sim = sim
            self.repo.add_message(msg)

    # ── 대표의 취향 → 직원 Memory 로 분배 ────────────────────
    def share_preference(self, team_id: int, text: str) -> list[tuple[Employee, str]]:
        """대표가 한 줄 쓰면 관련 직원의 기억으로 배포되고, 팀이 반응(대화)합니다."""
        text = text.strip()
        if not text:
            return []

        # 대표가 말한다 (from_id=None → 대표)
        self._say(None, text)

        updated: list[tuple[Employee, str]] = []

        def add_mem(emp: Employee, key: str, value: str, content: str) -> None:
            self.repo.add_memory(MemoryEntry(
                content=content, employee_id=emp.id, source="feedback",
                key=key, value=value,
            ))
            updated.append((emp, value))

        has_style = any(k in text for k in
                        ["고급", "럭셔리", "명품", "우아", "감성", "패션", "여성", "무드", "세련", "비주얼"])
        has_tone = any(k in text for k in ["짧", "간결", "문장", "캡션", "톤", "말투"])
        has_metric = any(k in text for k in ["성과", "조회", "도달", "저장", "지표", "반응"])

        if has_style:
            if any(k in text for k in ["고급", "럭셔리", "명품"]):
                val = "럭셔리"
            elif any(k in text for k in ["여성", "패션"]):
                val = "여성 패션"
            else:
                val = "감각적인"
            for cap in ("produce_video", "ideate"):
                for e in self.repo.find_employees_by_capability(cap, team_id):
                    add_mem(e, "style_pref", val, f"대표는 {val} 스타일을 선호한다.")
        if has_tone:
            for e in self.repo.find_employees_by_capability("write_caption", team_id):
                add_mem(e, "tone_pref", "짧은", "대표는 짧은 문장을 선호한다.")
        if has_metric:
            for e in self.repo.find_employees_by_capability("research", team_id):
                add_mem(e, "metric_focus", "성과", "대표는 성과 지표를 중요하게 본다.")

        # 팀장과 직원들이 반응한다
        if updated:
            leads = self.repo.find_employees_by_capability("decompose", team_id)
            if leads:
                self._say(leads[0].id, "대표님 취향 확인했습니다. 팀에 반영하겠습니다.")
                seen: set[int] = set()
                for emp, val in updated:
                    if emp.id in seen or emp.id == leads[0].id:
                        continue
                    seen.add(emp.id)
                    self._say(emp.id, self._persona(emp).ack(val), to_id=leads[0].id)
        return updated

    def _emit(self, type_: EventType, team_id: int, **kwargs) -> Event:
        event = Event(type=type_, team_id=team_id, **kwargs)
        return self.repo.add_event(event)
