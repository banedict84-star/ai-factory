"""FastAPI 앱 — 화면. 엔진/Repository 에만 의존하고 DB 를 직접 만지지 않습니다.

화면의 중심은 대시보드가 아니라 'Task 흐름'입니다:
누가 → 누구에게, 왜 넘겼는지(Decision)와 무슨 일이 있었는지(Event)를 보여줍니다.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from ..domain.models import EventType, Mode, TaskStatus
from ..engine.reactor import OrganizationEngine
from ..repository.sqlite_repo import SQLiteRepository
from ..seed import seed

DB_PATH = Path(__file__).resolve().parent.parent.parent / "ai_os.db"
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

repo = SQLiteRepository(DB_PATH)
engine = OrganizationEngine(repo)
app = FastAPI(title="AI Employee OS")


@app.on_event("startup")
def _startup() -> None:
    seed(repo)


# ── 표시용 라벨 ─────────────────────────────────────────
TASK_STATUS_LABEL = {
    TaskStatus.created: ("생성됨", "muted"),
    TaskStatus.in_progress: ("작업중", "blue"),
    TaskStatus.handed_off: ("인계됨", "amber"),
    TaskStatus.awaiting_approval: ("승인 대기", "purple"),
    TaskStatus.blocked: ("막힘", "red"),
    TaskStatus.completed: ("완료", "green"),
}

EVENT_ICON = {
    EventType.mission_created: "🎯",
    EventType.task_created: "🆕",
    EventType.task_handed_off: "🔁",
    EventType.task_worked: "🛠",
    EventType.task_completed: "✅",
    EventType.employee_blocked: "⚠️",
    EventType.approval_requested: "⏳",
    EventType.approval_granted: "👍",
    EventType.mission_done: "🏁",
}


def _emp_map() -> dict[int, object]:
    return {e.id: e for e in repo.list_employees()}


def _fmt(dt) -> str:
    return dt.strftime("%H:%M:%S")


def _event_text(ev, emps) -> str:
    p = ev.payload or {}
    if ev.type == EventType.mission_created:
        return "대표가 미션을 지시했습니다."
    if ev.type == EventType.task_created:
        return f"업무 생성: {p.get('title', '')}"
    if ev.type == EventType.task_handed_off:
        return f"{p.get('to_name', '')}에게 인계 — {p.get('reason', '')}"
    if ev.type == EventType.task_worked:
        return f"{p.get('label', '')} 완료"
    if ev.type == EventType.task_completed:
        return "업무 완료"
    if ev.type == EventType.employee_blocked:
        return f"에스컬레이션 — {p.get('reason', '')}"
    if ev.type == EventType.approval_requested:
        return "게시 전 대표 승인 요청"
    if ev.type == EventType.approval_granted:
        return "대표가 게시를 승인"
    if ev.type == EventType.mission_done:
        return "미션 완료 🏁"
    return ev.type.value


def _actor_name(actor_id, emps) -> str:
    if actor_id is None:
        return "대표"
    e = emps.get(actor_id)
    return f"{e.emoji} {e.name}" if e else "?"


def _journey(task_id: int, emps) -> list[dict]:
    """Task 가 거쳐온 담당자 사슬 (Decision 의 handoff 기록으로 구성)."""
    chain = []
    for d in repo.list_decisions(task_id):
        if d.next_assignee_id and d.action.value == "handoff":
            e = emps.get(d.next_assignee_id)
            if e:
                chain.append({"name": e.name, "emoji": e.emoji, "reason": d.reason})
    return chain


# ── 라우트 ──────────────────────────────────────────────
@app.get("/")
def home():
    return RedirectResponse("/flow")


@app.get("/flow")
def flow(request: Request):
    emps = _emp_map()
    missions = repo.list_missions()
    mission_views = []
    for m in sorted(missions, key=lambda x: x.id):
        tasks = sorted(repo.list_tasks(mission_id=m.id), key=lambda t: t.id)
        task_views = []
        for t in tasks:
            holder = emps.get(t.assignee_id)
            label, color = TASK_STATUS_LABEL.get(t.status, (t.status.value, "muted"))
            task_views.append({
                "id": t.id, "title": t.title, "kind": t.kind,
                "status_label": label, "status_color": color,
                "holder": f"{holder.emoji} {holder.name}" if holder else "-",
                "journey": _journey(t.id, emps),
                "artifacts": [k for k in t.artifacts if not k.startswith("_")],
            })
        mission_views.append({
            "id": m.id, "intent": m.intent, "status": m.status.value,
            "mode": m.mode.value, "tasks": task_views,
        })
    pending = [t.id for t in repo.list_tasks(status=TaskStatus.awaiting_approval)]
    return TEMPLATES.TemplateResponse(request, "flow.html", {
        "request": request, "missions": mission_views, "pending_count": len(pending),
    })


@app.get("/tasks/{task_id}")
def task_detail(request: Request, task_id: int):
    emps = _emp_map()
    task = repo.get_task(task_id)
    if task is None:
        return RedirectResponse("/flow")

    # Event 와 Decision 을 하나의 타임라인으로 병합
    timeline = []
    for ev in repo.list_events(task_id=task_id):
        timeline.append({
            "when": ev.created_at, "t": _fmt(ev.created_at),
            "icon": EVENT_ICON.get(ev.type, "•"),
            "actor": _actor_name(ev.actor_id, emps),
            "text": _event_text(ev, emps), "kind": "event",
        })
    for d in repo.list_decisions(task_id):
        timeline.append({
            "when": d.created_at, "t": _fmt(d.created_at),
            "icon": "🧠",
            "actor": _actor_name(d.decided_by_id, emps),
            "text": f"결정({d.action.value}): {d.reason} · made_by={d.made_by}",
            "kind": "decision",
        })
    timeline.sort(key=lambda x: x["when"])

    holder = emps.get(task.assignee_id)
    label, color = TASK_STATUS_LABEL.get(task.status, (task.status.value, "muted"))
    return TEMPLATES.TemplateResponse(request, "task_detail.html", {
        "request": request, "task": task,
        "holder": f"{holder.emoji} {holder.name}" if holder else "-",
        "status_label": label, "status_color": color,
        "journey": _journey(task_id, emps),
        "artifacts": {k: v for k, v in task.artifacts.items() if not k.startswith("_")},
        "timeline": timeline,
        "can_approve": task.status == TaskStatus.awaiting_approval,
    })


@app.get("/employees")
def employees(request: Request):
    roles = {r.id: r for r in repo.list_roles()}
    emps = _emp_map()
    views = []
    for e in repo.list_employees():
        role = roles.get(e.role_id)
        current = [
            t for t in repo.list_tasks(assignee_id=e.id)
            if t.status in (TaskStatus.handed_off, TaskStatus.in_progress,
                            TaskStatus.awaiting_approval, TaskStatus.blocked)
        ]
        reports_to = emps.get(e.reports_to_id)
        views.append({
            "emoji": e.emoji, "name": e.name, "title": e.title,
            "role": role.name if role else "-",
            "status": e.status.value,
            "reports_to": (reports_to.name if reports_to else "대표"),
            "current": [{"id": t.id, "title": t.title} for t in current],
            "memory": [m.content for m in repo.list_memory(e.id)],
        })
    return TEMPLATES.TemplateResponse(request, "employees.html", {
        "request": request, "employees": views,
    })


@app.get("/feed")
def feed(request: Request):
    emps = _emp_map()
    items = []
    for ev in repo.list_events(limit=100):
        items.append({
            "t": _fmt(ev.created_at), "icon": EVENT_ICON.get(ev.type, "•"),
            "actor": _actor_name(ev.actor_id, emps),
            "text": _event_text(ev, emps), "task_id": ev.task_id,
        })
    return TEMPLATES.TemplateResponse(request, "feed.html", {"request": request, "items": items})


# ── 액션 ────────────────────────────────────────────────
@app.post("/missions")
def create_mission(intent: str = Form(...), mode: str = Form("auto")):
    team = repo.list_teams()[0]
    engine.create_mission(team.id, intent.strip(), Mode(mode))
    return RedirectResponse("/flow", status_code=303)


@app.post("/tick")
def tick():
    engine.tick()
    return RedirectResponse("/flow", status_code=303)


@app.post("/run")
def run():
    engine.run_until_idle()
    return RedirectResponse("/flow", status_code=303)


@app.post("/tasks/{task_id}/approve")
def approve(task_id: int):
    engine.approve_task(task_id)
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)
