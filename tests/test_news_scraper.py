"""news_scraper 파서 검증 — 네트워크 없이 합성 HTML로.

pytest 없이도 실행됩니다:  python -m tests.test_news_scraper
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from src import news_scraper as ns

LIST_HTML = """
<html><body>
<section id="section-list">
  <ul class="type2">
    <li>
      <a href="/news/articleView.html?idxno=100123"><img src="/img/a.jpg"></a>
      <div class="view-cont">
        <h4 class="titles"><a href="/news/articleView.html?idxno=100123">안산 반월공단 소식 하나</a></h4>
        <p class="lead"><a href="/news/articleView.html?idxno=100123">리드 요약문입니다 첫번째 문장.</a></p>
        <span class="byline"><em>홍길동 기자</em> <em>2026.07.09 10:30</em></span>
      </div>
    </li>
    <li>
      <a href="/news/articleView.html?idxno=100124"><img src="/img/b.jpg"></a>
      <div class="view-cont">
        <h4 class="titles"><a href="/news/articleView.html?idxno=100124">두번째 기사 제목</a></h4>
        <p class="lead">두번째 리드 요약.</p>
        <span class="byline"><em>김철수 기자</em> <em>2026.07.08 15:05</em></span>
      </div>
    </li>
  </ul>
</section>
</body></html>
"""

ARTICLE_HTML = """
<html><head>
<meta property="og:title" content="안산 반월공단 소식 하나">
<meta property="og:description" content="본문 요약 설명">
<meta property="article:published_time" content="2026-07-09T10:30:00+09:00">
</head><body>
<div class="info">홍길동 기자 | 승인 2026.07.09 10:30</div>
<div id="article-view-content-div" itemprop="articleBody">
  <p>첫 문단 본문입니다.</p>
  <script>var x=1;</script>
  <p>둘째 문단 본문입니다.</p>
  <figure>사진 캡션 무시</figure>
</div>
</body></html>
"""


def test_parse_list() -> None:
    arts = ns._parse_list(LIST_HTML, "S1N6")
    assert len(arts) == 2, f"기대 2건, 실제 {len(arts)}건"
    a = arts[0]
    assert a.idxno == "100123", a.idxno
    assert a.title == "안산 반월공단 소식 하나", a.title  # 리드 앵커에 덮이면 안 됨
    assert a.url == "https://www.banwol.net/news/articleView.html?idxno=100123", a.url
    assert a.date == "2026.07.09 10:30", a.date
    assert a.summary == "리드 요약문입니다 첫번째 문장.", a.summary
    assert a.section == "S1N6"


def test_parse_article() -> None:
    soup = BeautifulSoup(ARTICLE_HTML, "html.parser")
    assert ns._meta(soup, "og:title") == "안산 반월공단 소식 하나"
    assert ns._meta(soup, "article:published_time").startswith("2026-07-09")
    body = ns._extract_body(soup)
    assert "첫 문단 본문입니다." in body
    assert "둘째 문단 본문입니다." in body
    assert "var x=1" not in body, "script 가 제거되지 않음"
    assert "사진 캡션" not in body, "figure 가 제거되지 않음"


def test_recent_articles_with_mock() -> None:
    """recent_articles → to_dict 전체 경로 (응답 목킹)."""

    class FakeResp:
        def __init__(self, text: str, url: str) -> None:
            self.text, self.url, self.encoding = text, url, "utf-8"

        def raise_for_status(self) -> None:
            pass

    def fake_get(session, url, params=None, retries=3):  # noqa: ANN001
        if "articleList" in url:
            return FakeResp(LIST_HTML, url)
        idxno = (params or {}).get("idxno", "")
        return FakeResp(ARTICLE_HTML, f"{url}?idxno={idxno}")

    original = ns._get
    try:
        ns._get = fake_get  # type: ignore[assignment]
        arts = ns.recent_articles("S1N6", limit=10, with_body=True, delay=0)
    finally:
        ns._get = original  # type: ignore[assignment]

    assert len(arts) == 2
    assert arts[0].body.startswith("첫 문단")
    assert all(a.to_dict()["idxno"] for a in arts)


def _run_all() -> None:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✓ {name}")
    print("\n전부 통과 ✅")


if __name__ == "__main__":
    _run_all()
