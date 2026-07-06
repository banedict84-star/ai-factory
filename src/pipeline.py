"""파이프라인 — 아이디어 → 영상 → 업로드 → 게시 를 순서대로 실행합니다."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import idea_generator, uploader, video_generator
from .idea_generator import VideoIdea
from .instagram_publisher import InstagramPublisher


@dataclass
class PipelineResult:
    idea: VideoIdea
    video_path: Path
    video_url: str | None = None
    media_id: str | None = None
    published: bool = False
    notes: list[str] = field(default_factory=list)


def run(dry_run: bool = False) -> PipelineResult:
    """전체 파이프라인 1회 실행.

    dry_run=True 면 아이디어·영상까지만 만들고 실제 게시는 하지 않습니다.
    """
    # 1) 아이디어
    idea = idea_generator.generate_idea()
    result = PipelineResult(idea=idea, video_path=Path())

    # 2) 영상
    video_path = video_generator.generate_video(idea)
    result.video_path = video_path

    if dry_run:
        result.notes.append("dry-run: 게시하지 않고 종료")
        return result

    # 3) 공개 URL 업로드
    video_url = uploader.upload_video(video_path)
    result.video_url = video_url
    if not video_url:
        result.notes.append(
            "UPLOADER 가 none 이라 공개 URL 이 없어 게시를 건너뜁니다. "
            "실제 게시하려면 UPLOADER 를 설정하세요."
        )
        return result

    # 4) 인스타 게시
    publisher = InstagramPublisher()
    media_id = publisher.publish_reel(video_url, idea.full_caption)
    result.media_id = media_id
    result.published = True
    return result
