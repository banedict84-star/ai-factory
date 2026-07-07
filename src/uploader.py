"""업로더 — 로컬 미디어(사진/영상)를 공개적으로 접근 가능한 URL 로 올립니다.

인스타그램 Graph API 는 로컬 파일이 아니라 '공개 URL' 을 요구합니다.
그래서 게시 전에 파일을 어딘가에 올리고 그 URL 을 넘겨야 합니다.

지원하는 업로더 (환경변수 `UPLOADER` 로 선택):
  - `imgur`  : 무료 익명 업로드. `IMGUR_CLIENT_ID` 만 있으면 됨 (사진 권장·기본).
  - `public` : 이미 배포된 서버의 공개 폴더에 파일이 있을 때, 그 URL 을 그대로 사용.
               `PUBLIC_MEDIA_BASE_URL` (예: https://내앱.onrender.com/media) 을 붙여 URL 생성.
  - `none`   : 업로드하지 않음 → 공개 URL 이 없으므로 실제 게시는 건너뜁니다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import requests

from . import config

IMGUR_API = "https://api.imgur.com/3/image"


class Uploader(ABC):
    @abstractmethod
    def upload(self, path: Path) -> str | None:
        """파일을 올리고 공개 URL 을 반환. None 이면 게시를 건너뜁니다."""
        raise NotImplementedError


class NoopUploader(Uploader):
    """업로드하지 않음 — 공개 URL 이 없으므로 실제 게시는 건너뜁니다."""

    def upload(self, path: Path) -> str | None:
        return None


class ImgurUploader(Uploader):
    """Imgur 익명 업로드. 사진/이미지에 적합하며 무료입니다.

    imgur.com → Settings → Applications 에서 앱을 등록하고 'Client ID' 를 받아
    `IMGUR_CLIENT_ID` 환경변수에 넣으면 됩니다. (OAuth 없이 익명 업로드 가능)
    """

    def __init__(self, client_id: str | None = None):
        self.client_id = client_id or config.env("IMGUR_CLIENT_ID", required=True)

    def upload(self, path: Path) -> str | None:
        with open(path, "rb") as f:
            resp = requests.post(
                IMGUR_API,
                headers={"Authorization": f"Client-ID {self.client_id}"},
                files={"image": f},
                data={"type": "file"},
                timeout=120,
            )
        resp.raise_for_status()
        payload = resp.json()
        if not payload.get("success"):
            raise RuntimeError(f"Imgur 업로드 실패: {payload}")
        return payload["data"]["link"]


class PublicUrlUploader(Uploader):
    """이미 공개 서버에 파일이 올라가 있는 경우, 그 파일의 공개 URL 을 만들어 반환.

    예) OMS 를 Render 에 배포했고 `/media/` 가 공개라면
        PUBLIC_MEDIA_BASE_URL=https://내앱.onrender.com/media 로 두면
        로컬 파일명(basename)을 붙여 공개 URL 을 구성합니다.
    실제로 그 URL 에 파일이 존재하는지는 확인하지 않습니다(배포 환경 전제).
    """

    def __init__(self, base_url: str | None = None):
        base = base_url or config.env("PUBLIC_MEDIA_BASE_URL", required=True)
        self.base_url = base.rstrip("/")

    def upload(self, path: Path) -> str | None:
        return f"{self.base_url}/{Path(path).name}"


def get_uploader(name: str | None = None) -> Uploader:
    name = (name or config.env("UPLOADER", "none")).lower()
    if name == "none":
        return NoopUploader()
    if name == "imgur":
        return ImgurUploader()
    if name == "public":
        return PublicUrlUploader()
    raise ValueError(
        f"알 수 없는 UPLOADER: {name!r}. 지원: none, imgur, public. "
        "다른 호스팅을 쓰려면 Uploader 를 상속해 구현하세요."
    )


def upload_file(path: Path) -> str | None:
    """사진이든 영상이든 로컬 파일 하나를 공개 URL 로 올립니다."""
    return get_uploader().upload(Path(path))


# 이전 코드 호환용 별칭
def upload_video(path: Path) -> str | None:
    return upload_file(path)


def upload_image(path: Path) -> str | None:
    return upload_file(path)
