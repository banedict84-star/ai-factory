"""업무 지식 — Instagram 팀이 '무엇을 만들어야 하는가'.

이 부분은 지금은 사람이 정의하지만, 나중에는 AI 가 학습/판단할 영역입니다.
Task 자체에는 순서가 박혀있지 않습니다. '무엇이 필요한가'만 여기 정의하고,
'다음에 누가 할까'는 Decision 이 정합니다.
"""
from __future__ import annotations

# Task 종류별로 완성에 필요한 산출물(checklist) — 순서 아님, 그냥 '필요한 것들'
REQUIRED_ARTIFACTS: dict[str, list[str]] = {
    "reel": ["concept", "video", "caption", "published"],
    "rebrand": ["brand_definition", "audience_research"],
    "analysis": ["audience_research", "direction_proposal"],
}

# 역량(capability) → 그 역량이 만들어내는 산출물
CAPABILITY_PRODUCES: dict[str, str] = {
    "ideate": "concept",
    "brand_define": "brand_definition",
    "produce_video": "video",
    "write_caption": "caption",
    "publish": "published",
    "research": "audience_research",
    "propose": "direction_proposal",
}

# 산출물 → 그것을 만들 수 있는 역량 (역방향)
PRODUCED_BY: dict[str, str] = {v: k for k, v in CAPABILITY_PRODUCES.items()}

# 산출물(=업무) 한글 라벨 — 활동 문구에 그대로 쓰입니다.
ARTIFACT_LABEL: dict[str, str] = {
    "concept": "컨셉 기획",
    "brand_definition": "브랜드 정의",
    "video": "영상 제작",
    "caption": "캡션과 해시태그 작성",
    "published": "게시",
    "audience_research": "리서치·분석",
    "direction_proposal": "콘텐츠 방향 제안",
}


def plan_mission(intent: str) -> list[tuple[str, str]]:
    """팀장이 Mission 을 Task 로 분해하는 규칙 (지금은 규칙, 나중엔 AI).

    반환: (kind, title) 리스트
    """
    # 성과 분석형 미션
    if any(k in intent for k in ("분석", "성과")):
        return [("analysis", "성과 분석 및 다음 콘텐츠 방향 제안")]

    tasks: list[tuple[str, str]] = []
    if any(k in intent for k in ("리브랜딩", "브랜드", "리브랜드", "rebrand")):
        tasks.append(("rebrand", "브랜드 리브랜딩: AI Boots / AI Fashion 정의"))
    # 기본적으로 릴스 3개 (하루 3개 운영 준비)
    for i in range(1, 4):
        tasks.append(("reel", f"릴스 #{i} 제작"))
    return tasks
