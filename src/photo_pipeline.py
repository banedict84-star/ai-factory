"""사진 파이프라인 — 모델 컷 1장을 기획→생성→호스팅→게시→기록 까지 한 바퀴 돌립니다.

흐름:
  1) Claude 가 오늘의 컷 컨셉/이미지 프롬프트/캡션/해시태그 기획
  2) OpenAI 가 이미지 프롬프트로 실제 모델 컷 PNG 생성
  3) 업로더가 공개 URL 로 호스팅 (Imgur 등)
  4) 인스타 Graph API 로 사진 게시
  5) media_id 를 output/posts.json 에 기록 (나중에 반응 조회용)

dry_run=True 면 기획·이미지까지만 만들고 게시는 건너뜁니다(키/토큰 없이 확인용).
기존에 만들어둔 이미지가 있으면 image_path 로 넘겨 생성을 건너뛸 수도 있습니다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import benchmark, idea_generator, photo_generator, store, uploader
from .idea_generator import PhotoIdea
from .instagram_publisher import InstagramPublisher


@dataclass
class PhotoResult:
    idea: PhotoIdea
    image_path: Path
    image_url: str | None = None
    media_id: str | None = None
    permalink: str = ""
    published: bool = False
    notes: list[str] = field(default_factory=list)


def run(dry_run: bool = False, image_path: Path | None = None) -> PhotoResult:
    """모델 컷 게시 파이프라인 1회 실행.

    output/benchmark.json 이 있으면 '잘되는 채널' 패턴을 반영해 기획합니다.
    (먼저 `python -m src.main benchmark @계정...` 을 돌려두면 생성됩니다.)
    """
    # 1) 기획 (벤치마크가 있으면 그 패턴을 반영)
    hints = benchmark.load_hints()
    idea = idea_generator.generate_photo_idea(hints=hints)

    # 2) 이미지 (이미 만든 컷이 있으면 그대로 사용)
    if image_path is not None:
        img = Path(image_path)
    else:
        img = photo_generator.generate_photo(
            idea.image_prompt, name="model_cut", title=idea.topic
        )
    result = PhotoResult(idea=idea, image_path=img)
    if hints:
        result.notes.append("벤치마크 패턴을 반영해 기획했습니다 (output/benchmark.json)")

    if dry_run:
        result.notes.append("dry-run: 게시하지 않고 종료")
        return result

    # 3) 공개 URL 호스팅
    image_url = uploader.upload_image(img)
    result.image_url = image_url
    if not image_url:
        result.notes.append(
            "UPLOADER 가 none 이라 공개 URL 이 없어 게시를 건너뜁니다. "
            "실제 게시하려면 UPLOADER=imgur(또는 public) 로 설정하세요."
        )
        return result

    # 4) 인스타 사진 게시
    publisher = InstagramPublisher()
    media_id = publisher.publish_photo(image_url, idea.full_caption)
    result.media_id = media_id
    result.published = True

    # 5) 기록 (반응 조회용) — permalink 도 함께 저장
    permalink = ""
    try:
        from . import insights

        permalink = insights.fetch_basic(media_id).get("permalink", "")
    except Exception:
        pass
    result.permalink = permalink
    store.record_post(
        media_id=media_id,
        permalink=permalink,
        caption=idea.caption,
        topic=idea.topic,
        image_url=image_url,
    )
    return result
