"""네이버 카페 게시 — 카페 글쓰기 OpenAPI 로 글을 발행합니다.

전제: 네이버 개발자센터 앱 등록 + '네이버 카페' API 사용 설정 + 회원(로그인) 토큰.
토큰은 auth.get_access_token() 이 refresh_token 으로부터 확보합니다.

주의: 이 API 는 **본인이 회원이고 글쓰기 권한이 있는 카페/게시판**에만 글을 쓸 수 있습니다.
"""
from __future__ import annotations

from urllib.parse import quote

import requests

from .. import config
from . import auth
from .models import CafePost

API_BASE = "https://openapi.naver.com/v1/cafe"


def _fetch_image_bytes(src: str) -> bytes:
    """본문 <img> 의 src 에서 이미지 바이트를 가져온다.

    우리 firebase/GCS 이미지면 GCS 에서 직접 읽고, 그 외에는 HTTP GET.
    """
    import re
    from urllib.parse import unquote

    m = re.search(r"/o/([^?]+)", src)
    if "firebasestorage.googleapis.com" in src and m:
        from . import images

        return images.fetch_image(unquote(m.group(1)))
    r = requests.get(src, timeout=30)
    r.raise_for_status()
    return r.content


def _collect_images(content: str, limit: int = 10) -> list[tuple[str, bytes]]:
    """본문의 <img src="..."> 들을 (파일명, 바이트) 목록으로 수집한다(최대 limit장)."""
    import re

    srcs = re.findall(r'<img\b[^>]*\bsrc=["\']([^"\']+)["\']', content, flags=re.IGNORECASE)
    out: list[tuple[str, bytes]] = []
    for i, src in enumerate(srcs[:limit]):
        try:
            out.append((f"image{i}.png", _fetch_image_bytes(src)))
        except Exception:
            continue  # 못 가져온 이미지는 건너뛴다
    return out


def _prettify_for_cafe(html: str, keep_images: bool = False) -> str:
    """네이버 카페는 블록 요소(<p>,<h3>) 간 여백이 거의 없어 문단이 붙어 보인다.
    문단/목록 끝과 소제목 앞에 빈 줄(<br>)을 넣어 가독성 있게 다듬는다.

    keep_images=False 면 외부 <img> 를 제거한다(네이버가 거부/999 방지). 인라인 이미지를
    테스트할 때만 keep_images=True 로 남긴다.
    """
    import re

    if not keep_images:
        # 외부 <img> 가 든 글을 네이버가 거부(999)할 수 있어 안전하게 제거한다.
        html = re.sub(r"<img\b[^>]*>", "", html, flags=re.IGNORECASE)
        html = re.sub(r"<p>\s*</p>", "", html, flags=re.IGNORECASE)

    # 문단/목록 끝에 빈 줄 (소제목 뒤에는 넣지 않아 제목이 본문에 붙게)
    html = re.sub(r"</(p|ul|ol)>", r"</\1><br>", html, flags=re.IGNORECASE)
    # 소제목(h1~h4) 앞에 빈 줄 → 섹션 구분
    html = re.sub(r"\s*<(h[1-4])(\b|>)", r"<br><\1\2", html, flags=re.IGNORECASE)
    # 맨 앞에 생긴 <br> 는 제거
    html = re.sub(r"^\s*(<br>\s*)+", "", html.strip(), flags=re.IGNORECASE)
    return html


def _naver_encode(s: str) -> str:
    """네이버 카페 API 명세대로 이중 URL 인코딩: UTF-8 인코딩 후 MS949로 재인코딩.

    (공식 예: URLEncoder.encode(URLEncoder.encode(s, "UTF-8"), "MS949"))
    1차에서 한글→UTF-8 %인코딩, 2차에서 그 결과(ASCII)의 % 등을 다시 %인코딩한다.
    """
    return quote(quote(s, safe="", encoding="utf-8"), safe="", encoding="cp949")


class NaverCafePublisher:
    def __init__(
        self,
        club_id: str | None = None,
        menu_id: str | None = None,
        access_token: str | None = None,
    ):
        self.access_token = access_token or auth.get_access_token()
        self.club_id = str(club_id or self._resolve_club_id())
        self.menu_id = str(menu_id or config.env("NAVER_CAFE_MENU_ID", required=True))

    # ── clubid 확보 ─────────────────────────────────────────────
    def _resolve_club_id(self) -> str:
        """env 의 NAVER_CAFE_CLUB_ID 우선, 없으면 카페 URL 이름으로 조회."""
        club_id = config.env("NAVER_CAFE_CLUB_ID")
        if club_id:
            return club_id
        url_name = config.env("NAVER_CAFE_URL_NAME")
        if url_name:
            return self.lookup_club_id(url_name)
        raise RuntimeError(
            "카페 ID 를 알 수 없습니다. NAVER_CAFE_CLUB_ID(숫자) 또는 "
            "NAVER_CAFE_URL_NAME(cafe.naver.com/뒤 이름) 중 하나를 .env 에 설정하세요."
        )

    def lookup_club_id(self, cafe_url_name: str) -> str:
        """카페 URL 이름(cafe.naver.com/<이름>)으로 숫자 clubid 를 조회합니다."""
        resp = requests.get(
            f"{API_BASE}/{cafe_url_name}/clubid",
            headers=self._auth_header(),
            timeout=30,
        )
        resp.raise_for_status()
        # 응답은 XML 또는 JSON 일 수 있어 message.result.cafeId 를 관대하게 파싱
        data = _parse_clubid(resp.text)
        if not data:
            raise RuntimeError(
                f"'{cafe_url_name}' 의 clubid 조회 실패. 응답: {resp.text[:200]}"
            )
        return data

    # ── 글쓰기 ─────────────────────────────────────────────────
    def publish(self, post: CafePost, open_to_public: bool = True) -> dict:
        """게시글을 발행하고 {articleId, articleUrl} 를 반환합니다."""
        return self.publish_raw(post.subject, post.content, open_to_public)

    def publish_raw(
        self, subject: str, content: str, open_to_public: bool = True
    ) -> dict:
        """제목/본문 문자열로 발행합니다. 본문에 이미지가 있으면 multipart 로 첨부합니다.

        - 이미지 없음: form-urlencoded + 이중 인코딩(UTF-8→MS949). (네이버 명세)
        - 이미지 있음: 본문의 <img> 를 파일로 추출해 multipart image[] 로 첨부하고,
          본문은 텍스트만(단일 UTF-8 인코딩) 보낸다. 이미지는 글 하단에 붙는다
          (네이버 API 는 본문 중간 삽입을 지원하지 않음).
        """
        url = f"{API_BASE}/{self.club_id}/menu/{self.menu_id}/articles"
        image_files = _collect_images(content)  # [(filename, bytes), ...]
        text = _prettify_for_cafe(content, keep_images=False)  # <img> 제거 + 간격
        openyn = "true" if open_to_public else "false"
        headers = self._auth_header()

        if image_files:
            # multipart: subject/content 는 단일 URL 인코딩(UTF-8), 이미지는 파일 첨부
            data = {
                "subject": quote(subject, encoding="utf-8"),
                "content": quote(text, encoding="utf-8"),
                "openyn": openyn,
            }
            files = [
                ("image", (name, blob, "image/png")) for name, blob in image_files
            ]
            resp = requests.post(url, headers=headers, data=data, files=files, timeout=120)
        else:
            # form-urlencoded: 이중 인코딩(공식 명세)
            body = (
                f"subject={_naver_encode(subject)}"
                f"&content={_naver_encode(text)}"
                f"&openyn={openyn}"
            )
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            resp = requests.post(url, headers=headers, data=body.encode("ascii"), timeout=60)

        if not resp.ok:
            raise RuntimeError(
                f"네이버 카페 발행 실패 (HTTP {resp.status_code}). 네이버 응답: "
                f"{resp.text[:600] or '(본문 없음)'}"
            )
        return _parse_article_result(resp.text)

    # ── 내부 ───────────────────────────────────────────────────
    def _auth_header(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


def _parse_clubid(text: str) -> str | None:
    """clubid 응답에서 카페 숫자 ID 를 추출 (JSON/XML 모두 관대하게)."""
    import json
    import re

    try:
        data = json.loads(text)
        result = data.get("message", {}).get("result", {})
        cid = result.get("cafeId") or result.get("clubid") or result.get("cafeid")
        if cid:
            return str(cid)
    except (ValueError, AttributeError):
        pass
    m = re.search(r"<cafeid>\s*(\d+)\s*</cafeid>", text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r'"cafeId"\s*:\s*"?(\d+)"?', text)
    if m:
        return m.group(1)
    return None


def _parse_article_result(text: str) -> dict:
    """글쓰기 응답에서 articleId / articleUrl 을 추출 (JSON/XML 모두 관대하게)."""
    import json
    import re

    result: dict = {"raw": text}
    try:
        data = json.loads(text)
        node = data.get("message", {}).get("result", data)
        result["articleId"] = node.get("articleId") or node.get("refarticleid")
        result["articleUrl"] = node.get("articleUrl") or node.get("url")
        return result
    except (ValueError, AttributeError):
        pass
    m = re.search(r"<articleId>\s*(\d+)\s*</articleId>", text, re.IGNORECASE)
    if m:
        result["articleId"] = m.group(1)
    m = re.search(r"<articleUrl>\s*(.*?)\s*</articleUrl>", text, re.IGNORECASE)
    if m:
        result["articleUrl"] = m.group(1)
    return result
