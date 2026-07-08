"""네이버 OAuth 2.0 인증 — 카페 글쓰기 API 는 '로그인한 회원' 자격이 필요합니다.

카페 글쓰기는 앱 토큰이 아니라 **사용자(회원) 토큰**으로 동작합니다. 그래서
한 번은 네이버 로그인을 거쳐 access/refresh 토큰을 받아야 합니다.

권장 사용 흐름:
  1) 네이버 개발자센터(https://developers.naver.com)에서 애플리케이션 등록
     - 사용 API: '네이버 카페', Callback URL 등록 (예: http://localhost)
     - 클라이언트 ID/Secret 을 .env 에 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 로 저장
  2) `python -m src.cafe.main login` 실행 → 안내에 따라 로그인 → refresh_token 획득
  3) 받은 refresh_token 을 .env 의 NAVER_REFRESH_TOKEN 에 저장
  4) 이후 발행 시 자동으로 refresh_token → access_token 을 교환해 사용

간단히 단발성으로 쓰려면 NAVER_ACCESS_TOKEN 을 직접 넣어도 됩니다(만료 짧음).
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse

import requests

from .. import config

AUTHORIZE_URL = "https://nid.naver.com/oauth2.0/authorize"
TOKEN_URL = "https://nid.naver.com/oauth2.0/token"


def build_authorize_url(redirect_uri: str, state: str = "aifactory") -> str:
    """사용자가 브라우저로 열어 로그인할 인증 URL 을 만듭니다."""
    client_id = config.env("NAVER_CLIENT_ID", required=True)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_tokens(code: str, state: str = "aifactory") -> dict:
    """authorization code 를 access/refresh 토큰으로 교환합니다."""
    resp = requests.get(
        TOKEN_URL,
        params={
            "grant_type": "authorization_code",
            "client_id": config.env("NAVER_CLIENT_ID", required=True),
            "client_secret": config.env("NAVER_CLIENT_SECRET", required=True),
            "code": code,
            "state": state,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(
            f"토큰 교환 실패: {data.get('error')} - {data.get('error_description')}"
        )
    return data


def refresh_access_token(refresh_token: str) -> str:
    """refresh_token 으로 새 access_token 을 발급받습니다."""
    resp = requests.get(
        TOKEN_URL,
        params={
            "grant_type": "refresh_token",
            "client_id": config.env("NAVER_CLIENT_ID", required=True),
            "client_secret": config.env("NAVER_CLIENT_SECRET", required=True),
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data or "access_token" not in data:
        raise RuntimeError(
            f"access_token 갱신 실패: {data.get('error')} - {data.get('error_description')}"
        )
    return data["access_token"]


def get_access_token() -> str:
    """발행에 쓸 access_token 을 확보합니다.

    우선순위:
      1) NAVER_ACCESS_TOKEN 이 있으면 그대로 사용 (직접 넣은 단발성 토큰)
      2) NAVER_REFRESH_TOKEN 이 있으면 교환해서 access_token 발급
      3) 둘 다 없으면 안내와 함께 에러
    """
    access = config.env("NAVER_ACCESS_TOKEN")
    if access:
        return access

    refresh = config.env("NAVER_REFRESH_TOKEN")
    if refresh:
        return refresh_access_token(refresh)

    raise RuntimeError(
        "네이버 토큰이 없습니다. `python -m src.cafe.main login` 으로 로그인해 "
        "refresh_token 을 받아 .env 의 NAVER_REFRESH_TOKEN 에 넣으세요. "
        "(또는 단발성으로 NAVER_ACCESS_TOKEN 을 직접 지정)"
    )


def login_cli(redirect_uri: str | None = None) -> dict:
    """터미널에서 진행하는 로그인 흐름.

    로컬 서버 없이 동작합니다: 인증 URL 을 출력 → 사용자가 브라우저에서 로그인 →
    redirect_uri 로 리다이렉트된 '전체 주소'를 붙여넣으면 code 를 추출해 토큰 교환.
    """
    redirect_uri = redirect_uri or config.env(
        "NAVER_REDIRECT_URI", "http://localhost"
    )
    state = "aifactory"
    url = build_authorize_url(redirect_uri, state)

    print("─" * 60)
    print("1) 아래 URL 을 브라우저에서 열어 네이버로 로그인/동의하세요:\n")
    print(url)
    print(
        f"\n2) 로그인 후 '{redirect_uri}' 로 이동되며 주소창에 ?code=... 가 붙습니다."
    )
    print("3) 그 '전체 주소'를 그대로 아래에 붙여넣고 Enter:\n")
    pasted = input("리다이렉트된 전체 주소 (또는 code 값): ").strip()

    code = _extract_code(pasted)
    tokens = exchange_code_for_tokens(code, state)

    print("\n✅ 토큰 발급 완료. 아래 값을 .env 에 저장하세요:\n")
    if tokens.get("refresh_token"):
        print(f"NAVER_REFRESH_TOKEN={tokens['refresh_token']}")
    print(f"# (참고) access_token(만료됨): {tokens.get('access_token', '')[:12]}...")
    print("─" * 60)
    return tokens


def _extract_code(pasted: str) -> str:
    """붙여넣은 값에서 code 를 추출. 전체 URL 이면 쿼리에서, 아니면 그대로 code 로 간주."""
    if "code=" in pasted or pasted.startswith("http"):
        query = urlparse(pasted).query or pasted.split("?", 1)[-1]
        params = parse_qs(query)
        codes = params.get("code")
        if codes:
            return codes[0]
    return pasted
