FROM python:3.13-slim AS dependency-export
WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv
RUN uv export --frozen --no-dev --no-hashes --no-emit-project \
    --output-file /build/requirements.txt

FROM python:3.13-slim
WORKDIR /app
COPY --from=dependency-export /build/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --root-user-action=ignore \
    -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY src ./src
COPY evaluation ./evaluation
COPY supabase ./supabase

ENV PYTHONPATH=/app/src
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "knowledge_platform.bootstrap.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
