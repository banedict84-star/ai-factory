"""SQLite 구현체 — MVP 저장소.

각 개체를 (id, data=JSON) 형태로 저장합니다. 필터링은 소량 데이터 기준으로
파이썬에서 수행합니다. 나중에 Postgres/Supabase 로 옮길 때는 이 파일만
같은 인터페이스로 다시 구현하면 됩니다 (엔진/화면은 손대지 않음).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, TypeVar

from ..domain.models import (
    Decision,
    Employee,
    Event,
    MemoryEntry,
    Message,
    Mission,
    MissionStatus,
    Role,
    Task,
    TaskStatus,
    Team,
)
from ..serde import from_data, to_data
from .base import Repository

T = TypeVar("T")

# 개체 클래스 → 테이블 이름
_TABLES: dict[type, str] = {
    Team: "teams",
    Role: "roles",
    Employee: "employees",
    Mission: "missions",
    Task: "tasks",
    Event: "events",
    Decision: "decisions",
    MemoryEntry: "memories",
    Message: "messages",
}


class SQLiteRepository(Repository):
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._init()

    # ── 저수준 헬퍼 ─────────────────────────────
    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._conn() as conn:
            for table in _TABLES.values():
                conn.execute(
                    f"CREATE TABLE IF NOT EXISTS {table} "
                    "(id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL)"
                )

    def _add(self, obj: T) -> T:
        table = _TABLES[type(obj)]
        data = to_data(obj)
        data.pop("id", None)
        with self._conn() as conn:
            cur = conn.execute(
                f"INSERT INTO {table}(data) VALUES(?)",
                (json.dumps(data, ensure_ascii=False),),
            )
            obj.id = cur.lastrowid  # type: ignore[attr-defined]
        return obj

    def _update(self, obj: T) -> T:
        table = _TABLES[type(obj)]
        data = to_data(obj)
        data.pop("id", None)
        with self._conn() as conn:
            conn.execute(
                f"UPDATE {table} SET data=? WHERE id=?",
                (json.dumps(data, ensure_ascii=False), obj.id),  # type: ignore[attr-defined]
            )
        return obj

    def _row_to_obj(self, cls: type, row: sqlite3.Row) -> Any:
        obj = from_data(cls, json.loads(row["data"]))
        obj.id = row["id"]
        return obj

    def _get(self, cls: type, obj_id: int) -> Any | None:
        table = _TABLES[cls]
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT id, data FROM {table} WHERE id=?", (obj_id,)
            ).fetchone()
        return self._row_to_obj(cls, row) if row else None

    def _all(self, cls: type) -> list[Any]:
        table = _TABLES[cls]
        with self._conn() as conn:
            rows = conn.execute(f"SELECT id, data FROM {table} ORDER BY id").fetchall()
        return [self._row_to_obj(cls, r) for r in rows]

    # ── Team ──
    def add_team(self, team: Team) -> Team:
        return self._add(team)

    def get_team(self, team_id: int) -> Team | None:
        return self._get(Team, team_id)

    def list_teams(self) -> list[Team]:
        return self._all(Team)

    # ── Role ──
    def add_role(self, role: Role) -> Role:
        return self._add(role)

    def get_role(self, role_id: int) -> Role | None:
        return self._get(Role, role_id)

    def get_role_by_key(self, key: str) -> Role | None:
        return next((r for r in self._all(Role) if r.key == key), None)

    def list_roles(self) -> list[Role]:
        return self._all(Role)

    # ── Employee ──
    def add_employee(self, employee: Employee) -> Employee:
        return self._add(employee)

    def get_employee(self, employee_id: int) -> Employee | None:
        return self._get(Employee, employee_id)

    def update_employee(self, employee: Employee) -> Employee:
        return self._update(employee)

    def list_employees(self, team_id: int | None = None) -> list[Employee]:
        emps = self._all(Employee)
        if team_id is not None:
            emps = [e for e in emps if e.team_id == team_id]
        return emps

    def find_employees_by_capability(
        self, capability: str, team_id: int | None = None
    ) -> list[Employee]:
        roles = {r.id: r for r in self._all(Role)}
        result = []
        for e in self.list_employees(team_id):
            role = roles.get(e.role_id)
            if role and capability in role.capabilities:
                result.append(e)
        return result

    # ── Mission ──
    def add_mission(self, mission: Mission) -> Mission:
        return self._add(mission)

    def get_mission(self, mission_id: int) -> Mission | None:
        return self._get(Mission, mission_id)

    def update_mission(self, mission: Mission) -> Mission:
        return self._update(mission)

    def list_missions(
        self, team_id: int | None = None, status: MissionStatus | None = None
    ) -> list[Mission]:
        ms = self._all(Mission)
        if team_id is not None:
            ms = [m for m in ms if m.team_id == team_id]
        if status is not None:
            ms = [m for m in ms if m.status == status]
        return ms

    # ── Task ──
    def add_task(self, task: Task) -> Task:
        return self._add(task)

    def get_task(self, task_id: int) -> Task | None:
        return self._get(Task, task_id)

    def update_task(self, task: Task) -> Task:
        return self._update(task)

    def list_tasks(
        self,
        mission_id: int | None = None,
        team_id: int | None = None,
        status: TaskStatus | None = None,
        assignee_id: int | None = None,
    ) -> list[Task]:
        ts = self._all(Task)
        if mission_id is not None:
            ts = [t for t in ts if t.mission_id == mission_id]
        if team_id is not None:
            ts = [t for t in ts if t.team_id == team_id]
        if status is not None:
            ts = [t for t in ts if t.status == status]
        if assignee_id is not None:
            ts = [t for t in ts if t.assignee_id == assignee_id]
        return ts

    # ── Event ──
    def add_event(self, event: Event) -> Event:
        return self._add(event)

    def list_events(
        self,
        task_id: int | None = None,
        mission_id: int | None = None,
        limit: int | None = None,
    ) -> list[Event]:
        evs = self._all(Event)
        if task_id is not None:
            evs = [e for e in evs if e.task_id == task_id]
        if mission_id is not None:
            evs = [e for e in evs if e.mission_id == mission_id]
        evs.sort(key=lambda e: (e.created_at, e.id or 0), reverse=True)
        if limit is not None:
            evs = evs[:limit]
        return evs

    # ── Decision ──
    def add_decision(self, decision: Decision) -> Decision:
        return self._add(decision)

    def list_decisions(self, task_id: int | None = None) -> list[Decision]:
        ds = self._all(Decision)
        if task_id is not None:
            ds = [d for d in ds if d.task_id == task_id]
        ds.sort(key=lambda d: (d.created_at, d.id or 0))
        return ds

    # ── Memory ──
    def add_memory(self, entry: MemoryEntry) -> MemoryEntry:
        return self._add(entry)

    def list_memory(self, employee_id: int | None = None) -> list[MemoryEntry]:
        ms = self._all(MemoryEntry)
        if employee_id is not None:
            ms = [m for m in ms if m.employee_id == employee_id]
        return ms

    # ── Message ──
    def add_message(self, message: Message) -> Message:
        return self._add(message)

    def list_messages(
        self, task_id: int | None = None, limit: int | None = None
    ) -> list[Message]:
        msgs = self._all(Message)
        if task_id is not None:
            msgs = [m for m in msgs if m.task_id == task_id]
        msgs.sort(key=lambda m: (m.created_at, m.id or 0))
        if limit is not None:
            msgs = msgs[-limit:]
        return msgs
