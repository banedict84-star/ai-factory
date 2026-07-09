"""네이버 카페 자동 발행 에이전트.

흐름: 초안 생성(AI) → 검수(대표 승인) → 발행(네이버 카페 OpenAPI).

  content_generator  Claude 로 제목+본문 초안 생성
  review             초안 저장/조회/승인 (검수 단계)
  publisher          네이버 카페 글쓰기 OpenAPI 호출
  auth               네이버 OAuth 토큰 (refresh → access)
  pipeline           위 단계를 묶은 실행 흐름
  main               CLI 진입점
"""
