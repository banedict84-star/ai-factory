"""검수 저장소 — 초안을 디스크에 저장하고, 대표가 승인/반려한 뒤 발행합니다.

초안은 output/cafe_drafts/ 아래에 저장됩니다:
  <id>.json   초안 데이터(검수 상태 포함)
  <id>.html   브라우저로 미리보기용 렌더링

'초안 AI + 내 검수' 흐름의 핵심: AI 가 만든 글을 바로 올리지 않고 이 폴더에 쌓아두면,
대표가 내용을 확인하고 approve 한 것만 실제로 발행됩니다.
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import config
from .models import CafePost, Draft

DRAFTS_DIR = config.OUTPUT_DIR / "cafe_drafts"


def _dir() -> Path:
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    return DRAFTS_DIR


def save_draft(post: CafePost, draft_id: str, created_at: str) -> Draft:
    """새 초안을 pending 상태로 저장합니다. id/created_at 은 호출자가 생성해 넘깁니다."""
    draft = Draft(id=draft_id, post=post, status="pending", created_at=created_at)
    _write(draft)
    return draft


def _write(draft: Draft) -> None:
    d = _dir()
    (d / f"{draft.id}.json").write_text(
        json.dumps(draft.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (d / f"{draft.id}.html").write_text(_render_preview(draft), encoding="utf-8")


def load_draft(draft_id: str) -> Draft:
    path = _dir() / f"{draft_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"초안을 찾을 수 없습니다: {draft_id}")
    return Draft.from_dict(json.loads(path.read_text(encoding="utf-8")))


def list_drafts(status: str | None = None) -> list[Draft]:
    """저장된 초안 목록. status 를 주면 그 상태만 필터링(최신순)."""
    drafts: list[Draft] = []
    for path in sorted(_dir().glob("*.json"), reverse=True):
        try:
            draft = Draft.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, KeyError):
            continue
        if status is None or draft.status == status:
            drafts.append(draft)
    return drafts


def update_post(
    draft_id: str,
    subject: str | None = None,
    content: str | None = None,
) -> Draft:
    """초안의 제목/본문을 수정해서 다시 저장합니다(대시보드 편집용)."""
    draft = load_draft(draft_id)
    if subject is not None:
        draft.post.subject = subject
    if content is not None:
        draft.post.content = content
    _write(draft)
    return draft


def set_detail_image(draft_id: str, url: str) -> Draft:
    """상세페이지 이미지 URL 을 초안에 저장합니다."""
    draft = load_draft(draft_id)
    draft.post.detail_image_url = url
    _write(draft)
    return draft


def update_status(draft_id: str, status: str, note: str = "") -> Draft:
    draft = load_draft(draft_id)
    draft.status = status
    if note:
        draft.note = note
    _write(draft)
    return draft


def approve(draft_id: str, note: str = "") -> Draft:
    return update_status(draft_id, "approved", note)


def reject(draft_id: str, note: str = "") -> Draft:
    return update_status(draft_id, "rejected", note)


def mark_published(
    draft_id: str,
    article_id: str | None,
    article_url: str | None,
    published_at: str,
) -> Draft:
    draft = load_draft(draft_id)
    draft.status = "published"
    draft.article_id = article_id
    draft.article_url = article_url
    draft.published_at = published_at
    _write(draft)
    return draft


def _render_preview(draft: Draft) -> str:
    """검수용 미리보기 HTML. 본문이 HTML 이든 텍스트든 브라우저에서 확인 가능."""
    p = draft.post
    return (
        "<!doctype html><meta charset='utf-8'>"
        f"<title>초안 {draft.id}</title>"
        "<div style='max-width:720px;margin:40px auto;font-family:system-ui,sans-serif;"
        "line-height:1.7;padding:0 16px'>"
        f"<p style='color:#888;font-size:13px'>초안 ID: {draft.id} · 상태: {draft.status}</p>"
        f"<p style='color:#888;font-size:13px'>요약: {p.summary}</p>"
        f"<h1 style='font-size:24px'>{p.subject}</h1>"
        f"<hr><div>{p.content}</div>"
        f"<hr><p style='color:#aaa;font-size:12px'>태그: {', '.join(p.tags)}</p>"
        "</div>"
    )
