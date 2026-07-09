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
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import config
from . import auth, content_generator, images, pipeline, publisher, review

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

# ── (선택) 비밀번호 잠금 ──────────────────────────────────
# APP_PASSWORD 를 설정하면 공개 주소로 배포해도 남이 내 카페에 글을 쓰거나
# 내 크레딧을 쓰지 못하게 막아줍니다. 비워두면 잠금 없음.
_APP_PASSWORD = os.getenv("APP_PASSWORD")
if _APP_PASSWORD:
    import base64

    from starlette.responses import Response

    @app.middleware("http")
    async def _basic_auth(request: Request, call_next):
        # 이미지(/img/)는 네이버·방문자가 불러가야 하므로 잠금 예외
        if request.url.path.startswith("/img/"):
            return await call_next(request)
        header = request.headers.get("authorization", "")
        ok = False
        if header.startswith("Basic "):
            try:
                decoded = base64.b64decode(header[6:]).decode("utf-8")
                ok = decoded.split(":", 1)[1] == _APP_PASSWORD
            except Exception:
                ok = False
        if not ok:
            return Response(
                "비밀번호가 필요합니다.", status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="cafe-agent"'},
            )
        return await call_next(request)


def _has_llm_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))


def _hero_image_src(content: str) -> str:
    """본문 상단 대표 이미지(<img>)의 src 를 뽑는다. 없으면 빈 문자열."""
    import re

    m = re.search(r'<img\b[^>]*\bsrc=["\']([^"\']+)["\']', content, re.IGNORECASE)
    return m.group(1) if m else ""


def _public_base(request: Request) -> str:
    """배포 도메인 기준 base URL. 프록시(https) 뒤에서도 https 로 맞춥니다."""
    override = os.getenv("CAFE_PUBLIC_URL")
    if override:
        return override.rstrip("/")
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.url.netloc
    return f"{proto}://{host}"


def _redirect_uri(request: Request) -> str:
    return f"{_public_base(request)}/oauth/callback"


def _render(request: Request, name: str, status_code: int = 200, **kw):
    """모던 Starlette 시그니처(request 우선)로 템플릿을 렌더링합니다."""
    ctx = {
        "status_badge": STATUS_BADGE,
        "has_key": _has_llm_key(),
        "connected": auth.is_connected(),
    }
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
    return _render(
        request, "draft.html", d=d,
        cafe_hero=_hero_image_src(d.post.content),
        cafe_preview=publisher._prettify_for_cafe(d.post.content),
    )


@app.post("/draft/{draft_id}/edit")
def edit_draft(draft_id: str, subject: str = Form(...), content: str = Form(...)):
    """대시보드에서 편집한 제목/본문을 저장합니다."""
    review.update_post(draft_id, subject=subject.strip(), content=content)
    return RedirectResponse(f"/draft/{draft_id}", status_code=303)


@app.post("/draft/{draft_id}/images")
def generate_images(request: Request, draft_id: str):
    """본문의 각 소제목마다 이미지를 생성·삽입합니다. (시간이 걸릴 수 있음)"""
    d = review.load_draft(draft_id)
    if d.status == "published":
        return _render(
            request, "message.html", status_code=400,
            title="이미지 삽입 불가", message="이미 발행된 글입니다.", back=f"/draft/{draft_id}",
        )
    try:
        brand = config.load_cafe_config().get("brand", {}).get("name", "")
        new_content = images.add_hero_image(
            d.post.content, d.post.topic, draft_id, title=d.post.subject, brand=brand
        )
    except Exception as e:
        return _render(
            request, "message.html", status_code=500,
            title="이미지 생성 실패", message=str(e), back=f"/draft/{draft_id}",
        )
    review.update_post(draft_id, content=new_content)
    return RedirectResponse(f"/draft/{draft_id}", status_code=303)


@app.post("/draft/{draft_id}/detail")
def make_detail(request: Request, draft_id: str):
    """글+이미지를 하나의 상세페이지 이미지로 만들어 초안에 저장합니다."""
    d = review.load_draft(draft_id)
    if d.status == "published":
        return _render(
            request, "message.html", status_code=400,
            title="상세페이지 생성 불가", message="이미 발행된 글입니다.",
            back=f"/draft/{draft_id}",
        )
    try:
        content = d.post.content
        if "<img" not in content.lower():
            # 이미지가 없으면 소제목마다 이미지를 만들어 넣는다(상세페이지용)
            content = images.add_section_images(content, d.post.topic, draft_id, "")
            review.update_post(draft_id, content=content)
        brand = config.load_cafe_config().get("brand", {}).get("name", "")
        png = images.render_detail_page(content, d.post.subject, brand)
        url = images.upload_image(png, f"{images.GCS_PREFIX}/{draft_id}/detail.png")
        review.set_detail_image(draft_id, url)
    except Exception as e:
        return _render(
            request, "message.html", status_code=500,
            title="상세페이지 생성 실패", message=str(e), back=f"/draft/{draft_id}",
        )
    return RedirectResponse(f"/draft/{draft_id}", status_code=303)


@app.get("/img/{path:path}")
def serve_image(path: str):
    """GCS 에 저장된 이미지를 서빙합니다(공개, 잠금 예외)."""
    from starlette.responses import Response

    try:
        data = images.fetch_image(f"{images.GCS_PREFIX}/{path}")
    except Exception:
        return Response(status_code=404)
    return Response(content=data, media_type="image/png")


@app.post("/api/rewrite")
async def api_rewrite(request: Request):
    """선택한 본문 일부를 지시대로 AI가 고쳐 JSON 으로 돌려줍니다."""
    data = await request.json()
    text = (data.get("text") or "").strip()
    instruction = (data.get("instruction") or "").strip()
    if not text or not instruction:
        return JSONResponse({"error": "선택 텍스트와 지시가 필요합니다."}, status_code=400)
    try:
        result = content_generator.rewrite_snippet(text, instruction)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    return JSONResponse({"result": result})


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


# ── 네이버 연결 (OAuth) ─────────────────────────────────────
@app.get("/connect")
def connect(request: Request):
    """네이버 로그인 페이지로 보냅니다. redirect_uri 는 이 배포 도메인 기준."""
    if not os.getenv("NAVER_CLIENT_ID"):
        return _render(
            request, "message.html", status_code=400,
            title="네이버 설정 필요",
            message="NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수가 없습니다. "
                    "배포 환경(예: Render)의 환경변수에 넣어주세요.",
            back="/",
        )
    url = auth.build_authorize_url(_redirect_uri(request), state="aifactory")
    return RedirectResponse(url, status_code=303)


@app.get("/oauth/callback")
def oauth_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    """네이버가 돌려보낸 code 를 토큰으로 교환하고 refresh_token 을 저장/안내합니다."""
    if error or not code:
        return _render(
            request, "message.html", status_code=400,
            title="네이버 연결 취소/실패",
            message=f"인증 코드가 없습니다. (error={error or '없음'})",
            back="/",
        )
    try:
        tokens = auth.exchange_code_for_tokens(code, state or "aifactory")
    except Exception as e:
        return _render(
            request, "message.html", status_code=500,
            title="토큰 교환 실패", message=str(e), back="/",
        )
    refresh = tokens.get("refresh_token")
    if refresh:
        auth.save_refresh_token(refresh)
    return _render(request, "connected.html", refresh_token=refresh or "")


def main() -> None:
    import uvicorn

    # Render 등 호스팅은 $PORT 를 지정하고 0.0.0.0 바인딩을 요구합니다.
    # 로컬은 CAFE_WEB_PORT(기본 8010) + 127.0.0.1.
    port = int(os.getenv("PORT", os.getenv("CAFE_WEB_PORT", "8010")))
    host = "0.0.0.0" if os.getenv("PORT") else "127.0.0.1"
    print(f"[가죽공예 카페 에이전트] {host}:{port}  (AI키="
          f"{'set' if _has_llm_key() else 'MISSING'})")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
