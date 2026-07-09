"""카페 글 데이터 모델 — AI 초안(CafePost)과 검수 대상 초안(Draft)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class CafePost:
    """AI 가 생성한 카페 글 한 건. 발행 시 subject/content 가 그대로 API 로 넘어갑니다."""

    topic: str          # 이 글의 소재 한 줄
    subject: str        # 제목
    content: str        # 본문 (HTML 또는 순수 텍스트)
    summary: str        # 검수용 한두 문장 요약
    tags: list[str] = field(default_factory=list)  # 참고용 키워드(발행엔 미사용 가능)
    detail_image_url: str = ""  # 상세페이지 이미지(설정 시 발행에 첨부)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CafePost":
        return cls(
            topic=data["topic"],
            subject=data["subject"],
            content=data["content"],
            summary=data.get("summary", ""),
            tags=list(data.get("tags", [])),
            detail_image_url=data.get("detail_image_url", ""),
        )


@dataclass
class Draft:
    """디스크에 저장되는 검수 단위. 상태: pending → approved/published/rejected."""

    id: str                 # 파일명이자 초안 ID (예: 20260708-153000)
    post: CafePost
    status: str = "pending"           # pending / approved / published / rejected
    created_at: str = ""              # ISO8601 (외부에서 주입 — 테스트 재현성 위해 모델 내부에서 시간 생성 안 함)
    published_at: str | None = None
    article_url: str | None = None    # 발행 후 글 URL
    article_id: str | None = None     # 발행 후 글 ID
    note: str = ""                    # 검수 메모 / 반려 사유 등

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["post"] = self.post.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Draft":
        return cls(
            id=data["id"],
            post=CafePost.from_dict(data["post"]),
            status=data.get("status", "pending"),
            created_at=data.get("created_at", ""),
            published_at=data.get("published_at"),
            article_url=data.get("article_url"),
            article_id=data.get("article_id"),
            note=data.get("note", ""),
        )
