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
    EventType.mission_decomposed: "🧭",
    EventType.task_created: "🆕",
    EventType.task_handed_off: "🔁",
    EventType.task_started: "▶️",
    EventType.task_worked: "✔️",
    EventType.task_completed: "✅",
    EventType.employee_blocked: "⚠️",
    EventType.approval_requested: "⏳",
    EventType.approval_granted: "👍",
    EventType.mission_done: "🏁",
}

# 활동 피드에 자연스럽게 노출할 이벤트 (인계/생성 같은 내부 기록은 제외)
FEED_TYPES = {
    EventType.mission_created, EventType.mission_decomposed,
    EventType.task_started, EventType.task_worked,
    EventType.approval_requested, EventType.approval_granted,
    EventType.employee_blocked, EventType.mission_done,
}


def _emp_map() -> dict[int, object]:
    return {e.id: e for e in repo.list_employees()}


def _fmt(dt) -> str:
    return dt.strftime("%H:%M:%S")


def _has_batchim(word: str) -> bool:
    if not word:
        return False
    code = ord(word[-1])
    return 0xAC00 <= code <= 0xD7A3 and (code - 0xAC00) % 28 != 0


def _subj(word: str) -> str:  # 가 / 이
    return word + ("이" if _has_batchim(word) else "가")


def _obj(word: str) -> str:  # 을 / 를
    return word + ("을" if _has_batchim(word) else "를")


def _event_text(ev, emps) -> str:
    p = ev.payload or {}
    actor = emps.get(ev.actor_id) if ev.actor_id else None
    name = actor.name if actor else "대표"
    label = p.get("label", "")

    if ev.type == EventType.mission_created:
        return "대표가 미션을 지시했습니다."
    if ev.type == EventType.mission_decomposed:
        return f"{_subj(name)} 미션을 업무로 분해했습니다."
    if ev.type == EventType.task_started:
        return f"{_subj(name)} {label} 업무를 시작했습니다."
    if ev.type == EventType.task_worked:
        return f"{_subj(name)} {_obj(label)} 완료했습니다."
    if ev.type == EventType.task_completed:
        return f"{_subj(name)} 업무를 마무리했습니다."
    if ev.type == EventType.task_created:
        return f"업무 생성: {p.get('title', '')}"
    if ev.type == EventType.task_handed_off:
        return f"{p.get('to_name', '')}에게 인계 — {p.get('reason', '')}"
    if ev.type == EventType.employee_blocked:
        return f"{_subj(name)} 막혀 상급자에게 보고했습니다."
    if ev.type == EventType.approval_requested:
        return f"{_subj(name)} 게시 승인 요청을 올렸습니다."
    if ev.type == EventType.approval_granted:
        return "대표가 게시를 승인했습니다."
    if ev.type == EventType.mission_done:
        return "미션이 완료되었습니다. 🏁"
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


def _msg_view(m, emps) -> dict:
    if m.from_id is None:
        frm = {"name": "대표", "emoji": "👤", "ceo": True}
    else:
        e = emps.get(m.from_id)
        frm = {"name": e.name if e else "?", "emoji": e.emoji if e else "🤖", "ceo": False}
    to = None
    if m.to_id and emps.get(m.to_id):
        to = emps[m.to_id].name
    return {"from": frm, "to": to, "text": m.text, "sim": m.sim or _fmt(m.created_at),
            "kind": m.kind, "lines": m.text.split("\n"), "task_id": m.task_id}


PHASE_LABEL = {"before": "근무 전", "working": "근무 중", "after": "퇴근"}


# ── 라우트 ──────────────────────────────────────────────
@app.get("/")
def home(request: Request):
    """오피스 — 첫 화면. 직원들이 지금 무슨 상태이고 무슨 말을 하는지."""
    roles = {r.id: r for r in repo.list_roles()}
    emps = _emp_map()
    all_msgs = repo.list_messages()
    last_by_emp: dict[int, str] = {}
    for m in all_msgs:
        if m.from_id is not None:
            last_by_emp[m.from_id] = m.text

    roster = []
    for e in repo.list_employees():
        role = roles.get(e.role_id)
        current = [
            t for t in repo.list_tasks(assignee_id=e.id)
            if t.status in (TaskStatus.handed_off, TaskStatus.in_progress,
                            TaskStatus.awaiting_approval, TaskStatus.blocked)
        ]
        roster.append({
            "id": e.id, "emoji": e.emoji, "name": e.name, "title": e.title,
            "role": role.name if role else "-", "status": e.status.value,
            "current": current[0].title if current else None,
            "says": last_by_emp.get(e.id),
        })

    messages = [_msg_view(m, emps) for m in all_msgs[-60:]]
    w = engine.world()
    world = {
        "day": w.day, "time": engine._hhmm(w.sim_minutes),
        "phase": w.phase, "phase_label": PHASE_LABEL.get(w.phase, w.phase),
        "metric": w.metric,
    }
    return TEMPLATES.TemplateResponse(request, "office.html", {
        "request": request, "roster": roster, "messages": messages, "world": world,
    })


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
def employees_index():
    return RedirectResponse("/")  # 오피스에 직원 로스터가 있음


@app.get("/employees/{emp_id}")
def profile(request: Request, emp_id: int):
    roles = {r.id: r for r in repo.list_roles()}
    emps = _emp_map()
    e = repo.get_employee(emp_id)
    if e is None:
        return RedirectResponse("/")
    role = roles.get(e.role_id)
    reports_to = emps.get(e.reports_to_id)

    # 이 직원의 이벤트로 통계 계산
    events = [ev for ev in repo.list_events() if ev.actor_id == emp_id]
    started = {}  # task_id → 시작 시각
    done_count = 0
    durations = []
    recent_work = []
    for ev in sorted(events, key=lambda x: (x.created_at, x.id or 0)):
        if ev.type == EventType.task_started:
            started[ev.task_id] = ev.created_at
        elif ev.type == EventType.task_worked:
            done_count += 1
            label = (ev.payload or {}).get("label", "")
            recent_work.append({"task_id": ev.task_id, "label": label})
            if ev.task_id in started:
                durations.append((ev.created_at - started[ev.task_id]).total_seconds())
    avg = f"{sum(durations)/len(durations):.1f}초" if durations else "—"

    current = [
        t for t in repo.list_tasks(assignee_id=emp_id)
        if t.status in (TaskStatus.handed_off, TaskStatus.in_progress,
                        TaskStatus.awaiting_approval, TaskStatus.blocked)
    ]
    decisions = [d for d in repo.list_decisions() if d.decided_by_id == emp_id]
    decisions.sort(key=lambda d: (d.created_at, d.id or 0), reverse=True)

    return TEMPLATES.TemplateResponse(request, "profile.html", {
        "request": request,
        "e": {"emoji": e.emoji, "name": e.name, "title": e.title,
              "role": role.name if role else "-", "status": e.status.value,
              "reports_to": reports_to.name if reports_to else "대표"},
        "specialty": role.description if role and role.description else (role.name if role else "-"),
        "done_count": done_count, "avg": avg,
        "current": [{"id": t.id, "title": t.title, "status": t.status.value} for t in current],
        "recent_work": list(reversed(recent_work))[:6],
        "memory": [{"content": m.content, "key": m.key} for m in repo.list_memory(emp_id)],
        "decisions": [{"reason": d.reason, "t": _fmt(d.created_at)} for d in decisions[:6]],
    })


@app.get("/feed")
def feed(request: Request):
    emps = _emp_map()
    items = []
    for ev in repo.list_events():
        if ev.type not in FEED_TYPES:
            continue  # 인계/생성 같은 내부 기록은 활동 피드에서 숨김
        items.append({
            "t": _fmt(ev.created_at), "icon": EVENT_ICON.get(ev.type, "•"),
            "actor": _actor_name(ev.actor_id, emps),
            "text": _event_text(ev, emps), "task_id": ev.task_id,
        })
        if len(items) >= 100:
            break
    return TEMPLATES.TemplateResponse(request, "feed.html", {"request": request, "items": items})


# ── 액션 ────────────────────────────────────────────────
@app.post("/missions")
def create_mission(intent: str = Form(...), mode: str = Form("auto")):
    team = repo.list_teams()[0]
    engine.create_mission(team.id, intent.strip(), Mode(mode))
    return RedirectResponse("/flow", status_code=303)


@app.post("/preference")
def preference(intent: str = Form(...)):
    team = repo.list_teams()[0]
    engine.share_preference(team.id, intent)
    return RedirectResponse("/", status_code=303)


@app.post("/ask-status")
def ask_status():
    engine.ask_status()
    return RedirectResponse("/", status_code=303)


@app.post("/end-day")
def end_day():
    engine.end_day()
    return RedirectResponse("/", status_code=303)


@app.post("/new-day")
def new_day():
    engine.start_new_day()
    return RedirectResponse("/", status_code=303)


def _back(request: Request) -> str:
    ref = request.headers.get("referer")
    return ref if ref else "/"


@app.post("/tick")
def tick(request: Request):
    engine.tick()
    return RedirectResponse(_back(request), status_code=303)


@app.post("/run")
def run(request: Request):
    engine.run_until_idle()
    return RedirectResponse(_back(request), status_code=303)


@app.post("/tasks/{task_id}/approve")
def approve(task_id: int):
    engine.approve_task(task_id)
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)
