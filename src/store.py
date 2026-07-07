"""게시 기록 저장소 — 올린 게시물을 output/posts.json 에 남깁니다.

반응(insights)을 나중에 다시 조회하려면 '무엇을 올렸는지'(media_id)를 알아야 합니다.
그래서 게시할 때마다 여기에 한 줄씩 기록하고, insights 명령이 이 기록을 읽습니다.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import config

POSTS_PATH = config.OUTPUT_DIR / "posts.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_posts(path: Path = POSTS_PATH) -> list[dict]:
    if not Path(path).exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def record_post(
    media_id: str,
    permalink: str = "",
    caption: str = "",
    topic: str = "",
    image_url: str = "",
    path: Path = POSTS_PATH,
) -> dict:
    """게시물 1건을 기록에 추가하고 그 항목을 반환합니다."""
    config.ensure_output_dir()
    posts = load_posts(path)
    entry = {
        "media_id": media_id,
        "permalink": permalink,
        "caption": caption,
        "topic": topic,
        "image_url": image_url,
        "posted_at": _now_iso(),
    }
    posts.append(entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)
    return entry


def recent(n: int = 10, path: Path = POSTS_PATH) -> list[dict]:
    """가장 최근 n건을 (최신순으로) 반환합니다."""
    return list(reversed(load_posts(path)))[:n]
