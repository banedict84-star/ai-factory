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
        """제목/본문 문자열로 직접 발행합니다.

        ⚠️ 한글 깨짐 해법(네이버 공식 명세): subject/content 는 'UTF-8 URL 인코딩 후
        MS949로 재 URL 인코딩'한 이중 인코딩 값으로 보내야 한다. 이미 %인코딩된 본문을
        보내므로 Content-Type 은 charset 없이 form-urlencoded 로 두고 ASCII 로 전송.
        """
        url = f"{API_BASE}/{self.club_id}/menu/{self.menu_id}/articles"
        body = (
            f"subject={_naver_encode(subject)}"
            f"&content={_naver_encode(content)}"
            f"&openyn={'true' if open_to_public else 'false'}"
        )
        headers = self._auth_header()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        resp = requests.post(url, headers=headers, data=body.encode("ascii"), timeout=60)
        if not resp.ok:
            # 네이버가 준 실제 사유(권한/제한/토큰 등)를 그대로 노출해 진단을 돕는다.
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
