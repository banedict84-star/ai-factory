"""업로더 — 영상을 공개적으로 접근 가능한 URL 로 올립니다.

인스타그램 Graph API 는 로컬 파일이 아니라 '공개 URL' 을 요구합니다.
그래서 게시 전에 영상을 S3/GCS 같은 곳에 올리고 그 URL 을 넘겨야 합니다.

기본값 `none` 은 업로드를 하지 않아, 실제 게시는 건너뛰고 로컬 확인만 합니다.
실제 운영 시에는 S3Uploader 같은 구현을 추가하고 UPLOADER 환경변수를 바꾸세요.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from . import config


class Uploader(ABC):
    @abstractmethod
    def upload(self, path: Path) -> str | None:
        """파일을 올리고 공개 URL 을 반환. None 이면 게시를 건너뜁니다."""
        raise NotImplementedError


class NoopUploader(Uploader):
    """업로드하지 않음 — 공개 URL 이 없으므로 실제 게시는 건너뜁니다."""

    def upload(self, path: Path) -> str | None:
        return None


def get_uploader(name: str | None = None) -> Uploader:
    name = name or config.env("UPLOADER", "none")
    if name == "none":
        return NoopUploader()
    # 예: if name == "s3": return S3Uploader()
    raise ValueError(
        f"알 수 없는 UPLOADER: {name!r}. 지원: none. "
        "실제 호스팅을 쓰려면 Uploader 를 상속해 구현하세요."
    )


def upload_video(path: Path) -> str | None:
    return get_uploader().upload(path)
