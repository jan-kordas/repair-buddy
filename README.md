# Repair Buddy

AI diagnostic assistant for car mechanics. Supports Skoda Octavia I and VW Golf IV.

## Stack

- FastAPI + LangGraph + LangChain
- Qdrant (vector DB)
- Ollama (LLM, runs locally)

## Requirements

- Docker + Docker Compose
- Ollama running locally on port `11434`

## Setup

Pull the embedding model:

```bash
ollama pull qwen3-embedding:0.6b
```

Run the stack:

```bash
docker compose up --build
```

Ingest PDF manuals (required on first run):

```bash
uv run python scripts/ingest.py
```

API available at `http://localhost:8000`.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | app status |
| GET | `/health/qdrant` | Qdrant status |
| GET | `/health/ollama` | Ollama status |

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

### Data ingestion

Requires Tesseract for scanned PDFs:

```bash
brew install tesseract
```

Place PDF manuals in `data/raw/` and run:

```bash
uv run python scripts/ingest.py           # processes only new/unfinished PDFs
uv run python scripts/ingest.py --force   # reprocess everything
```

Progress is tracked in `data/processed/*.checkpoint.json`. The script is resumable - if interrupted, the next run continues from where it stopped. Point IDs in Qdrant are deterministic per `(source, page, chunk_index)`, so re-runs overwrite instead of duplicating.
