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
        # 절반 높이의 가로 배너(2:1)로 크롭 — 카페에서 이미지가 너무 크지 않게
        W0, H0 = img.size
        target_h = W0 // 2
        if H0 > target_h:
            top = (H0 - target_h) // 2
            img = img.crop((0, top, W0, top + target_h))
        W, H = img.size
        draw = ImageDraw.Draw(img, "RGBA")
        # 하단에 반투명 그라데이션 박스(글자 가독성)
        band_h = int(H * 0.6)
        overlay = Image.new("RGBA", (W, band_h), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        for i in range(band_h):
            a = int(200 * (i / band_h))
            od.line([(0, i), (W, i)], fill=(0, 0, 0, a))
        img.paste(overlay, (0, H - band_h), overlay)

        # 제목 줄바꿈 + 렌더 (배너 높이에 맞춰 조금 작게)
        font = _korean_font(int(W * 0.05))
        wrapped = textwrap.wrap(title, width=20) or [title]
        wrapped = wrapped[:2]
        line_h = int(W * 0.062)
        y = H - int(W * 0.06) - line_h * len(wrapped)
        for line in wrapped:
            draw.text((int(W * 0.05), y), line, font=font, fill=(255, 255, 255, 255))
            y += line_h
        if brand:
            bf = _korean_font(int(W * 0.028))
            draw.text((int(W * 0.05), int(H * 0.08)), brand, font=bf,
                      fill=(255, 255, 255, 235))

        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()
    except Exception:
        return image_bytes


def _fetch_bytes(src: str) -> bytes:
    """이미지 src(우리 firebase/GCS URL 또는 일반 URL)에서 바이트를 가져온다."""
    import re
    from urllib.parse import unquote

    m = re.search(r"/o/([^?]+)", src)
    if "firebasestorage.googleapis.com" in src and m:
        return fetch_image(unquote(m.group(1)))
    import requests as _rq

    r = _rq.get(src, timeout=30)
    r.raise_for_status()
    return r.content


def _parse_blocks(html: str):
    """본문 HTML 을 순서대로 (종류, 값) 블록 목록으로 파싱한다.

    종류: heading / paragraph / list(문자열 리스트) / image(src)
    """
    from html.parser import HTMLParser

    class _P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.blocks = []
            self.mode = None
            self.buf = ""
            self.items = None

        def handle_starttag(self, tag, attrs):
            tag = tag.lower()
            if tag in ("h1", "h2", "h3", "h4"):
                self.mode, self.buf = "heading", ""
            elif tag == "p":
                self.mode, self.buf = "paragraph", ""
            elif tag in ("ul", "ol"):
                self.items = []
            elif tag == "li":
                self.buf = ""
            elif tag == "img":
                src = dict(attrs).get("src")
                if src:
                    self.blocks.append(("image", src))
            elif tag == "br":
                self.buf += "\n"

        def handle_endtag(self, tag):
            tag = tag.lower()
            if tag in ("h1", "h2", "h3", "h4") and self.mode == "heading":
                t = self.buf.strip()
                if t:
                    self.blocks.append(("heading", t))
                self.mode, self.buf = None, ""
            elif tag == "p" and self.mode == "paragraph":
                t = self.buf.strip()
                if t:
                    self.blocks.append(("paragraph", t))
                self.mode, self.buf = None, ""
            elif tag == "li" and self.items is not None:
                t = self.buf.strip()
                if t:
                    self.items.append(t)
                self.buf = ""
            elif tag in ("ul", "ol") and self.items is not None:
                if self.items:
                    self.blocks.append(("list", self.items))
                self.items = None

        def handle_data(self, data):
            self.buf += data

    p = _P()
    p.feed(html)
    return p.blocks


def _strip_emoji(text: str) -> str:
    """Nanum 폰트가 못 그리는 이모지를 제거(두부 □ 방지)."""
    import re

    return re.sub(
        "[\U0001f000-\U0001faff\U00002600-\U000027bf\U0000fe00-\U0000fe0f\U00002190-\U000021ff]",
        "",
        text,
    ).strip()


def _wrap(draw, text: str, font, max_w: int):
    """픽셀 폭 기준 줄바꿈(한글은 글자 단위, 공백 있으면 우선 활용)."""
    text = _strip_emoji(text)
    lines = []
    for para in text.split("\n"):
        cur = ""
        for ch in para:
            if draw.textlength(cur + ch, font=font) <= max_w:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)
    return lines or [""]


def render_detail_page(
    content_html: str, title: str, brand: str = "", width: int = 880
) -> bytes:
    """본문(텍스트+이미지)을 하나의 긴 '상세페이지' PNG 로 렌더링한다(Pillow)."""
    import io

    from PIL import Image, ImageDraw

    pad = 48
    cw = width - pad * 2
    ACCENT = (138, 90, 43)
    TEXT = (55, 50, 45)
    canvas = Image.new("RGB", (width, 30000), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    f_title = _korean_font(46)
    f_h = _korean_font(33)
    f_p = _korean_font(25)
    f_brand = _korean_font(20)

    y = pad
    if brand:
        draw.text((pad, y), brand, font=f_brand, fill=ACCENT)
        y += 36
    for line in _wrap(draw, title, f_title, cw):
        draw.text((pad, y), line, font=f_title, fill=(35, 28, 22))
        y += 60
    y += 8
    draw.rectangle([pad, y, pad + 64, y + 6], fill=ACCENT)
    y += 34

    for kind, payload in _parse_blocks(content_html):
        if kind == "heading":
            y += 30
            for line in _wrap(draw, payload, f_h, cw):
                draw.text((pad, y), line, font=f_h, fill=ACCENT)
                y += 46
            y += 6
        elif kind == "paragraph":
            for line in _wrap(draw, payload, f_p, cw):
                draw.text((pad, y), line, font=f_p, fill=TEXT)
                y += 40
            y += 18
        elif kind == "list":
            for item in payload:
                lines = _wrap(draw, item, f_p, cw - 34)
                for i, line in enumerate(lines):
                    prefix = "•  " if i == 0 else "     "
                    draw.text((pad + 8, y), prefix + line, font=f_p, fill=TEXT)
                    y += 40
            y += 18
        elif kind == "image":
            try:
                im = Image.open(io.BytesIO(_fetch_bytes(payload))).convert("RGB")
                nh = int(im.height * (cw / im.width))
                im = im.resize((cw, nh))
                y += 10
                canvas.paste(im, (pad, y))
                y += nh + 24
            except Exception:
                continue

    y += pad
    out = canvas.crop((0, 0, width, min(y, 30000)))
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


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
