"""Grok Studio 웹앱 (FastAPI) — 회원제 + 크레딧.

- 회원가입/로그인 후 이용. 영상 1개 생성마다 크레딧 차감(실패 시 환불).
- 충전은 무통장입금 → 관리자가 크레딧 지급(수동). 나중에 PG 연동 자리.
- 각 회원의 생성 결과는 갤러리에 저장.
"""
from __future__ import annotations

import threading
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile, File
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import auth, config, db, models, xai_client

app = FastAPI(title="Grok Studio — 쇼핑몰 모델 영상")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/outputs", StaticFiles(directory=str(config.OUTPUT_DIR)), name="outputs")
STATIC_MODELS_DIR = BASE_DIR / "static" / "models"

db.init()


# ── 인메모리 job 저장소 ───────────────────────────────────────
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

STAGES = {
    "queued": "대기 중…",
    "analyzing": "옷을 분석하는 중…",
    "generating_image": "모델에게 옷을 입히는 중…",
    "image_ready": "옷 입은 사진 완성! 영상 만드는 중…",
    "generating_video": "영상을 생성하는 중… (수십 초~수 분)",
    "done": "완성!",
    "error": "오류",
}


def _set(job_id: str, **kw) -> None:
    with _jobs_lock:
        _jobs.setdefault(job_id, {}).update(kw)


def _get(job_id: str) -> dict | None:
    with _jobs_lock:
        j = _jobs.get(job_id)
        return dict(j) if j else None


# ── 현재 로그인 유저 ──────────────────────────────────────────
def _user(request: Request):
    return auth.current_user(request.cookies.get("gs_session"))


def _require_user(request: Request):
    u = _user(request)
    if not u:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return u


# ── 백그라운드 파이프라인 ─────────────────────────────────────
def _run_pipeline(job_id: str, user_id: int, cost: int, model_id: str,
                  image_bytes: bytes, mime: str, motion: str) -> None:
    try:
        model = models.get_model(model_id)

        _set(job_id, stage="analyzing")
        garment = xai_client.analyze_garment(image_bytes, mime)
        _set(job_id, garment=garment)

        _set(job_id, stage="generating_image")
        tryon_prompt = models.build_tryon_prompt(model.appearance, garment)
        tryon_png = xai_client.generate_tryon_image(tryon_prompt)
        img_name = f"{job_id}_tryon.png"
        (config.OUTPUT_DIR / img_name).write_bytes(tryon_png)
        tryon_url = f"/outputs/{img_name}"
        _set(job_id, stage="image_ready", tryon_url=tryon_url)

        _set(job_id, stage="generating_video")
        video_prompt = models.build_video_prompt(model.name, motion)
        _set(job_id, video_prompt=video_prompt)
        remote_url = xai_client.generate_video(
            tryon_png, video_prompt,
            on_progress=lambda s: _set(job_id, video_status=s),
        )

        video_url = remote_url
        try:
            vid = xai_client.download(remote_url)
            vid_name = f"{job_id}_video.mp4"
            (config.OUTPUT_DIR / vid_name).write_bytes(vid)
            video_url = f"/outputs/{vid_name}"
        except Exception:
            pass

        _set(job_id, stage="done", video_url=video_url)
        db.add_generation(user_id, model_id, garment, tryon_url, video_url, "done")

    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        # 실패하면 차감했던 크레딧 환불
        try:
            db.grant_credit(user_id, cost, "refund")
        except Exception:
            pass
        _set(job_id, stage="error", error=str(e))


# ── 인증 페이지/API ───────────────────────────────────────────
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if _user(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(request=request, name="login.html", context={})


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    if _user(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse(
        request=request, name="signup.html",
        context={"free": config.SIGNUP_FREE_CREDITS})


def _auth_cookie(resp, token: str):
    resp.set_cookie("gs_session", token, httponly=True, samesite="lax", max_age=60*60*24*30)
    return resp


@app.post("/api/signup")
def api_signup(email: str = Form(...), password: str = Form(...)):
    try:
        user = auth.signup(email, password)
    except auth.AuthError as e:
        raise HTTPException(status_code=400, detail=str(e))
    token = auth.start_session(user["id"])
    return _auth_cookie(JSONResponse({"ok": True}), token)


@app.post("/api/login")
def api_login(email: str = Form(...), password: str = Form(...)):
    try:
        user = auth.login(email, password)
    except auth.AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    token = auth.start_session(user["id"])
    return _auth_cookie(JSONResponse({"ok": True}), token)


@app.post("/api/logout")
def api_logout(request: Request):
    tok = request.cookies.get("gs_session")
    if tok:
        db.delete_session(tok)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("gs_session")
    return resp


# ── 메인 화면 (로그인 필요) ───────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    user = _user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "models": models.MODELS,
            "default_motion": models.DEFAULT_MOTION_PROMPT,
            "has_key": bool(config.XAI_API_KEY),
            "user": user,
            "credit_cost": config.CREDIT_COST_VIDEO,
        },
    )


@app.post("/api/generate")
async def generate(
    request: Request,
    model_id: str = Form(...),
    motion: str = Form(""),
    clothing: UploadFile = File(...),
):
    user = _require_user(request)
    if not config.XAI_API_KEY:
        raise HTTPException(status_code=400,
                            detail="서버에 XAI_API_KEY 가 설정되지 않았습니다.")
    if model_id not in models.MODELS_BY_ID:
        raise HTTPException(status_code=400, detail="알 수 없는 모델입니다.")

    image_bytes = await clothing.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="옷 사진이 비어 있습니다.")
    if len(image_bytes) > 15 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="사진이 너무 큽니다(최대 15MB).")

    # 크레딧 원자적 차감 (부족하면 402)
    cost = config.CREDIT_COST_VIDEO
    if not db.try_spend_credit(user["id"], cost, "video"):
        raise HTTPException(
            status_code=402,
            detail=f"크레딧이 부족합니다. (영상 1개 = {cost}크레딧) 충전 후 이용해주세요.")

    mime = clothing.content_type or "image/jpeg"
    motion = (motion or models.DEFAULT_MOTION_PROMPT).strip()

    job_id = uuid.uuid4().hex[:12]
    _set(job_id, stage="queued", model_id=model_id)
    threading.Thread(
        target=_run_pipeline,
        args=(job_id, user["id"], cost, model_id, image_bytes, mime, motion),
        daemon=True,
    ).start()
    return {"job_id": job_id}


@app.get("/api/job/{job_id}")
def job_status(job_id: str):
    j = _get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job 을 찾을 수 없습니다.")
    stage = j.get("stage", "queued")
    return {
        "job_id": job_id,
        "stage": stage,
        "stage_label": STAGES.get(stage, stage),
        "garment": j.get("garment"),
        "tryon_url": j.get("tryon_url"),
        "video_url": j.get("video_url"),
        "video_prompt": j.get("video_prompt"),
        "error": j.get("error"),
    }


# ── 갤러리 / 충전 ─────────────────────────────────────────────
@app.get("/gallery", response_class=HTMLResponse)
def gallery(request: Request):
    user = _user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    items = db.list_generations(user["id"])
    return templates.TemplateResponse(
        request=request, name="gallery.html",
        context={"user": user, "items": items})


@app.get("/billing", response_class=HTMLResponse)
def billing(request: Request):
    user = _user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse(
        request=request, name="billing.html",
        context={"user": user, "bank_info": config.BANK_INFO,
                 "price": config.CREDIT_PRICE_KRW})


# ── 관리자 ────────────────────────────────────────────────────
@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    user = _user(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="관리자만 접근 가능합니다.")
    return templates.TemplateResponse(
        request=request, name="admin.html",
        context={"user": user, "users": db.list_users()})


@app.post("/admin/grant")
def admin_grant(request: Request, user_id: int = Form(...), amount: int = Form(...)):
    user = _require_user(request)
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="관리자만 가능합니다.")
    if not db.get_user(user_id):
        raise HTTPException(status_code=404, detail="해당 회원이 없습니다.")
    db.grant_credit(user_id, amount, f"admin_grant(by {user['email']})")
    return RedirectResponse("/admin", status_code=303)


# ── 모델 프로필 사진 ──────────────────────────────────────────
_preview_locks: dict[str, threading.Lock] = {
    m.id: threading.Lock() for m in models.MODELS
}


@app.get("/api/model-preview/{model_id}")
def model_preview(model_id: str):
    if model_id not in models.MODELS_BY_ID:
        raise HTTPException(status_code=404, detail="unknown model")
    for ext in ("png", "jpg", "jpeg", "webp"):
        fixed = STATIC_MODELS_DIR / f"{model_id}.{ext}"
        if fixed.exists():
            mt = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
            return FileResponse(str(fixed), media_type=mt,
                                headers={"Cache-Control": "public, max-age=604800"})
    path = config.OUTPUT_DIR / f"model_{model_id}.png"
    if not path.exists():
        if not config.XAI_API_KEY:
            raise HTTPException(status_code=503, detail="no key")
        with _preview_locks[model_id]:
            if not path.exists():
                model = models.get_model(model_id)
                try:
                    png = xai_client.generate_tryon_image(
                        models.build_portrait_prompt(model.appearance))
                except Exception as e:  # noqa: BLE001
                    raise HTTPException(status_code=503, detail=str(e))
                path.write_bytes(png)
    return FileResponse(str(path), media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/diag")
def diag():
    out = {
        "has_key": bool(config.XAI_API_KEY),
        "configured": {
            "vision": config.XAI_VISION_MODELS,
            "image": config.XAI_IMAGE_MODELS,
            "video": config.XAI_VIDEO_MODELS,
        },
    }
    try:
        out["available_models"] = xai_client.list_models()
    except Exception as e:  # noqa: BLE001
        out["available_models_error"] = str(e)
    return out


def main():
    import uvicorn
    import os

    port = int(os.getenv("PORT", "8100"))
    uvicorn.run("grok_studio.app:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
