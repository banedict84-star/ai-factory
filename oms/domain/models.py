"""도메인 모델 — Organization Engine 의 1급 개념들.

여기에는 DB 지식이 전혀 없습니다. 순수한 개념만 있습니다.
(주의: 이 파일은 일부러 `from __future__ import annotations` 를 쓰지 않습니다 —
 직렬화 계층이 실제 타입을 읽을 수 있어야 하기 때문입니다.)
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


def now() -> datetime:
    return datetime.now()


# ── 상태/열거형 ────────────────────────────────────────────
class EmployeeStatus(str, Enum):
    idle = "idle"        # 대기
    working = "working"  # 작업중
    waiting = "waiting"  # 대기(승인 등)
    blocked = "blocked"  # 막힘


class TaskStatus(str, Enum):
    created = "created"
    in_progress = "in_progress"
    handed_off = "handed_off"
    awaiting_approval = "awaiting_approval"
    blocked = "blocked"
    completed = "completed"


class MissionStatus(str, Enum):
    open = "open"
    in_progress = "in_progress"
    done = "done"


class Mode(str, Enum):
    auto = "auto"          # AI 가 바로 게시
    approval = "approval"  # 대표 최종 승인


class EventType(str, Enum):
    mission_created = "mission_created"
    mission_decomposed = "mission_decomposed"
    task_created = "task_created"
    task_handed_off = "task_handed_off"
    task_started = "task_started"
    task_worked = "task_worked"
    task_completed = "task_completed"
    employee_blocked = "employee_blocked"
    approval_requested = "approval_requested"
    approval_granted = "approval_granted"
    mission_done = "mission_done"


class DecisionAction(str, Enum):
    handoff = "handoff"
    complete = "complete"
    escalate = "escalate"


# ── 조직 (그릇) ───────────────────────────────────────────
@dataclass
class Team:
    name: str
    emoji: str = "🏢"
    description: str = ""
    default_mode: Mode = Mode.auto
    created_at: datetime = field(default_factory=now)
    id: Optional[int] = None


@dataclass
class Role:
    key: str                                   # 예: team_lead, video_producer
    name: str                                  # 한글 표기
    capabilities: List[str] = field(default_factory=list)  # 처리 가능한 need
    description: str = ""
    id: Optional[int] = None


@dataclass
class Employee:
    team_id: int
    name: str
    role_id: int
    title: str = "팀원"                        # 직책
    emoji: str = "🤖"
    reports_to_id: Optional[int] = None        # 보고 대상 (None = 대표)
    status: EmployeeStatus = EmployeeStatus.idle
    created_at: datetime = field(default_factory=now)
    id: Optional[int] = None


# ── 일 ───────────────────────────────────────────────────
@dataclass
class Mission:
    """대표가 만드는 상위 목표. 실행 불가, 팀장이 Task 로 분해."""
    team_id: int
    intent: str
    mode: Mode = Mode.auto
    status: MissionStatus = MissionStatus.open
    created_by: str = "ceo"
    created_at: datetime = field(default_factory=now)
    id: Optional[int] = None


@dataclass
class Task:
    """팀장이 분해한 실행 단위. Decision 에 의해 담당자가 바뀌며 이동."""
    mission_id: int
    team_id: int
    title: str
    kind: str = "reel"                         # reel | rebrand ...
    description: str = ""
    assignee_id: Optional[int] = None          # 지금 든 사람
    status: TaskStatus = TaskStatus.created
    artifacts: Dict[str, Any] = field(default_factory=dict)  # 쌓이는 산출물
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)
    completed_at: Optional[datetime] = None
    id: Optional[int] = None


# ── 엔진의 심장 ───────────────────────────────────────────
@dataclass
class Event:
    """무슨 일이 일어났다 — 조직이 반응하는 신호이자 감사 로그."""
    type: EventType
    team_id: int
    mission_id: Optional[int] = None
    task_id: Optional[int] = None
    actor_id: Optional[int] = None             # None = 대표
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=now)
    id: Optional[int] = None


@dataclass
class Decision:
    """이 태스크, 다음은 누구에게? — 지금은 규칙, 나중엔 AI 가 채운다."""
    task_id: int
    decided_by_id: int
    action: DecisionAction
    input: Dict[str, Any] = field(default_factory=dict)   # 결정이 본 것
    next_assignee_id: Optional[int] = None
    reason: str = ""
    made_by: str = "rule"                      # rule | ai
    created_at: datetime = field(default_factory=now)
    id: Optional[int] = None


# ── 맥락 ─────────────────────────────────────────────────
@dataclass
class MemoryEntry:
    """직원(또는 팀)의 기억. 결정할 때 읽고, 행동/피드백 후 쓴다."""
    content: str
    employee_id: Optional[int] = None          # None = 팀/조직 공용
    source: str = "learning"                   # feedback | decision | learning
    created_at: datetime = field(default_factory=now)
    id: Optional[int] = None
