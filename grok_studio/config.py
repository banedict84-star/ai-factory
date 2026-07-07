"""설정 — 환경변수로 그록 API 키/모델/엔드포인트를 조정한다.

xAI 가 모델 식별자를 바꿔도 코드를 고칠 필요 없이 .env 로 바꿀 수 있게 전부
환경변수로 뺐다. 기본값은 2026년 기준 공개 스펙이다.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # python-dotenv 미설치여도 동작
    pass


# ── 그록(xAI) 접속 ─────────────────────────────────────────────
# 키는 절대 코드에 넣지 말 것. .env 또는 배포 환경변수로만.
XAI_API_KEY: str = os.getenv("XAI_API_KEY", "").strip()
XAI_BASE_URL: str = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1").rstrip("/")

# ── 모델 식별자 (xAI 스펙 변경 시 .env 로 교체) ────────────────
# 옷 분석용 비전 모델 (멀티모달 chat)
XAI_VISION_MODEL: str = os.getenv("XAI_VISION_MODEL", "grok-2-vision-1212")
# 모델이 옷 입은 사진 생성 (text-to-image)
XAI_IMAGE_MODEL: str = os.getenv("XAI_IMAGE_MODEL", "grok-2-image-1212")
# 영상 생성 (Grok Imagine, image-to-video)
XAI_VIDEO_MODEL: str = os.getenv("XAI_VIDEO_MODEL", "grok-imagine-video")

# ── 엔드포인트 경로 (base_url 뒤에 붙는다) ─────────────────────
IMAGE_PATH: str = os.getenv("XAI_IMAGE_PATH", "/images/generations")
VIDEO_PATH: str = os.getenv("XAI_VIDEO_PATH", "/videos/generations")
CHAT_PATH: str = os.getenv("XAI_CHAT_PATH", "/chat/completions")

# ── 영상 파라미터 기본값 ───────────────────────────────────────
VIDEO_DURATION: int = int(os.getenv("XAI_VIDEO_DURATION", "10"))
VIDEO_ASPECT_RATIO: str = os.getenv("XAI_VIDEO_ASPECT_RATIO", "9:16")  # 쇼핑몰 세로영상
VIDEO_RESOLUTION: str = os.getenv("XAI_VIDEO_RESOLUTION", "720p")

# 영상 폴링 (비동기 job 인 경우)
VIDEO_POLL_INTERVAL: float = float(os.getenv("XAI_VIDEO_POLL_INTERVAL", "5"))
VIDEO_POLL_TIMEOUT: float = float(os.getenv("XAI_VIDEO_POLL_TIMEOUT", "600"))

# 일반 요청 타임아웃(초)
HTTP_TIMEOUT: float = float(os.getenv("XAI_HTTP_TIMEOUT", "120"))

# ── 저장 위치 ─────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = Path(os.getenv("GROK_STUDIO_OUTPUT_DIR", str(BASE_DIR / "outputs")))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# (선택) 사이트 접속 비밀번호. 비우면 잠금 없음.
APP_PASSWORD: str = os.getenv("APP_PASSWORD", "").strip()


def require_key() -> str:
    """키가 없으면 명확한 에러를 던진다."""
    if not XAI_API_KEY:
        raise RuntimeError(
            "XAI_API_KEY 가 설정되지 않았습니다. .env 파일에 "
            "XAI_API_KEY=xai-... 를 넣어주세요."
        )
    return XAI_API_KEY
