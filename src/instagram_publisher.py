"""인스타그램 게시 — Instagram Graph API 로 릴스(Reels)를 올립니다.

릴스 게시는 3단계입니다:
  1) 미디어 컨테이너 생성 (video_url + caption)
  2) 처리 완료(FINISHED)까지 상태 폴링
  3) 게시(publish)

전제: 인스타 프로페셔널 계정 + 연결된 페이스북 페이지 + Meta 앱 + 액세스 토큰.
video_url 은 반드시 공개적으로 접근 가능한 URL 이어야 합니다(uploader 참고).
"""
from __future__ import annotations

import time

import requests

from . import config

GRAPH_API = "https://graph.facebook.com/v21.0"


class InstagramPublisher:
    def __init__(self, account_id: str | None = None, access_token: str | None = None):
        self.account_id = account_id or config.env("INSTAGRAM_ACCOUNT_ID", required=True)
        self.access_token = access_token or config.env(
            "INSTAGRAM_ACCESS_TOKEN", required=True
        )

    def publish_reel(self, video_url: str, caption: str) -> str:
        """릴스를 게시하고 게시된 미디어 ID 를 반환합니다."""
        container_id = self._create_container(video_url, caption)
        self._wait_until_ready(container_id)
        return self._publish(container_id)

    def publish_photo(self, image_url: str, caption: str) -> str:
        """사진(피드 이미지)을 게시하고 게시된 미디어 ID 를 반환합니다.

        모델 컷처럼 정지 이미지 1장을 올릴 때 씁니다. 사진 컨테이너는 대개
        곧바로 준비되지만, 만약을 위해 릴스와 동일하게 준비 상태를 폴링합니다.
        image_url 은 공개적으로 접근 가능한 URL 이어야 합니다(uploader 참고).
        """
        container_id = self._create_container(image_url, caption, media_type="IMAGE")
        self._wait_until_ready(container_id)
        return self._publish(container_id)

    def _create_container(
        self, media_url: str, caption: str, media_type: str = "REELS"
    ) -> str:
        # REELS 는 video_url, IMAGE 는 image_url 로 필드명이 다릅니다.
        url_field = "image_url" if media_type == "IMAGE" else "video_url"
        data = {
            "media_type": media_type,
            url_field: media_url,
            "caption": caption,
            "access_token": self.access_token,
        }
        resp = requests.post(
            f"{GRAPH_API}/{self.account_id}/media",
            data=data,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def _wait_until_ready(self, container_id: str, timeout_s: int = 300) -> None:
        """영상 처리는 시간이 걸립니다. FINISHED 될 때까지 폴링합니다."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            resp = requests.get(
                f"{GRAPH_API}/{container_id}",
                params={"fields": "status_code", "access_token": self.access_token},
                timeout=30,
            )
            resp.raise_for_status()
            status = resp.json().get("status_code")
            if status == "FINISHED":
                return
            if status == "ERROR":
                raise RuntimeError("인스타그램 영상 처리 중 오류(ERROR) 발생")
            time.sleep(5)
        raise TimeoutError("영상 처리 대기 시간 초과")

    def _publish(self, container_id: str) -> str:
        resp = requests.post(
            f"{GRAPH_API}/{self.account_id}/media_publish",
            data={"creation_id": container_id, "access_token": self.access_token},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["id"]
