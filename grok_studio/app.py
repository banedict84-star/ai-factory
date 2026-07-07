"""Grok Studio 웹앱 (FastAPI).

흐름:
  GET  /                     → 모델 3인 + 업로드 화면
  POST /api/generate         → 옷 업로드 + 모델 선택 → 백그라운드 job 시작, job_id 반환
  GET  /api/job/{id}         → 진행 상태 폴링 (분석 → 옷입은사진 → 영상)
  GET  /outputs/{file}       → 생성된 사진/영상 서빙

파이프라인은 스레드로 돌고 상태는 메모리에 둔다(단일 프로세스용 데모).
"""
from __future__ import annotations

import secrets
import threading
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import config, models, xai_client

app = FastAPI(title="Grok Studio — 쇼핑몰 모델 영상")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/outputs", StaticFiles(directory=str(config.OUTPUT_DIR)), name="outputs")


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


# ── 백그라운드 파이프라인 ─────────────────────────────────────
def _run_pipeline(job_id: str, model_id: str, image_bytes: bytes,
                  mime: str, motion: str) -> None:
    try:
        model = models.get_model(model_id)

        # 1) 옷 분석
        _set(job_id, stage="analyzing")
        garment = xai_client.analyze_garment(image_bytes, mime)
        _set(job_id, garment=garment)

        # 2) 모델이 옷 입은 사진
        _set(job_id, stage="generating_image")
        tryon_prompt = models.build_tryon_prompt(model.appearance, garment)
        tryon_png = xai_client.generate_tryon_image(tryon_prompt)
        img_name = f"{job_id}_tryon.png"
        (config.OUTPUT_DIR / img_name).write_bytes(tryon_png)
        _set(job_id, stage="image_ready", tryon_url=f"/outputs/{img_name}")

        # 3) 영상
        _set(job_id, stage="generating_video")
        video_prompt = models.build_video_prompt(model.name, motion)
        _set(job_id, video_prompt=video_prompt)
        remote_url = xai_client.generate_video(
            tryon_png, video_prompt,
            on_progress=lambda s: _set(job_id, video_status=s),
        )

        # 가능하면 로컬로 내려받아 서빙(외부 URL 만료 대비)
        video_url = remote_url
        try:
            vid = xai_client.download(remote_url)
            vid_name = f"{job_id}_video.mp4"
            (config.OUTPUT_DIR / vid_name).write_bytes(vid)
            video_url = f"/outputs/{vid_name}"
        except Exception:
            pass  # 내려받기 실패하면 원격 URL 그대로 사용

        _set(job_id, stage="done", video_url=video_url, remote_video_url=remote_url)

    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        _set(job_id, stage="error", error=str(e))


# ── 라우트 ────────────────────────────────────────────────────
def _check_auth(request: Request) -> None:
    if not config.APP_PASSWORD:
        return
    if request.cookies.get("gs_auth") == config.APP_PASSWORD:
        return
    raise HTTPException(status_code=401, detail="비밀번호가 필요합니다.")


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "models": models.MODELS,
            "default_motion": models.DEFAULT_MOTION_PROMPT,
            "has_key": bool(config.XAI_API_KEY),
            "needs_password": bool(config.APP_PASSWORD),
        },
    )


@app.post("/api/login")
def login(request: Request, password: str = Form(...)):
    if not config.APP_PASSWORD or secrets.compare_digest(password, config.APP_PASSWORD):
        resp = JSONResponse({"ok": True})
        if config.APP_PASSWORD:
            resp.set_cookie("gs_auth", config.APP_PASSWORD, httponly=True, samesite="lax")
        return resp
    raise HTTPException(status_code=401, detail="비밀번호가 틀렸습니다.")


@app.post("/api/generate")
async def generate(
    request: Request,
    model_id: str = Form(...),
    motion: str = Form(""),
    clothing: UploadFile = File(...),
):
    _check_auth(request)
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

    mime = clothing.content_type or "image/jpeg"
    motion = (motion or models.DEFAULT_MOTION_PROMPT).strip()

    job_id = uuid.uuid4().hex[:12]
    _set(job_id, stage="queued", model_id=model_id)
    threading.Thread(
        target=_run_pipeline,
        args=(job_id, model_id, image_bytes, mime, motion),
        daemon=True,
    ).start()
    return {"job_id": job_id}


@app.get("/api/diag")
def diag():
    """계정에서 실제 사용 가능한 모델 목록 + 현재 설정된 후보 모델."""
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


def main():
    import uvicorn
    import os

    port = int(os.getenv("PORT", "8100"))
    uvicorn.run("grok_studio.app:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
