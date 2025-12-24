# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# uv 설치
RUN pip install --no-cache-dir uv

# 의존성 먼저 복사(캐시 최적화)
COPY pyproject.toml uv.lock* /app/

# 운영 이미지: dev 제외 설치
RUN uv sync --no-dev

# 소스 복사
COPY . /app

# API 기본 포트
ENV HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000

# 컨테이너 실행하면 곧바로 API 시작 (README/온보딩의 기본 실행 방식)
CMD ["uv", "run", "python", "main.py"]
