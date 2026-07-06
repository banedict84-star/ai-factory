"""초기 조직 구성 — Instagram Automation Team + 고정 5인 + 첫 Mission."""
from __future__ import annotations

from .domain.models import Employee, MemoryEntry, Mode, Role, Team
from .engine.reactor import OrganizationEngine
from .repository.base import Repository


def seed(repo: Repository) -> None:
    if repo.list_teams():
        return  # 이미 구성됨

    # ── 부서 ──
    team = repo.add_team(Team(
        name="Instagram Automation Team",
        emoji="📸",
        description="인스타그램 콘텐츠 기획·제작·게시·분석을 담당하는 AI 부서.",
        default_mode=Mode.auto,
    ))

    # ── 역할 (능력의 정의) ──
    role_lead = repo.add_role(Role(
        key="team_lead", name="팀장·콘텐츠 디렉터",
        capabilities=["decompose", "ideate", "brand_define", "propose", "review", "report"],
        description="미션을 업무로 분해하고 컨셉을 잡으며 결과를 대표에게 보고.",
    ))
    role_video = repo.add_role(Role(
        key="video_producer", name="영상 프로듀서",
        capabilities=["prompt_gen", "image_gen"],
    ))
    role_copy = repo.add_role(Role(
        key="copywriter", name="카피라이터",
        capabilities=["write_caption"],
    ))
    role_pub = repo.add_role(Role(
        key="publisher", name="게시 매니저",
        capabilities=["publish"],
    ))
    role_analyst = repo.add_role(Role(
        key="analyst", name="분석가",
        capabilities=["research", "analyze"],
    ))

    # ── 고정 5인 ──
    jiho = repo.add_employee(Employee(
        team_id=team.id, name="지호", role_id=role_lead.id,
        title="팀장", emoji="🧭", reports_to_id=None,  # 대표에게 보고
    ))
    rina = repo.add_employee(Employee(
        team_id=team.id, name="리나", role_id=role_video.id,
        title="팀원", emoji="🎬", reports_to_id=jiho.id,
    ))
    minjun = repo.add_employee(Employee(
        team_id=team.id, name="민준", role_id=role_copy.id,
        title="팀원", emoji="✍️", reports_to_id=jiho.id,
    ))
    repo.add_employee(Employee(
        team_id=team.id, name="수아", role_id=role_pub.id,
        title="팀원", emoji="📅", reports_to_id=jiho.id,
    ))
    taeo = repo.add_employee(Employee(
        team_id=team.id, name="태오", role_id=role_analyst.id,
        title="팀원", emoji="📊", reports_to_id=jiho.id,
    ))

    # ── 초기 기억 (일부는 key 를 달아 대화에 반영됨) ──
    repo.add_memory(MemoryEntry(
        content="대표는 기존 계정을 AI Boots / AI Fashion 릴스 계정으로 리브랜딩하길 원한다.",
        employee_id=jiho.id, source="feedback",
    ))
    repo.add_memory(MemoryEntry(
        content="브랜드 방향은 감성적이고 담백하게.",
        employee_id=jiho.id, source="learning", key="style_pref", value="감성적인",
    ))
    repo.add_memory(MemoryEntry(
        content="지난 영상이 조금 길다는 피드백이 있었다.",
        employee_id=rina.id, source="feedback", key="past_feedback", value="영상 길이 축소",
    ))
    repo.add_memory(MemoryEntry(
        content="대표는 짧은 문장을 선호한다.",
        employee_id=minjun.id, source="feedback", key="tone_pref", value="짧은",
    ))
    repo.add_memory(MemoryEntry(
        content="성과는 저장수 중심으로 본다.",
        employee_id=taeo.id, source="learning", key="metric_focus", value="저장수",
    ))
    repo.add_memory(MemoryEntry(
        content="브랜드 톤: 담백하고 감각적. 자연광 세로 숏폼.",
        employee_id=None, source="learning",  # 팀 공용 기억
    ))

    # ── 첫 Mission (대표가 만든 상위 목표) ──
    engine = OrganizationEngine(repo)
    engine.create_mission(
        team_id=team.id,
        intent=(
            "기존 인스타 계정을 AI Boots / AI Fashion 릴스 계정으로 리브랜딩하고, "
            "첫 7일 동안 하루 3개 릴스를 운영할 준비를 하라."
        ),
        mode=Mode.auto,
    )

    # 아침을 미리 돌려둔다 — 대표가 앱을 열면 이미 직원들이 출근해 일하고 있게.
    engine.open_office()
    for _ in range(9):
        engine.tick()
