FROM ghcr.io/astral-sh/uv:0.11.30-python3.11-trixie-slim

ENV UV_NO_DEV=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GRADIO_SERVER_NAME=0.0.0.0 \
    GRADIO_SERVER_PORT=7861 \
    GRADIO_TEMP_DIR=/tmp/doc-inspector-gradio \
    GRADIO_ANALYTICS_ENABLED=False \
    PUBLIC_MAX_REQUESTS_PER_HOUR=60

WORKDIR /app

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY app.py ./

RUN uv sync --locked --no-dev --no-editable && \
    useradd --create-home --uid 10001 appuser && \
    chown -R appuser:appuser /app

ENV PATH="/app/.venv/bin:$PATH"

USER appuser
EXPOSE 7861
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7861/', timeout=4)"

CMD ["python", "app.py"]
