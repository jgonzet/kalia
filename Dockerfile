FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/srv/.venv/bin:$PATH" \
    LLM_BASE_URL=http://host.docker.internal:11434 \
    SAMPLE_COMPANY=lamanija

WORKDIR /srv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY scripts/operate/check_llm.py ./scripts/operate/check_llm.py

# Only what loading the sample company needs: no story, question banks or org chart.
COPY data/lamanija/company.json data/lamanija/people.jsonl data/lamanija/projects.jsonl ./data/lamanija/
COPY data/lamanija/documents ./data/lamanija/documents
COPY data/lamanija/expected ./data/lamanija/expected

# Writable directory for the SQLite file. Nothing mounts it: the data lives as long as the container does.
RUN useradd --create-home app && mkdir /var/lib/kalia && chown app /var/lib/kalia
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
