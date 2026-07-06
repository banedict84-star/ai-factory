"""영상 생성 — 제공자(provider) 교체 가능한 구조.

기본 제공자는 `placeholder`: 텍스트 카드 영상을 만들어 전체 파이프라인을 끝까지 시험해볼 수 있게 합니다.
나중에 실제 텍스트→영상 AI 서비스를 `AIVideoProvider` 형태로 추가해 VIDEO_PROVIDER 로 갈아끼우면 됩니다.
"""
from __future__ import annotations

import shutil
import subprocess
import textwrap
from abc import ABC, abstractmethod
from pathlib import Path

from PIL import Image, ImageDraw

from . import config
from .idea_generator import VideoIdea


class VideoProvider(ABC):
    """영상 생성 제공자 인터페이스. 새 제공자는 이 클래스를 상속해 generate 만 구현하면 됩니다."""

    @abstractmethod
    def generate(self, idea: VideoIdea, out_path: Path) -> Path:
        """idea 를 받아 out_path 에 영상 파일을 만들고 그 경로를 반환합니다."""
        raise NotImplementedError


class PlaceholderProvider(VideoProvider):
    """텍스트 카드 → 짧은 세로 MP4. 실제 AI 영상 대신 흐름 검증용."""

    WIDTH, HEIGHT = 1080, 1920  # 9:16

    def generate(self, idea: VideoIdea, out_path: Path) -> Path:
        if not shutil.which("ffmpeg"):
            raise RuntimeError(
                "placeholder 영상 생성에는 ffmpeg 가 필요합니다. "
                "설치하거나 VIDEO_PROVIDER 를 실제 제공자로 바꾸세요."
            )

        content = config.load_content_config()
        duration = content.get("video", {}).get("duration_seconds", 8)

        card = out_path.with_suffix(".png")
        self._render_card(idea, card)

        subprocess.run(
            [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", str(card),
                "-c:v", "libx264",
                "-t", str(duration),
                "-pix_fmt", "yuv420p",
                "-vf", f"scale={self.WIDTH}:{self.HEIGHT}",
                str(out_path),
            ],
            check=True,
            capture_output=True,
        )
        card.unlink(missing_ok=True)
        return out_path

    def _render_card(self, idea: VideoIdea, path: Path) -> None:
        img = Image.new("RGB", (self.WIDTH, self.HEIGHT), color=(28, 32, 30))
        draw = ImageDraw.Draw(img)
        wrapped = "\n".join(textwrap.wrap(idea.topic, width=14)) or idea.topic
        # 기본 폰트(작음)라도 흐름 검증에는 충분합니다.
        draw.multiline_text(
            (self.WIDTH // 2, self.HEIGHT // 2),
            wrapped,
            fill=(240, 240, 235),
            anchor="mm",
            align="center",
            spacing=20,
        )
        img.save(path)


def get_provider(name: str | None = None) -> VideoProvider:
    """VIDEO_PROVIDER 환경변수(또는 인자)에 맞는 제공자를 반환합니다."""
    name = name or config.env("VIDEO_PROVIDER", "placeholder")
    if name == "placeholder":
        return PlaceholderProvider()
    # 예: if name == "runway": return RunwayProvider()
    raise ValueError(
        f"알 수 없는 VIDEO_PROVIDER: {name!r}. "
        "지원: placeholder. 실제 AI 영상 제공자를 추가하려면 VideoProvider 를 상속하세요."
    )


def generate_video(idea: VideoIdea) -> Path:
    """아이디어로 영상을 만들고 output/ 아래 파일 경로를 반환합니다."""
    out_dir = config.ensure_output_dir()
    out_path = out_dir / "today.mp4"
    return get_provider().generate(idea, out_path)
