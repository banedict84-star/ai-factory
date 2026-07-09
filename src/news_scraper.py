"""반월신문(banwol.net) 기사 스크래퍼.

반월신문 섹션 목록(articleList.html)에서 최근 기사의 제목·링크·날짜·요약을 뽑고,
필요하면 기사 본문(articleView.html)까지 가져옵니다.

이 CMS 는 국내 지역신문이 널리 쓰는 형식(`articleList.html?sc_section_code=...`,
`articleView.html?idxno=...`)이라, 스킨이 조금씩 달라도 견디도록
① `idxno` 링크 패턴으로 기사를 모으고 ② 본문은 표준 컨테이너(`#article-view-content-div`)를
우선 찾되 폴백을 여러 개 두는 방식으로 짰습니다.

주의: 반월신문 서버는 봇/비브라우저 요청을 403 으로 막습니다. 브라우저에 가까운
헤더를 붙이지만, 그래도 막히는 환경(예: 데이터센터 IP)에서는 실행되지 않을 수 있습니다.
반월신문이 정상 접속되는 네트워크(대표님 로컬 PC 등)에서 실행하세요.

단독 실행:
    python -m src.news_scraper --section S1N6 --limit 10 --with-body \
        --out output/banwol_S1N6.json
"""
from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urljoin

import requests

try:
    from bs4 import BeautifulSoup
except ImportError as exc:  # pragma: no cover - 안내용
    raise ImportError(
        "beautifulsoup4 가 필요합니다. `pip install -r requirements.txt` 로 설치하세요."
    ) from exc


BASE_URL = "https://www.banwol.net"
LIST_PATH = "/news/articleList.html"
VIEW_PATH = "/news/articleView.html"
DEFAULT_SECTION = "S1N6"
TIMEOUT = 20  # 초

# 브라우저에 가깝게 보이도록 하는 헤더 (봇 차단 완화용)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": BASE_URL + "/",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

_IDXNO_RE = re.compile(r"idxno=(\d+)")
# 2026.07.09 10:30 / 2026-07-09 / 2026.7.9 등
_DATE_RE = re.compile(r"\d{4}[.\-/]\s?\d{1,2}[.\-/]\s?\d{1,2}(?:\s+\d{1,2}:\d{2})?")


@dataclass
class NewsArticle:
    """기사 한 건."""

    idxno: str
    title: str
    url: str
    section: str = ""
    date: str = ""
    summary: str = ""
    body: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_session() -> requests.Session:
    """반월신문용 requests 세션 (브라우저 헤더 + 재시도)."""
    session = requests.Session()
    session.headers.update(_HEADERS)
    return session


def _get(session: requests.Session, url: str, *, params: dict | None = None,
         retries: int = 3) -> requests.Response:
    """네트워크 오류 시 지수 백오프로 재시도하는 GET."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = session.get(url, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            # 한글 깨짐 방지: 서버가 euc-kr 을 줄 때가 있어 실제 인코딩을 우선.
            if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
                resp.encoding = resp.apparent_encoding or "utf-8"
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    assert last_exc is not None
    raise last_exc


def _abs(href: str) -> str:
    """상대 링크를 절대 URL 로."""
    return urljoin(BASE_URL, href)


def _meta(soup: BeautifulSoup, prop: str) -> str:
    """<meta property=...> 또는 <meta name=...> 값."""
    tag = soup.find("meta", attrs={"property": prop}) or soup.find(
        "meta", attrs={"name": prop}
    )
    if tag and tag.get("content"):
        return tag["content"].strip()
    return ""


def fetch_list(
    section_code: str = DEFAULT_SECTION,
    *,
    page: int = 1,
    view_type: str = "sm",
    session: requests.Session | None = None,
) -> list[NewsArticle]:
    """섹션 목록 한 페이지에서 기사 스텁(본문 제외)을 뽑습니다."""
    session = session or make_session()
    resp = _get(
        session,
        _abs(LIST_PATH),
        params={
            "sc_section_code": section_code,
            "view_type": view_type,
            "page": page,
        },
    )
    return _parse_list(resp.text, section_code)


def _parse_list(html: str, section_code: str) -> list[NewsArticle]:
    """목록 HTML → NewsArticle 목록.

    스킨에 상관없이 `articleView.html?idxno=` 링크를 모두 모아 idxno 로 중복 제거하고,
    같은 기사에서 가장 긴 앵커 텍스트를 제목으로, 주변 컨테이너에서 날짜/요약을 뽑습니다.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: dict[str, NewsArticle] = {}
    order: list[str] = []
    # 제목이 heading/타이틀-클래스 앵커에서 확정됐는지 추적 (리드 문단 앵커에 덮이지 않게)
    authoritative: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = _IDXNO_RE.search(href)
        if not m or VIEW_PATH.split("/")[-1] not in href:
            continue
        idxno = m.group(1)
        if idxno not in items:
            items[idxno] = NewsArticle(
                idxno=idxno, title="", url=_abs(href), section=section_code
            )
            order.append(idxno)
        art = items[idxno]

        text = a.get_text(strip=True)
        if text:
            is_title = _is_title_anchor(a)
            if is_title:
                # 타이틀 앵커끼리는 더 긴 텍스트를 채택
                if idxno not in authoritative or len(text) > len(art.title):
                    art.title = text
                authoritative.add(idxno)
            elif idxno not in authoritative and not _inside_paragraph(a):
                # 확정 제목이 없고 리드(p) 밖의 앵커일 때만 폴백 제목으로
                if len(text) > len(art.title):
                    art.title = text

        container = a.find_parent(["li", "div", "article"])
        if container is not None:
            ctext = container.get_text(" ", strip=True)
            if not art.date:
                dm = _DATE_RE.search(ctext)
                if dm:
                    art.date = dm.group(0)
            if not art.summary:
                art.summary = _extract_summary(container, art.title)

    return [items[i] for i in order if items[i].title]


def _is_title_anchor(a: Any) -> bool:
    """이 앵커가 기사 '제목' 링크로 보이는지 (heading 안이거나 title 클래스)."""
    if a.find_parent(["h1", "h2", "h3", "h4", "h5", "h6"]) is not None:
        return True
    for el in [a, *a.find_parents(limit=3)]:
        cls = " ".join(el.get("class", []) or []).lower()
        if "title" in cls:
            return True
    return False


def _inside_paragraph(a: Any) -> bool:
    """앵커가 <p>(대개 리드/요약문) 안에 있는지."""
    return a.find_parent("p") is not None


def _extract_summary(container: Any, title: str) -> str:
    """목록 항목 컨테이너에서 리드/요약 문장을 best-effort 로 추출."""
    for sel in ("p.lead", ".lead", ".art_txt", ".cont", "p"):
        el = container.select_one(sel)
        if el:
            txt = el.get_text(" ", strip=True)
            if txt and txt != title and not _DATE_RE.fullmatch(txt):
                return txt
    return ""


def fetch_article(
    idxno_or_url: str,
    *,
    section_code: str = "",
    session: requests.Session | None = None,
) -> NewsArticle:
    """기사 한 건의 본문까지 가져옵니다. idxno(숫자) 또는 전체 URL 모두 허용."""
    session = session or make_session()

    if idxno_or_url.isdigit():
        url = _abs(VIEW_PATH)
        params = {"idxno": idxno_or_url}
        idxno = idxno_or_url
    else:
        url = idxno_or_url
        params = None
        m = _IDXNO_RE.search(idxno_or_url)
        idxno = m.group(1) if m else ""

    resp = _get(session, url, params=params)
    soup = BeautifulSoup(resp.text, "html.parser")

    title = _meta(soup, "og:title")
    if not title and soup.title:
        title = soup.title.get_text(strip=True)

    date = (
        _meta(soup, "article:published_time")
        or _meta(soup, "og:regDate")
        or _find_date(soup)
    )
    summary = _meta(soup, "og:description")
    body = _extract_body(soup)

    return NewsArticle(
        idxno=idxno,
        title=title,
        url=resp.url,
        section=section_code,
        date=date,
        summary=summary,
        body=body,
    )


def _find_date(soup: BeautifulSoup) -> str:
    """본문 페이지의 바이라인 영역에서 날짜 문자열을 찾습니다."""
    for sel in (".info", ".article-head-info", ".byline", ".view-editors"):
        el = soup.select_one(sel)
        if el:
            m = _DATE_RE.search(el.get_text(" ", strip=True))
            if m:
                return m.group(0)
    m = _DATE_RE.search(soup.get_text(" ", strip=True))
    return m.group(0) if m else ""


def _extract_body(soup: BeautifulSoup) -> str:
    """본문 컨테이너에서 텍스트만 정리해서 반환."""
    node = (
        soup.select_one("#article-view-content-div")
        or soup.select_one("#articleBody")
        or soup.select_one(".article-view-content")
        or soup.find(attrs={"itemprop": "articleBody"})
    )
    if node is None:
        return ""
    for junk in node.select("script, style, .ad, .adver, figure, .view-copyright"):
        junk.decompose()
    lines = [ln.strip() for ln in node.get_text("\n").splitlines()]
    return "\n".join(ln for ln in lines if ln)


def recent_articles(
    section_code: str = DEFAULT_SECTION,
    *,
    limit: int = 10,
    with_body: bool = False,
    delay: float = 0.5,
    session: requests.Session | None = None,
) -> list[NewsArticle]:
    """섹션 최근 기사 목록. with_body=True 면 각 기사 본문까지 채웁니다."""
    session = session or make_session()
    articles = fetch_list(section_code, session=session)[:limit]

    if with_body:
        for art in articles:
            try:
                full = fetch_article(
                    art.idxno or art.url, section_code=section_code, session=session
                )
            except requests.RequestException:
                continue
            # 목록에서 얻은 날짜/제목이 더 정확할 때가 있어 빈 값만 보강.
            art.body = full.body
            art.summary = art.summary or full.summary
            art.title = art.title or full.title
            art.date = art.date or full.date
            if delay:
                time.sleep(delay)

    return articles


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="반월신문 최근 기사 스크래퍼")
    parser.add_argument("--section", default=DEFAULT_SECTION, help="섹션 코드 (기본 S1N6)")
    parser.add_argument("--limit", type=int, default=10, help="가져올 기사 수 (기본 10)")
    parser.add_argument("--with-body", action="store_true", help="본문까지 가져오기")
    parser.add_argument("--out", default=None, help="결과를 저장할 JSON 파일 경로")
    args = parser.parse_args(argv)

    articles = recent_articles(
        args.section, limit=args.limit, with_body=args.with_body
    )
    payload = [a.to_dict() for a in articles]
    text = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.out:
        from pathlib import Path

        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"기사 {len(payload)}건 저장: {path}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
