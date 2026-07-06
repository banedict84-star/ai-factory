"""진입점 — `python -m src.main [--dry-run]`"""
from __future__ import annotations

import argparse
import sys

from . import pipeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI Factory — 인스타 자동 영상 게시")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 게시 없이 아이디어·영상 생성까지만 실행",
    )
    args = parser.parse_args(argv)

    result = pipeline.run(dry_run=args.dry_run)

    print("─" * 50)
    print(f"소재      : {result.idea.topic}")
    print(f"컨셉      : {result.idea.concept}")
    print(f"영상 프롬프트: {result.idea.video_prompt}")
    print(f"캡션      :\n{result.idea.full_caption}")
    print(f"영상 파일 : {result.video_path}")
    if result.video_url:
        print(f"영상 URL  : {result.video_url}")
    if result.published:
        print(f"✅ 게시 완료 (media_id={result.media_id})")
    for note in result.notes:
        print(f"ℹ️  {note}")
    print("─" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
