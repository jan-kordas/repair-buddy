# Repair Buddy

AI diagnostic assistant for car mechanics. Supports Skoda Octavia I and VW Golf IV.

## Stack

- FastAPI + LangGraph + LangChain
- Qdrant (vector DB)
- Postgres (app data, async SQLAlchemy + Alembic)
- Ollama (LLM, runs locally)

## Requirements

- Docker + Docker Compose
- Ollama running locally on port `11434`

## Setup

Pull the models:

```bash
ollama pull qwen3-embedding:0.6b   # for embeddings (ingestion + queries)
ollama pull qwen3:8b               # for chat answers
```

Run the stack:

```bash
docker compose up --build
```

Apply DB migrations:

```bash
cd backend
uv run alembic upgrade head
```

Ingest data into the vector DB (required on first run, and after adding new sources):

```bash
cd backend
uv run python scripts/ingest.py
```

This rebuilds the entire Qdrant collection from scratch each time — PDF manuals from `data/raw/` and forum threads from `elektroda_scraper/output/threads.jsonl`.

API available at `http://localhost:8000`. Adminer (DB browser) at `http://localhost:8080`.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | app status |
| GET | `/health/qdrant` | Qdrant status |
| GET | `/health/ollama` | Ollama status |
| GET | `/health/postgres` | Postgres status |
| POST | `/chat` | ask a question, get RAG answer with sources |

## Local development

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

Code style is enforced with ruff. After `uv sync` run:

```bash
uv run ruff check .
uv run ruff format .
```

### Database migrations

After changing models in `app/models/`, generate a new migration:

```bash
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
```

Rollback last migration:

```bash
uv run alembic downgrade -1
```

### Data ingestion

`scripts/ingest.py` rebuilds the full Qdrant collection from two sources:

| Source | Location | Format |
|--------|----------|--------|
| PDF repair manuals | `data/raw/*.pdf` | chunked by page (512 words, 50 overlap) |
| Elektroda forum threads | `elektroda_scraper/output/threads.jsonl` | posts chunked with thread title prefix |

Requires Tesseract for scanned PDFs:

```bash
brew install tesseract
```

To scrape forum threads, add URLs to `elektroda_scraper/urls.txt` and run:

```bash
cd elektroda_scraper
uv run python main.py urls.txt
```

Then rebuild the vector DB:

```bash
cd backend
uv run python scripts/ingest.py
```
