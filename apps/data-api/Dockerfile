FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /uvx /bin/
WORKDIR /workspace
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY apps/data-api ./apps/data-api
COPY apps/worker ./apps/worker
COPY packages ./packages

ENV PATH="/workspace/.venv/bin:$PATH"
ENV PYTHONPATH="/workspace:/workspace/apps/data-api/src:/workspace/apps/worker/src"
EXPOSE 8000
CMD ["uvicorn", "aeromaint_api.main:app", "--app-dir", "apps/data-api/src", "--host", "0.0.0.0", "--port", "8000"]
