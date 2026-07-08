# 가죽공예 카페 에이전트 대시보드 — Cloud Run / 컨테이너 배포용
#
# Cloud Run 은 $PORT(기본 8080)를 주입하고 0.0.0.0 바인딩을 요구합니다.
# src.cafe.web 의 main() 이 $PORT 를 읽어 0.0.0.0 으로 바인딩합니다.
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

# 의존성 먼저 설치 (레이어 캐시)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 소스
COPY . .

EXPOSE 8080

# 대시보드 실행 (PORT 가 있으므로 0.0.0.0:$PORT 로 바인딩)
CMD ["python", "-m", "src.cafe.web"]
