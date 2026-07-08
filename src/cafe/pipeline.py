"""파이프라인 — 초안 생성 → 검수 저장 → (승인 후) 발행.

핵심 흐름은 두 단계로 나뉩니다:
  1) draft(): AI 가 초안을 만들어 검수 폴더에 pending 으로 저장 (아직 발행 안 함)
  2) publish(): 대표가 확인/승인한 초안을 실제 네이버 카페에 발행

이렇게 나눠야 '초안 AI + 내 검수' 가 성립합니다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .. import config
from . import content_generator, review
from .models import Draft
from .publisher import NaverCafePublisher


@dataclass
class DraftResult:
    draft: Draft
    preview_path: str


def draft(topic_hint: str | None = None) -> DraftResult:
    """AI 초안을 생성해 검수 대기(pending) 상태로 저장합니다. 발행하지 않습니다."""
    post = content_generator.generate_post(topic_hint=topic_hint)
    now = datetime.now()
    draft_id = now.strftime("%Y%m%d-%H%M%S")
    saved = review.save_draft(post, draft_id=draft_id, created_at=now.isoformat())
    preview = str(review.DRAFTS_DIR / f"{draft_id}.html")
    return DraftResult(draft=saved, preview_path=preview)


def run_daily(topic_hint: str | None = None) -> Draft:
    """매일 1회 자동 발행 — 초안 생성 → 자동 승인 → 발행 을 한 번에.

    검수 없이 바로 올라가지만, 초안/발행 결과는 output/cafe_drafts 에 기록되어
    나중에 무엇이 언제 올라갔는지 확인할 수 있습니다.
    """
    result = draft(topic_hint=topic_hint)
    draft_id = result.draft.id
    review.approve(draft_id, note="daily 자동 발행")
    return publish(draft_id, require_approved=False)


def publish(draft_id: str, require_approved: bool = True) -> Draft:
    """검수된 초안을 실제로 발행합니다.

    require_approved=True 면 status 가 approved 인 초안만 발행합니다(안전장치).
    """
    d = review.load_draft(draft_id)

    if d.status == "published":
        raise RuntimeError(f"이미 발행된 초안입니다: {draft_id}")
    if require_approved and d.status != "approved":
        raise RuntimeError(
            f"승인되지 않은 초안입니다(status={d.status}). "
            f"먼저 `python -m src.cafe.main approve {draft_id}` 로 승인하세요."
        )

    cfg = config.load_cafe_config()
    open_to_public = bool(cfg.get("post", {}).get("open_to_public", True))

    publisher = NaverCafePublisher()
    result = publisher.publish(d.post, open_to_public=open_to_public)

    return review.mark_published(
        draft_id,
        article_id=result.get("articleId"),
        article_url=result.get("articleUrl"),
        published_at=datetime.now().isoformat(),
    )
