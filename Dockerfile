# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

# 1) 의존성 정의만 먼저 복사
COPY pyproject.toml uv.lock* /app/
RUN uv sync --no-dev

# 2) 가상환경 
ENV PATH="/app/.venv/bin:${PATH}"

# 3) 소스만 복사 (필요한 폴더만)
COPY app /app/app
COPY main.py /app/main.py
# 필요하면 추가로:
# COPY alembic /app/alembic
# COPY alembic.ini /app/alembic.ini

ENV HOST=0.0.0.0 PORT=8000
EXPOSE 8000
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]