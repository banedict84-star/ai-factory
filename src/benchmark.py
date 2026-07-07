"""벤치마크 — 잘되는 채널을 '공식 API'로 분석해서, 뭐가 먹히는지 패턴을 뽑습니다.

인스타 Graph API 의 **Business Discovery** 를 씁니다. 남의 계정을 @아이디로 지정하면
그 계정의 공개 정보(팔로워 수, 최근 게시물의 캡션·좋아요·댓글·시간)를 합법적으로
가져올 수 있습니다.

  - 대상은 **비즈니스/크리에이터 계정**이어야 합니다(개인 계정은 조회 불가).
  - 남의 계정의 도달·저장 같은 내부 인사이트는 볼 수 없습니다(공개 지표만).
  - ⚠️ 이미지·글을 그대로 베끼는 용도가 아니라, **패턴(소재·포맷·해시태그·주기)**을
    학습해 우리 브랜드로 재창조하기 위한 것입니다.

필요: INSTAGRAM_ACCOUNT_ID(내 계정) + INSTAGRAM_ACCESS_TOKEN
     (권한: instagram_basic, instagram_manage_insights)
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import requests

from . import config

GRAPH_API = "https://graph.facebook.com/v21.0"
KST = timezone(timedelta(hours=9))

# 캡션에서 해시태그 뽑기 (한글/영문/숫자/밑줄)
_HASHTAG_RE = re.compile(r"#([0-9A-Za-z_가-힣]+)")

BENCHMARK_PATH = config.OUTPUT_DIR / "benchmark.json"


@dataclass
class BenchmarkReport:
    usernames: list[str] = field(default_factory=list)
    followers: dict[str, int] = field(default_factory=dict)
    sample_size: int = 0
    avg_engagement: float = 0.0
    top_hashtags: list[tuple[str, int]] = field(default_factory=list)
    top_posts: list[dict] = field(default_factory=list)
    best_hours_kst: list[int] = field(default_factory=list)
    posts_per_week: float = 0.0
    media_mix: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "usernames": self.usernames,
            "followers": self.followers,
            "sample_size": self.sample_size,
            "avg_engagement": round(self.avg_engagement, 1),
            "top_hashtags": self.top_hashtags,
            "top_posts": self.top_posts,
            "best_hours_kst": self.best_hours_kst,
            "posts_per_week": round(self.posts_per_week, 1),
            "media_mix": self.media_mix,
        }

    def to_prompt_hints(self) -> str:
        """Claude 기획 프롬프트에 넣을 압축 힌트(한국어)."""
        tags = " ".join(f"#{t}" for t, _ in self.top_hashtags[:12]) or "(없음)"
        hours = ", ".join(f"{h}시" for h in self.best_hours_kst[:3]) or "(불명)"
        examples = "\n".join(
            f"  - (❤️{p['engagement']}) {p['caption_head']}" for p in self.top_posts[:5]
        ) or "  - (없음)"
        return (
            f"[벤치마크: {', '.join('@'+u for u in self.usernames)}]\n"
            f"- 게시물당 평균 반응(좋아요+댓글): 약 {self.avg_engagement:.0f}\n"
            f"- 올리는 주기: 주 {self.posts_per_week:.1f}회, 반응 좋은 시간대(KST): {hours}\n"
            f"- 자주 쓰는 해시태그: {tags}\n"
            f"- 반응이 특히 좋았던 게시물(소재/톤 참고용):\n{examples}\n"
        )

    def summary_text(self) -> str:
        lines = [
            f"벤치마크 대상: {', '.join('@'+u for u in self.usernames)}",
            f"표본 게시물: {self.sample_size}개",
            f"팔로워: " + ", ".join(f"@{u} {n:,}" for u, n in self.followers.items()),
            f"게시물당 평균 반응: {self.avg_engagement:.0f} (좋아요+댓글)",
            f"게시 주기: 주 {self.posts_per_week:.1f}회",
            f"반응 좋은 시간대(KST): " + (", ".join(f"{h}시" for h in self.best_hours_kst[:3]) or "불명"),
            f"미디어 구성: " + ", ".join(f"{k} {v}" for k, v in self.media_mix.items()),
            "자주 쓰는 해시태그 TOP: " + " ".join(f"#{t}({c})" for t, c in self.top_hashtags[:12]),
            "반응 좋은 게시물 TOP:",
        ]
        for p in self.top_posts[:5]:
            lines.append(f"  ❤️{p['engagement']:>5}  {p['caption_head']}")
            if p.get("permalink"):
                lines.append(f"         {p['permalink']}")
        return "\n".join(lines)


def discover(username: str, limit: int = 25,
             account_id: str | None = None, access_token: str | None = None) -> dict:
    """Business Discovery 로 한 계정의 프로필+최근 게시물을 가져옵니다."""
    account = account_id or config.env("INSTAGRAM_ACCOUNT_ID", required=True)
    token = access_token or config.env("INSTAGRAM_ACCESS_TOKEN", required=True)
    username = username.lstrip("@")
    media_fields = "caption,like_count,comments_count,timestamp,permalink,media_type"
    field_expr = (
        f"business_discovery.username({username})"
        f"{{followers_count,media_count,media.limit({limit}){{{media_fields}}}}}"
    )
    resp = requests.get(
        f"{GRAPH_API}/{account}",
        params={"fields": field_expr, "access_token": token},
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"@{username} 조회 실패({resp.status_code}). 대상이 비즈니스/크리에이터 "
            f"계정인지, 토큰 권한(instagram_manage_insights)을 확인하세요.\n{resp.text}"
        )
    return resp.json().get("business_discovery", {})


def _hashtags(caption: str) -> list[str]:
    return [m.lower() for m in _HASHTAG_RE.findall(caption or "")]


def _caption_head(caption: str, n: int = 40) -> str:
    first = (caption or "").strip().splitlines()[0] if (caption or "").strip() else "(캡션 없음)"
    return first[:n]


def analyze(discoveries: dict[str, dict]) -> BenchmarkReport:
    """여러 계정의 discovery 결과를 합쳐 하나의 리포트로 분석합니다."""
    report = BenchmarkReport(usernames=list(discoveries.keys()))
    all_media: list[dict] = []
    hashtag_counter: Counter[str] = Counter()
    hour_counter: Counter[int] = Counter()
    media_mix: Counter[str] = Counter()
    timestamps: list[datetime] = []

    for username, disc in discoveries.items():
        report.followers[username] = disc.get("followers_count", 0)
        for m in (disc.get("media", {}) or {}).get("data", []):
            eng = m.get("like_count", 0) + m.get("comments_count", 0)
            entry = {
                "username": username,
                "engagement": eng,
                "like_count": m.get("like_count", 0),
                "comments_count": m.get("comments_count", 0),
                "caption_head": _caption_head(m.get("caption", "")),
                "permalink": m.get("permalink", ""),
                "media_type": m.get("media_type", ""),
            }
            all_media.append(entry)
            hashtag_counter.update(_hashtags(m.get("caption", "")))
            media_mix.update([m.get("media_type", "UNKNOWN")])
            ts = m.get("timestamp")
            if ts:
                try:
                    dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z").astimezone(KST)
                    timestamps.append(dt)
                    hour_counter.update([dt.hour])
                except ValueError:
                    pass

    report.sample_size = len(all_media)
    if all_media:
        report.avg_engagement = sum(m["engagement"] for m in all_media) / len(all_media)
        report.top_posts = sorted(all_media, key=lambda m: m["engagement"], reverse=True)[:8]
    report.top_hashtags = hashtag_counter.most_common(20)
    report.best_hours_kst = [h for h, _ in hour_counter.most_common(3)]
    report.media_mix = dict(media_mix)

    if len(timestamps) >= 2:
        span = (max(timestamps) - min(timestamps)).total_seconds() / 86400  # 일
        if span > 0:
            report.posts_per_week = len(timestamps) / span * 7

    return report


def build_report(usernames: list[str], limit: int = 25) -> BenchmarkReport:
    """@아이디 목록을 받아 각각 조회 후 하나의 벤치마크 리포트로 종합합니다."""
    discoveries: dict[str, dict] = {}
    for u in usernames:
        u = u.lstrip("@")
        discoveries[u] = discover(u, limit=limit)
    return analyze(discoveries)


def save(report: BenchmarkReport, path=BENCHMARK_PATH) -> None:
    config.ensure_output_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)


def load_hints(path=BENCHMARK_PATH) -> str | None:
    """저장된 벤치마크가 있으면 기획 프롬프트용 힌트 문자열로 돌려줍니다(없으면 None)."""
    from pathlib import Path

    if not Path(path).exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    report = BenchmarkReport(
        usernames=data.get("usernames", []),
        followers=data.get("followers", {}),
        sample_size=data.get("sample_size", 0),
        avg_engagement=data.get("avg_engagement", 0.0),
        top_hashtags=[tuple(x) for x in data.get("top_hashtags", [])],
        top_posts=data.get("top_posts", []),
        best_hours_kst=data.get("best_hours_kst", []),
        posts_per_week=data.get("posts_per_week", 0.0),
        media_mix=data.get("media_mix", {}),
    )
    return report.to_prompt_hints()
