"""카페 에이전트 관리 대시보드 (FastAPI).

브라우저에서 초안을 생성·검수(승인/반려)·발행하고, 발행 이력과 설정을 봅니다.
file 기반 검수 저장소(review)와 pipeline 에만 의존합니다.

실행:
  uvicorn src.cafe.web:app --reload      # 개발
  python -m src.cafe.web                  # 간편 실행 (http://127.0.0.1:8010)
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import config
from . import pipeline, review

ROOT = Path(__file__).resolve().parent.parent.parent

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # pragma: no cover - dotenv 없으면 그냥 넘어감
    pass

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

STATUS_BADGE = {
    "pending": ("amber", "검수 대기"),
    "approved": ("blue", "승인됨"),
    "published": ("green", "발행됨"),
    "rejected": ("red", "반려됨"),
}

app = FastAPI(title="가죽공예 카페 에이전트")


def _has_anthropic() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _render(request: Request, name: str, status_code: int = 200, **kw):
    """모던 Starlette 시그니처(request 우선)로 템플릿을 렌더링합니다."""
    ctx = {"status_badge": STATUS_BADGE, "has_key": _has_anthropic()}
    ctx.update(kw)
    return TEMPLATES.TemplateResponse(request, name, ctx, status_code=status_code)


@app.get("/")
def dashboard(request: Request):
    cfg = config.load_cafe_config()
    all_drafts = review.list_drafts()
    pending = [d for d in all_drafts if d.status == "pending"]
    approved = [d for d in all_drafts if d.status == "approved"]
    published = [d for d in all_drafts if d.status == "published"]
    return _render(
        request,
        "dashboard.html",
        cafe_name=cfg.get("brand", {}).get("name", "카페"),
        pending=pending,
        approved=approved,
        published=published[:10],
        total=len(all_drafts),
    )


@app.post("/generate")
def generate(request: Request, topic: str = Form("")):
    try:
        result = pipeline.draft(topic_hint=topic.strip() or None)
    except Exception as e:  # 키 없음/생성 실패 등을 화면에 표시
        return _render(
            request, "message.html", status_code=500,
            title="초안 생성 실패", message=str(e), back="/",
        )
    return RedirectResponse(f"/draft/{result.draft.id}", status_code=303)


@app.get("/draft/{draft_id}")
def draft_detail(request: Request, draft_id: str):
    try:
        d = review.load_draft(draft_id)
    except FileNotFoundError:
        return _render(
            request, "message.html", status_code=404,
            title="초안 없음", message=f"{draft_id} 를 찾을 수 없습니다.", back="/",
        )
    return _render(request, "draft.html", d=d)


@app.post("/draft/{draft_id}/approve")
def approve(draft_id: str, note: str = Form("")):
    review.approve(draft_id, note=note.strip())
    return RedirectResponse(f"/draft/{draft_id}", status_code=303)


@app.post("/draft/{draft_id}/reject")
def reject(draft_id: str, note: str = Form("")):
    review.reject(draft_id, note=note.strip())
    return RedirectResponse(f"/draft/{draft_id}", status_code=303)


@app.post("/draft/{draft_id}/publish")
def publish(request: Request, draft_id: str):
    try:
        pipeline.publish(draft_id, require_approved=True)
    except Exception as e:
        return _render(
            request, "message.html", status_code=500,
            title="발행 실패", message=str(e), back=f"/draft/{draft_id}",
        )
    return RedirectResponse(f"/draft/{draft_id}", status_code=303)


@app.get("/settings")
def settings(request: Request):
    cfg = config.load_cafe_config()
    return _render(request, "settings.html", cfg=cfg, path=str(config.CAFE_CONFIG_PATH))


def main() -> None:
    import uvicorn

    port = int(os.getenv("CAFE_WEB_PORT", "8010"))
    print(f"[가죽공예 카페 에이전트] http://127.0.0.1:{port}  (ANTHROPIC_API_KEY="
          f"{'set' if _has_anthropic() else 'MISSING'})")
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
