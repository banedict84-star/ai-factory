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
        """제목/본문 문자열로 직접 발행. subject·content 는 URL 인코딩해서 전송합니다."""
        url = f"{API_BASE}/{self.club_id}/menu/{self.menu_id}/articles"
        # ⚠️ 네이버 카페 글쓰기 API 는 charset 을 명시하지 않으면 인코딩을 잘못 추측해
        # 한글이 깨진다(占쏙옙/� 현상). 검증 결과 euc-kr(cp949) URL 인코딩 + 헤더에
        # charset=euc-kr 을 함께 명시하면 정상. 만약 그래도 깨지면 env
        # CAFE_NAVER_CHARSET=utf-8 로 바꿔 재시도할 수 있게 했다.
        # euc-kr 로 표현 불가한 이모지 등은 HTML 엔티티(&#...;)로 대체해 그대로 렌더.
        charset = (config.env("CAFE_NAVER_CHARSET") or "euc-kr").lower()
        py_enc = "cp949" if charset in ("euc-kr", "euckr", "ms949", "cp949") else "utf-8"
        subj = quote(subject, encoding=py_enc, errors="xmlcharrefreplace")
        cont = quote(content, encoding=py_enc, errors="xmlcharrefreplace")
        body = (
            f"subject={subj}"
            f"&content={cont}"
            f"&openyn={'true' if open_to_public else 'false'}"
        )
        headers = self._auth_header()
        headers["Content-Type"] = f"application/x-www-form-urlencoded; charset={charset}"

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
