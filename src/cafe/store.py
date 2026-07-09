"""런타임 설정 저장소 — 대시보드에서 바꾼 값을 GCS 에 저장합니다.

Cloud Run 은 파일이 휘발성이고 앱이 자기 env 를 못 바꾸므로, 발행 대상 게시판처럼
'앱에서 바꾸고 유지돼야 하는' 값은 GCS(이미지와 같은 버킷)에 둔다.
GCS 가 없으면 env 값으로 폴백한다.
"""
from __future__ import annotations

import json
import re

from .. import config

SETTINGS_OBJECT = "cafe-config/settings.json"


def _bucket():
    from google.cloud import storage

    name = config.env("CAFE_GCS_BUCKET")
    if not name:
        return None
    return storage.Client().bucket(name)


def load_settings() -> dict:
    b = _bucket()
    if not b:
        return {}
    try:
        blob = b.blob(SETTINGS_OBJECT)
        if not blob.exists():
            return {}
        return json.loads(blob.download_as_bytes())
    except Exception:
        return {}


def save_settings(data: dict) -> None:
    b = _bucket()
    if not b:
        raise RuntimeError(
            "CAFE_GCS_BUCKET 가 설정되지 않아 저장할 수 없습니다. 버킷을 먼저 지정하세요."
        )
    blob = b.blob(SETTINGS_OBJECT)
    blob.upload_from_string(
        json.dumps(data, ensure_ascii=False), content_type="application/json"
    )


def get_target() -> tuple[str | None, str | None]:
    """발행 대상 (club_id, menu_id). GCS 저장값 우선, 없으면 env."""
    s = load_settings()
    club = s.get("club_id") or config.env("NAVER_CAFE_CLUB_ID")
    menu = s.get("menu_id") or config.env("NAVER_CAFE_MENU_ID")
    return club, menu


def set_target(club_id: str, menu_id: str) -> None:
    s = load_settings()
    s["club_id"] = str(club_id).strip()
    s["menu_id"] = str(menu_id).strip()
    save_settings(s)


def parse_board_url(url: str) -> tuple[str | None, str | None]:
    """카페 게시판 URL 에서 club_id, menu_id 를 추출합니다.

    지원: .../cafes/<clubid>/menus/<menuid>  또는  ...clubid=..&menuid=..
    """
    m = re.search(r"cafes/(\d+)/menus/(\d+)", url)
    if m:
        return m.group(1), m.group(2)
    c = re.search(r"clubid=(\d+)", url)
    mn = re.search(r"menuid=(\d+)", url)
    if c and mn:
        return c.group(1), mn.group(1)
    return None, None
