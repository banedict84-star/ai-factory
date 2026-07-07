"""그록(xAI) API 클라이언트.

3가지 능력만 노출한다:
  - analyze_garment(image_bytes)      → 업로드한 옷의 상세 설명(영어)
  - generate_tryon_image(prompt)      → 모델이 옷 입은 사진 (bytes)
  - generate_video(image_bytes, prompt) → 영상 URL

xAI 는 OpenAI 호환이다. 영상 API 는 동기(바로 URL 반환) 또는 비동기(job → 폴링)
둘 다 있을 수 있어 응답 모양을 유연하게 파싱한다.
"""
from __future__ import annotations

import base64
import time
from typing import Any

import requests

from . import config


class XAIError(RuntimeError):
    """그록 API 호출 실패."""


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.require_key()}",
        "Content-Type": "application/json",
    }


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{config.XAI_BASE_URL}{path}"
    try:
        r = requests.post(url, headers=_headers(), json=payload,
                          timeout=config.HTTP_TIMEOUT)
    except requests.RequestException as e:
        raise XAIError(f"그록 요청 실패({path}): {e}") from e
    if r.status_code >= 400:
        raise XAIError(f"그록 오류 {r.status_code} ({path}): {r.text[:500]}")
    try:
        return r.json()
    except ValueError as e:
        raise XAIError(f"그록 응답 파싱 실패({path}): {r.text[:300]}") from e


def _get(path: str) -> dict[str, Any]:
    url = f"{config.XAI_BASE_URL}{path}"
    try:
        r = requests.get(url, headers=_headers(), timeout=config.HTTP_TIMEOUT)
    except requests.RequestException as e:
        raise XAIError(f"그록 폴링 실패({path}): {e}") from e
    if r.status_code >= 400:
        raise XAIError(f"그록 폴링 오류 {r.status_code} ({path}): {r.text[:500]}")
    return r.json()


def _data_uri(image_bytes: bytes, mime: str = "image/png") -> str:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _is_model_error(msg: str) -> bool:
    """'그 모델은 없다' 류의 에러인지 — 이러면 다음 후보 모델로 넘어간다."""
    low = msg.lower()
    return (
        "model not found" in low
        or "does not exist" in low
        or "no such model" in low
        or "unknown model" in low
        or "not supported" in low
        or "unsupported model" in low
        or "invalid model" in low
    )


def list_models() -> list[str]:
    """계정에서 실제 사용 가능한 모델 id 목록 (진단용)."""
    ids: list[str] = []
    for path in ("/models", "/image-generation-models", "/language-models"):
        try:
            data = _get(path)
        except XAIError:
            continue
        items = data.get("data") or data.get("models") or []
        for it in items:
            mid = it.get("id") if isinstance(it, dict) else None
            if mid and mid not in ids:
                ids.append(mid)
    return ids


# ── 1) 옷 분석 (비전) ─────────────────────────────────────────
GARMENT_SYSTEM = (
    "You are a fashion e-commerce assistant. Look at the clothing item in the "
    "image and describe ONLY the garment(s) for an image-generation prompt. "
    "Be concrete: garment type, color(s), pattern, fabric/material, silhouette/cut, "
    "sleeve/length, neckline, and notable details (buttons, print, texture). "
    "Ignore any person, background, or mannequin. Answer in one dense English "
    "sentence, no preamble."
)


def analyze_garment(image_bytes: bytes, mime: str = "image/jpeg") -> str:
    messages = [
        {"role": "system", "content": GARMENT_SYSTEM},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this clothing for a try-on image prompt."},
                {"type": "image_url",
                 "image_url": {"url": _data_uri(image_bytes, mime)}},
            ],
        },
    ]
    last: Exception | None = None
    for model in config.XAI_VISION_MODELS:
        payload = {"model": model, "messages": messages, "temperature": 0.2}
        try:
            data = _post(config.CHAT_PATH, payload)
        except XAIError as e:
            last = e
            if _is_model_error(str(e)):
                continue  # 다음 후보 모델
            raise
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as e:
            raise XAIError(f"옷 분석 응답 형식 오류: {str(data)[:300]}") from e
    raise XAIError(
        "사용 가능한 비전 모델을 못 찾았습니다. XAI_VISION_MODEL 을 확인하세요. "
        f"(마지막 오류: {last})"
    )


# ── 2) 모델이 옷 입은 사진 생성 ────────────────────────────────
def generate_tryon_image(prompt: str) -> bytes:
    last: Exception | None = None
    for model in config.XAI_IMAGE_MODELS:
        payload = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "response_format": "b64_json",
        }
        try:
            data = _post(config.IMAGE_PATH, payload)
        except XAIError as e:
            # 이미지는 검증된 폴백 모델이 있으므로 어떤 오류든 다음 후보로 시도.
            # (새 품질 모델이 파라미터를 거부해도 기존 모델로 안전하게 넘어감)
            last = e
            if model != config.XAI_IMAGE_MODELS[-1]:
                continue
            raise
        try:
            item = data["data"][0]
        except (KeyError, IndexError, TypeError) as e:
            raise XAIError(f"이미지 응답 형식 오류: {str(data)[:300]}") from e
        if item.get("b64_json"):
            return base64.b64decode(item["b64_json"])
        if item.get("url"):
            img = requests.get(item["url"], timeout=config.HTTP_TIMEOUT)
            img.raise_for_status()
            return img.content
        raise XAIError(f"이미지 데이터 없음: {str(item)[:300]}")
    raise XAIError(
        "사용 가능한 이미지 모델을 못 찾았습니다. XAI_IMAGE_MODEL 을 확인하세요. "
        f"(마지막 오류: {last})"
    )


# ── 3) 영상 생성 (image-to-video) ─────────────────────────────
def _extract_status(obj: dict[str, Any]) -> str:
    return str(obj.get("status") or obj.get("state") or "").lower()


def _extract_video_url(obj: Any) -> str | None:
    """다양한 응답 모양에서 영상 URL 을 뽑아낸다."""
    if isinstance(obj, str):
        return obj if obj.startswith("http") else None
    if isinstance(obj, dict):
        # 흔한 위치들
        for key in ("video_url", "url", "video", "output", "result"):
            if key in obj:
                found = _extract_video_url(obj[key])
                if found:
                    return found
        # data / videos 배열
        for key in ("data", "videos", "outputs"):
            if key in obj:
                found = _extract_video_url(obj[key])
                if found:
                    return found
    if isinstance(obj, list):
        for it in obj:
            found = _extract_video_url(it)
            if found:
                return found
    return None


def _extract_job_id(obj: dict[str, Any]) -> str | None:
    for key in ("id", "job_id", "request_id", "generation_id"):
        if obj.get(key):
            return str(obj[key])
    return None


def generate_video(image_bytes: bytes, prompt: str,
                   duration: int | None = None,
                   on_progress=None) -> str:
    """참조 이미지 + 프롬프트로 영상 생성. 완성된 영상 URL 을 반환.

    on_progress: 선택. 상태 문자열을 받는 콜백.
    """
    base_payload = {
        "prompt": prompt,
        "image": {"url": _data_uri(image_bytes, "image/png")},
        "duration": duration or config.VIDEO_DURATION,
        "aspect_ratio": config.VIDEO_ASPECT_RATIO,
        "resolution": config.VIDEO_RESOLUTION,
    }
    data = None
    last: Exception | None = None
    for model in config.XAI_VIDEO_MODELS:
        try:
            data = _post(config.VIDEO_PATH, {"model": model, **base_payload})
            break
        except XAIError as e:
            last = e
            if _is_model_error(str(e)):
                continue
            raise
    if data is None:
        raise XAIError(
            "사용 가능한 영상 모델을 못 찾았습니다. XAI_VIDEO_MODEL 을 확인하세요. "
            f"(마지막 오류: {last})"
        )

    # 동기 응답: 바로 URL 이 오는 경우
    status = _extract_status(data)
    url = _extract_video_url(data)
    if url and status in ("", "done", "completed", "succeeded", "success"):
        return url

    # 비동기 job: 폴링
    job_id = _extract_job_id(data)
    if not job_id:
        # id 도 없고 url 도 없으면 실패로 본다
        if url:
            return url
        raise XAIError(f"영상 응답을 이해할 수 없음: {str(data)[:400]}")

    deadline = time.monotonic() + config.VIDEO_POLL_TIMEOUT
    # 제출: POST /v1/videos/generations → 폴링: GET /v1/videos/{request_id}
    poll_path = f"{config.VIDEO_STATUS_PATH}/{job_id}"
    while time.monotonic() < deadline:
        if on_progress:
            on_progress(status or "processing")
        time.sleep(config.VIDEO_POLL_INTERVAL)
        job = _get(poll_path)
        status = _extract_status(job)
        if status in ("failed", "error", "canceled", "cancelled", "expired"):
            raise XAIError(f"영상 생성 실패: {str(job)[:400]}")
        url = _extract_video_url(job)
        if url and status in ("done", "completed", "succeeded", "success", ""):
            return url
        if url and status in ("processing", "pending", "running", "queued"):
            # 일부 API 는 진행 중에도 임시 url 을 줄 수 있으니 완료 상태만 신뢰
            continue

    raise XAIError("영상 생성 시간 초과(timeout). 프롬프트를 짧게 하거나 재시도하세요.")


def download(url: str) -> bytes:
    r = requests.get(url, timeout=config.HTTP_TIMEOUT)
    r.raise_for_status()
    return r.content
