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


def upload_image(data: bytes, object_path: str) -> str:
    """이미지를 GCS 에 올리고, 공개 접근 가능한 Firebase 다운로드 URL 을 반환합니다.

    firebasestorage.googleapis.com 은 구글 CDN 으로 빠르고 항상 켜져 있어, 네이버가
    이미지를 안정적으로 불러올 수 있다(우리 앱 프록시보다 유리).
    """
    import uuid
    from urllib.parse import quote as _q

    bucket_name = _bucket_name()
    blob = _bucket().blob(object_path)
    token = str(uuid.uuid4())
    blob.metadata = {"firebaseStorageDownloadTokens": token}
    blob.upload_from_string(data, content_type="image/png")
    return (
        f"https://firebasestorage.googleapis.com/v0/b/{bucket_name}"
        f"/o/{_q(object_path, safe='')}?alt=media&token={token}"
    )


def fetch_image(object_path: str) -> bytes:
    return _bucket().blob(object_path).download_as_bytes()


# ── 본문 삽입 ───────────────────────────────────────────────
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
]


def _korean_font(size: int):
    from PIL import ImageFont

    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_title_card(image_bytes: bytes, title: str, brand: str = "") -> bytes:
    """대표 이미지 위에 제목을 얹어 '타이틀 카드' PNG 를 만든다.

    폰트/렌더 실패 시 원본 이미지를 그대로 반환(발행이 깨지지 않게).
    """
    try:
        import io
        import textwrap

        from PIL import Image, ImageDraw

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        W, H = img.size
        draw = ImageDraw.Draw(img, "RGBA")
        # 하단에 반투명 그라데이션 박스(글자 가독성)
        band_h = int(H * 0.42)
        overlay = Image.new("RGBA", (W, band_h), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        for i in range(band_h):
            a = int(200 * (i / band_h))
            od.line([(0, i), (W, i)], fill=(0, 0, 0, a))
        img.paste(overlay, (0, H - band_h), overlay)

        # 제목 줄바꿈 + 렌더
        font = _korean_font(int(W * 0.062))
        wrapped = textwrap.wrap(title, width=16) or [title]
        wrapped = wrapped[:3]
        line_h = int(W * 0.075)
        y = H - int(W * 0.09) - line_h * len(wrapped)
        for line in wrapped:
            draw.text((int(W * 0.06), y), line, font=font, fill=(255, 255, 255, 255))
            y += line_h
        if brand:
            bf = _korean_font(int(W * 0.032))
            draw.text((int(W * 0.06), int(H * 0.05)), brand, font=bf,
                      fill=(255, 255, 255, 230))

        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()
    except Exception:
        return image_bytes


def _image_prompt(section_title: str, topic: str) -> str:
    return (
        "A clean, realistic photograph related to leather craft (가죽공예). "
        f"Scene: {section_title}. Overall topic: {topic}. "
        "Soft natural studio lighting, close-up, no text, no words, no letters."
    )


def _img_tag(url: str) -> str:
    return f'<p><img src="{url}" style="max-width:100%;border-radius:8px" alt=""></p>'


def add_hero_image(
    content: str, topic: str, draft_id: str, title: str = "", brand: str = ""
) -> str:
    """글 대표 '타이틀 카드' 1장을 만들어 본문 맨 앞에 삽입합니다.

    AI 이미지 위에 제목을 얹어 블로그 썸네일 같은 카드로 만든다. 발행 시 multipart 로
    첨부되며 네이버가 상단에 배치하므로 헤더로 적합.
    """
    data = generate_image_bytes(_image_prompt("대표 이미지", topic))
    if title:
        data = make_title_card(data, title, brand=brand)
    url = upload_image(data, f"{GCS_PREFIX}/{draft_id}/hero.png")
    # 이미 대표 이미지가 있으면(재생성) 기존 <img> 는 지우고 새로 넣는다
    import re

    content = re.sub(r"<p><img\b[^>]*></p>\s*", "", content, flags=re.IGNORECASE)
    return _img_tag(url) + "\n" + content


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
        url = upload_image(data, obj)
        return _img_tag(url) + "\n" + content

    urls: list[str] = []
    for i, title in enumerate(titles):
        clean = re.sub("<[^>]+>", "", title).strip()
        data = generate_image_bytes(_image_prompt(clean, topic))
        obj = f"{GCS_PREFIX}/{draft_id}/sec{i}.png"
        urls.append(upload_image(data, obj))

    counter = {"i": 0}

    def repl(m: re.Match) -> str:
        i = counter["i"]
        counter["i"] += 1
        return m.group(0) + "\n" + _img_tag(urls[i])

    return re.sub(r"</h3>", repl, content, flags=re.IGNORECASE)
