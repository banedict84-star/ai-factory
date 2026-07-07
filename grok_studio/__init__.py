"""Grok Studio — 쇼핑몰 모델 영상 생성기.

그록(xAI Grok Imagine) API로:
  1) 업로드한 옷을 비전으로 분석하고
  2) 지정한 모델이 그 옷을 입은 사진을 만든 뒤
  3) 정해진 프롬프트대로 영상을 생성한다.
"""

__all__ = ["config", "models", "xai_client", "app"]
