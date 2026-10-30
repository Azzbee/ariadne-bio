FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ARIADNE_DATA_DIR=/app/data/processed

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 ariadne \
    && mkdir -p /app/data/processed /app/data/raw /app/reports \
    && chown -R ariadne:ariadne /app

COPY --chown=ariadne:ariadne app ./app
COPY --chown=ariadne:ariadne scripts ./scripts
COPY --chown=ariadne:ariadne infra/entrypoint.sh ./infra/entrypoint.sh
USER ariadne
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=10s --start-period=600s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=8)" || exit 1
ENTRYPOINT ["sh", "/app/infra/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
