"""이미지 생성(OpenAI) + 저장(GCS/Firebase Storage) + 본문 소제목마다 삽입.

흐름: 본문의 각 <h3> 소제목마다 관련 이미지를 OpenAI 로 생성 → GCS 버킷에 저장 →
우리 앱의 /img/ 경로로 서빙되는 공개 URL 을 <img> 로 소제목 뒤에 삽입.

⚠️ 네이버 카페는 외부 이미지를 막을 수 있어, 실제 표시 여부는 발행해서 확인이 필요합니다.
"""
from __future__ import annotations

import base64
import re

from .. import config

IMAGE_MODEL_DEFAULT = "gpt-image-1"
GCS_PREFIX = "cafe-images"


def _bucket_name() -> str:
    b = config.env("CAFE_GCS_BUCKET")
    if not b:
        raise RuntimeError(
            "CAFE_GCS_BUCKET 환경변수가 없습니다. 파이어베이스 Storage 버킷 이름을 "
            "넣어주세요 (예: jjj2195-1bd15.firebasestorage.app 또는 xxx.appspot.com)."
        )
    return b


# ── 이미지 생성 ─────────────────────────────────────────────
def _gen(client, model: str, prompt: str) -> bytes:
    kwargs = {"model": model, "prompt": prompt, "size": "1024x1024", "n": 1}
    if model.startswith("dall-e"):
        kwargs["response_format"] = "b64_json"
    resp = client.images.generate(**kwargs)
    return base64.b64decode(resp.data[0].b64_json)


def generate_image_bytes(prompt: str) -> bytes:
    """OpenAI 로 이미지를 생성해 PNG 바이트로 반환. gpt-image-1 막히면 dall-e-3 폴백."""
    from openai import OpenAI

    client = OpenAI(api_key=config.env("OPENAI_API_KEY", required=True))
    model = config.env("CAFE_IMAGE_MODEL") or IMAGE_MODEL_DEFAULT
    try:
        return _gen(client, model, prompt)
    except Exception:
        if model != "dall-e-3":
            return _gen(client, "dall-e-3", prompt)
        raise


# ── GCS 저장/조회 ───────────────────────────────────────────
def _bucket():
    from google.cloud import storage

    return storage.Client().bucket(_bucket_name())


def upload_image(data: bytes, object_path: str) -> None:
    blob = _bucket().blob(object_path)
    blob.upload_from_string(data, content_type="image/png")


def fetch_image(object_path: str) -> bytes:
    return _bucket().blob(object_path).download_as_bytes()


# ── 본문 삽입 ───────────────────────────────────────────────
def _image_prompt(section_title: str, topic: str) -> str:
    return (
        "A clean, realistic photograph related to leather craft (가죽공예). "
        f"Scene: {section_title}. Overall topic: {topic}. "
        "Soft natural studio lighting, close-up, no text, no words, no letters."
    )


def _img_tag(url: str) -> str:
    return f'<p><img src="{url}" style="max-width:100%;border-radius:8px" alt=""></p>'


def add_section_images(
    content: str, topic: str, draft_id: str, public_base: str
) -> str:
    """각 <h3> 뒤에 관련 이미지를 생성·삽입한 새 본문을 반환합니다.

    소제목이 없으면 글 맨 앞에 대표 이미지 1장을 넣습니다.
    public_base 는 이 앱의 공개 주소(예: https://...run.app).
    """
    titles = re.findall(r"<h3[^>]*>(.*?)</h3>", content, flags=re.DOTALL | re.IGNORECASE)

    if not titles:
        data = generate_image_bytes(_image_prompt("대표 이미지", topic))
        obj = f"{GCS_PREFIX}/{draft_id}/top.png"
        upload_image(data, obj)
        url = f"{public_base}/img/{draft_id}/top.png"
        return _img_tag(url) + "\n" + content

    urls: list[str] = []
    for i, title in enumerate(titles):
        clean = re.sub("<[^>]+>", "", title).strip()
        data = generate_image_bytes(_image_prompt(clean, topic))
        obj = f"{GCS_PREFIX}/{draft_id}/sec{i}.png"
        upload_image(data, obj)
        urls.append(f"{public_base}/img/{draft_id}/sec{i}.png")

    counter = {"i": 0}

    def repl(m: re.Match) -> str:
        i = counter["i"]
        counter["i"] += 1
        return m.group(0) + "\n" + _img_tag(urls[i])

    return re.sub(r"</h3>", repl, content, flags=re.IGNORECASE)
