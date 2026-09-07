FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY . /app
RUN uv pip install --system -e .

ENV PYTHONUNBUFFERED=1
ENV WIKI_PATH=/data/wiki
ENV HOST=0.0.0.0
ENV PORT=8000
ENV REMOTE_MODE=true

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "wiki_mcp.cli"]
