# 고정 모델 프로필 이미지

여기에 `seoa.png`, `jimin.png`, `haneul.png` 를 넣으면
카드 프로필을 **그록으로 매번 생성하지 않고 이 고정 이미지**를 씁니다.

- 파일명 = 모델 id (`grok_studio/models.py` 의 `MODELS` 참고)
  - `seoa.png` · `jimin.png` · `haneul.png`
  - png / jpg / jpeg / webp 지원
- 파일이 있으면 → 이 이미지 사용 (재생성 0원, 얼굴 항상 동일)
- 파일이 없으면 → 그록으로 자동 생성 (기존 동작)

`.gitignore` 에서 이 폴더의 이미지는 커밋되도록 예외 처리돼 있습니다.
