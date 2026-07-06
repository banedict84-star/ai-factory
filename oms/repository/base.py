"""Repository 인터페이스 — 데이터 접근의 유일한 경로.

엔진과 화면 코드는 이 인터페이스에만 의존합니다. DB(SQLite/Postgres/Supabase)는
구현체를 갈아끼우면 됩니다. DB 직접 호출이 엔진/화면에 새어나오면 안 됩니다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

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


class Repository(ABC):
    # ── Team ──
    @abstractmethod
    def add_team(self, team: Team) -> Team: ...
    @abstractmethod
    def get_team(self, team_id: int) -> Team | None: ...
    @abstractmethod
    def list_teams(self) -> list[Team]: ...

    # ── Role ──
    @abstractmethod
    def add_role(self, role: Role) -> Role: ...
    @abstractmethod
    def get_role(self, role_id: int) -> Role | None: ...
    @abstractmethod
    def get_role_by_key(self, key: str) -> Role | None: ...
    @abstractmethod
    def list_roles(self) -> list[Role]: ...

    # ── Employee ──
    @abstractmethod
    def add_employee(self, employee: Employee) -> Employee: ...
    @abstractmethod
    def get_employee(self, employee_id: int) -> Employee | None: ...
    @abstractmethod
    def update_employee(self, employee: Employee) -> Employee: ...
    @abstractmethod
    def list_employees(self, team_id: int | None = None) -> list[Employee]: ...
    @abstractmethod
    def find_employees_by_capability(
        self, capability: str, team_id: int | None = None
    ) -> list[Employee]: ...

    # ── Mission ──
    @abstractmethod
    def add_mission(self, mission: Mission) -> Mission: ...
    @abstractmethod
    def get_mission(self, mission_id: int) -> Mission | None: ...
    @abstractmethod
    def update_mission(self, mission: Mission) -> Mission: ...
    @abstractmethod
    def list_missions(
        self, team_id: int | None = None, status: MissionStatus | None = None
    ) -> list[Mission]: ...

    # ── Task ──
    @abstractmethod
    def add_task(self, task: Task) -> Task: ...
    @abstractmethod
    def get_task(self, task_id: int) -> Task | None: ...
    @abstractmethod
    def update_task(self, task: Task) -> Task: ...
    @abstractmethod
    def list_tasks(
        self,
        mission_id: int | None = None,
        team_id: int | None = None,
        status: TaskStatus | None = None,
        assignee_id: int | None = None,
    ) -> list[Task]: ...

    # ── Event ──
    @abstractmethod
    def add_event(self, event: Event) -> Event: ...
    @abstractmethod
    def list_events(
        self,
        task_id: int | None = None,
        mission_id: int | None = None,
        limit: int | None = None,
    ) -> list[Event]: ...

    # ── Decision ──
    @abstractmethod
    def add_decision(self, decision: Decision) -> Decision: ...
    @abstractmethod
    def list_decisions(self, task_id: int | None = None) -> list[Decision]: ...

    # ── Memory ──
    @abstractmethod
    def add_memory(self, entry: MemoryEntry) -> MemoryEntry: ...
    @abstractmethod
    def list_memory(self, employee_id: int | None = None) -> list[MemoryEntry]: ...

    # ── Message (대화) ──
    @abstractmethod
    def add_message(self, message: Message) -> Message: ...
    @abstractmethod
    def list_messages(
        self, task_id: int | None = None, limit: int | None = None
    ) -> list[Message]: ...
