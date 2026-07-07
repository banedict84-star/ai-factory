"""반응 수집 — 게시한 사진에 사람들이 어떻게 반응했는지 인스타 Graph API 로 긁어옵니다.

두 종류의 정보를 모읍니다:
  1) 미디어 기본 필드 : like_count, comments_count, caption, permalink, timestamp
  2) 인사이트(metric) : reach(도달), saved(저장), shares(공유),
                        total_interactions(총 상호작용), profile_visits 등

⚠️ 인사이트 metric 은 계정 종류·미디어 종류·게시 시점에 따라 지원 여부가 달라집니다
   (예: Meta 가 2024년 이후 일부 미디어의 impressions 를 없앰). 그래서 지원되지 않는
   metric 은 조용히 건너뛰고, 되는 것만 모읍니다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import requests

from . import config

GRAPH_API = "https://graph.facebook.com/v21.0"

# 미디어 노드에 바로 붙는 기본 필드
BASIC_FIELDS = "id,caption,media_type,permalink,timestamp,like_count,comments_count"

# 사진(피드 이미지) 게시물에서 시도해볼 인사이트 metric 후보
PHOTO_METRICS = [
    "reach",
    "saved",
    "shares",
    "total_interactions",
    "profile_visits",
    "follows",
]


@dataclass
class Reactions:
    media_id: str
    permalink: str = ""
    caption: str = ""
    timestamp: str = ""
    like_count: int = 0
    comments_count: int = 0
    insights: dict[str, int] = field(default_factory=dict)

    @property
    def total_engagement(self) -> int:
        """간단 지표: 좋아요 + 댓글 + 저장 + 공유."""
        return (
            self.like_count
            + self.comments_count
            + self.insights.get("saved", 0)
            + self.insights.get("shares", 0)
        )

    def summary_line(self) -> str:
        i = self.insights
        parts = [
            f"❤️ {self.like_count}",
            f"💬 {self.comments_count}",
        ]
        if "saved" in i:
            parts.append(f"🔖 {i['saved']}")
        if "reach" in i:
            parts.append(f"👀 도달 {i['reach']}")
        if "shares" in i:
            parts.append(f"🔁 {i['shares']}")
        head = self.caption.strip().splitlines()[0] if self.caption.strip() else self.media_id
        return f"{head[:32]:<32}  " + "  ".join(parts)


def _access_token(token: str | None) -> str:
    return token or config.env("INSTAGRAM_ACCESS_TOKEN", required=True)


def fetch_basic(media_id: str, access_token: str | None = None) -> dict:
    resp = requests.get(
        f"{GRAPH_API}/{media_id}",
        params={"fields": BASIC_FIELDS, "access_token": _access_token(access_token)},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_insights(
    media_id: str,
    metrics: list[str] | None = None,
    access_token: str | None = None,
) -> dict[str, int]:
    """인사이트 metric 을 모읍니다. 지원되지 않는 metric 은 건너뜁니다.

    먼저 전체를 한 번에 요청하고, 400(지원 안 됨) 이면 metric 을 하나씩 재시도합니다.
    """
    token = _access_token(access_token)
    metrics = metrics or PHOTO_METRICS

    def _request(metric_csv: str) -> requests.Response:
        return requests.get(
            f"{GRAPH_API}/{media_id}/insights",
            params={"metric": metric_csv, "access_token": token},
            timeout=30,
        )

    resp = _request(",".join(metrics))
    if resp.status_code == 400:
        # 하나씩 시도해서 되는 것만 수집
        result: dict[str, int] = {}
        for m in metrics:
            r = _request(m)
            if r.status_code == 200:
                result.update(_parse_insights(r.json()))
        return result
    resp.raise_for_status()
    return _parse_insights(resp.json())


def _parse_insights(payload: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for entry in payload.get("data", []):
        name = entry.get("name")
        values = entry.get("values") or []
        if name and values:
            out[name] = values[0].get("value", 0)
    return out


def fetch_reactions(media_id: str, access_token: str | None = None) -> Reactions:
    """한 게시물의 반응(기본 + 인사이트)을 한 번에 모아 반환합니다."""
    token = _access_token(access_token)
    basic = fetch_basic(media_id, token)
    insights = fetch_insights(media_id, access_token=token)
    return Reactions(
        media_id=media_id,
        permalink=basic.get("permalink", ""),
        caption=basic.get("caption", ""),
        timestamp=basic.get("timestamp", ""),
        like_count=basic.get("like_count", 0),
        comments_count=basic.get("comments_count", 0),
        insights=insights,
    )


def fetch_recent_media_ids(
    limit: int = 10,
    account_id: str | None = None,
    access_token: str | None = None,
) -> list[str]:
    """로컬 기록 없이도, 계정에 실제로 올라간 최근 게시물의 media_id 목록을 가져옵니다.

    GitHub Actions 처럼 상태가 남지 않는 환경에서 반응을 조회할 때 유용합니다.
    """
    token = _access_token(access_token)
    account = account_id or config.env("INSTAGRAM_ACCOUNT_ID", required=True)
    resp = requests.get(
        f"{GRAPH_API}/{account}/media",
        params={"fields": "id", "limit": limit, "access_token": token},
        timeout=30,
    )
    resp.raise_for_status()
    return [item["id"] for item in resp.json().get("data", [])]
