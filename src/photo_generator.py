"""사진 생성 — 이미지 프롬프트로 실제 '모델 컷' PNG 를 만듭니다.

OMS 직원(executor)과 같은 방식으로 OpenAI 이미지 API 를 씁니다.
계정마다 접근 가능한 이미지 모델이 달라서, 설정 모델 → 대체 모델 순으로
'되는' 첫 모델을 사용합니다. 키/패키지가 없으면 플레이스홀더 그림으로 폴백합니다.
"""
from __future__ import annotations

import base64
import sys
import textwrap
from pathlib import Path

from . import config

DEFAULT_IMAGE_MODEL = "gpt-image-1"


def _client_or_none():
    try:
        from openai import OpenAI

        return OpenAI(api_key=config.env("OPENAI_API_KEY", required=True))
    except Exception as e:  # 키 없음/패키지 없음
        print(f"[photo] OpenAI 초기화 실패 → 플레이스홀더 사용: {e}", file=sys.stderr)
        return None


def _image_models() -> list[str]:
    configured = config.env("EXECUTOR_IMAGE_MODEL", DEFAULT_IMAGE_MODEL)
    # 순서 유지하며 중복 제거
    return list(dict.fromkeys([configured, "gpt-image-1", "dall-e-3", "dall-e-2"]))


def _gen_bytes(client, prompt: str) -> tuple[bytes, str]:
    last: Exception | None = None
    for m in _image_models():
        try:
            res = client.images.generate(model=m, prompt=prompt, size="1024x1024")
            d = res.data[0]
            b64 = getattr(d, "b64_json", None)
            if b64:
                return base64.b64decode(b64), m
            url = getattr(d, "url", None)
            if url:
                import urllib.request

                with urllib.request.urlopen(url, timeout=60) as r:
                    return r.read(), m
            raise RuntimeError("이미지 응답에 b64_json/url 이 없습니다")
        except Exception as e:  # 이 모델은 이 계정에서 막힘 → 다음 모델
            last = e
            print(f"[photo] 이미지 모델 '{m}' 실패: {e}", file=sys.stderr)
    raise last or RuntimeError("이미지 생성 실패")


def _placeholder(path: Path, title: str, subtitle: str) -> None:
    try:
        from PIL import Image, ImageDraw
    except Exception:
        # PIL 도 없으면 최소한의 빈 파일이라도 남긴다
        path.write_bytes(b"")
        return
    W, H = 1024, 1024
    img = Image.new("RGB", (W, H), (28, 32, 30))
    d = ImageDraw.Draw(img)
    d.multiline_text(
        (W // 2, H // 2 - 40),
        "\n".join(textwrap.wrap(title or "모델 컷", 12)),
        fill=(240, 240, 235), anchor="mm", align="center", spacing=14,
    )
    if subtitle:
        d.multiline_text(
            (W // 2, H // 2 + 120),
            "\n".join(textwrap.wrap(subtitle, 22)),
            fill=(150, 155, 150), anchor="mm", align="center", spacing=8,
        )
    d.text((W // 2, H - 70), "· placeholder ·", fill=(110, 115, 110), anchor="mm")
    img.save(path)


def generate_photo(image_prompt: str, name: str = "photo", title: str = "") -> Path:
    """이미지 프롬프트로 사진을 생성해 output/ 에 저장하고 경로를 반환합니다.

    OpenAI 로 실제 생성하며, 실패 시 플레이스홀더 그림으로 폴백합니다.
    """
    out_dir = config.ensure_output_dir()
    path = out_dir / f"{name}.png"

    client = _client_or_none()
    if client is not None:
        try:
            data, used = _gen_bytes(client, image_prompt)
            path.write_bytes(data)
            print(f"[photo] 이미지 생성 성공: {used} → {path}", file=sys.stderr)
            return path
        except Exception as e:
            print(f"[photo] 이미지 생성 실패 → 플레이스홀더로 대체: {e}", file=sys.stderr)

    _placeholder(path, title or image_prompt[:40], image_prompt[:60])
    return path
