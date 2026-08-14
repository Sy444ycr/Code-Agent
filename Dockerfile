FROM node:22-bookworm AS web-build

WORKDIR /app
COPY web/package*.json web/
RUN cd web && npm ci
COPY web/ web/
RUN cd web && npm run build

FROM python:3.12-bookworm AS package-build

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/
COPY scripts/ scripts/
COPY --from=web-build /app/web/dist web/dist
RUN pip install --no-cache-dir build \
    && python scripts/prepare_web_package.py \
    && python -m build --wheel

FROM python:3.12-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CODE_AGENT_STATE_PATH=/var/lib/code-agent/state.db

WORKDIR /app
COPY --from=package-build /app/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl \
    && rm -f /tmp/*.whl \
    && useradd --create-home --home-dir /home/code-agent --shell /usr/sbin/nologin code-agent \
    && install --directory --owner=code-agent --group=code-agent /var/lib/code-agent

USER code-agent
EXPOSE 8000
CMD ["code-agent", "web", "--host", "0.0.0.0", "--port", "8000"]
