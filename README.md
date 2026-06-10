# Repair Buddy

Conversational diagnostic assistant for car mechanics. Currently covers Skoda Octavia I and VW Golf IV. Multi-turn chat with RAG over repair manuals and forum threads.

## Stack

- FastAPI + LangGraph + LangChain
- Qdrant for vectors
- Postgres for app data and parent chunks (async SQLAlchemy + Alembic)
- Ollama for local LLM, optional Groq for fast answer generation

## How it works

Each `/chat` request goes through a LangGraph pipeline:

1. NLU extracts the intent and slots (car make, model, system, symptoms) from the user message.
2. If the intent is `greeting` or `off_topic`, the graph returns a canned reply and skips RAG.
3. Otherwise the graph rewrites the question into a standalone form (resolves "it", "this", etc. from history), embeds it, and queries Qdrant filtered by the tracked slots.
4. The retrieved chunks plus recent conversation history go to the answer model.

Slots accumulate across turns in `conversations.slots`, so a follow-up like "ile to potrwa?" still filters retrieval to the right car.

## Requirements

- Docker + Docker Compose
- Ollama running locally on port `11434`

## Setup

Pull the local models:

```bash
ollama pull qwen3-embedding:0.6b   # embeddings
ollama pull gemma3:4b              # NLU + (optional) local answer generation
```

You can switch models via `OLLAMA_CHAT_MODEL`, `OLLAMA_NLU_MODEL`, `OLLAMA_EMBEDDING_MODEL` in `.env`.

For faster answers, set `GENERATE_PROVIDER=groq` and `GROQ_API_KEY=...` in `.env`. Groq has a free tier that covers normal usage.

Run the stack:

```bash
docker compose up --build
```

Apply DB migrations:

```bash
cd backend
uv run alembic upgrade head
```

Prepare and ingest the data:

```bash
cd backend
uv run python scripts/prepare_dataset.py   # OCR scanned PDFs into data/processed/
uv run python scripts/ingest.py            # chunk + embed PDFs and forum into Qdrant
```

`prepare_dataset.py` is idempotent: re-running only processes new files. `ingest.py` rebuilds both Qdrant collections; see [Data ingestion](#data-ingestion) for selective re-ingest.

API is at `http://localhost:8000`. Adminer (DB browser) at `http://localhost:8080`.

### Optional: LangSmith tracing

Set the `LANGSMITH_*` variables in `.env` (see `.env-example`) to see per-node traces at https://smith.langchain.com. Recreate the backend container after editing `.env`:

```bash
docker compose up -d backend --force-recreate
```

`docker compose restart` does not reload `.env`.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | app status |
| GET | `/health/qdrant` | Qdrant status |
| GET | `/health/ollama` | Ollama status |
| GET | `/health/postgres` | Postgres status |
| POST | `/chat` | ask a question; optional `conversation_id` for multi-turn |
| GET | `/conversations/{id}/messages` | message history for a conversation |

## Local development

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

Lint and format with ruff:

```bash
uv run ruff check .
uv run ruff format .
```

### Database migrations

After changing models in `app/models/`:

```bash
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
```

Rollback last migration:

```bash
uv run alembic downgrade -1
```

### Data ingestion

Two stages: prepare PDFs once, then ingest into Qdrant whenever the sources change.

**Stage 1 - `scripts/prepare_dataset.py`** reads `data/raw/` and writes `data/processed/`. PDFs with a text layer are copied as-is. Scanned PDFs go through `ocrmypdf` with the language inferred from the filename suffix (`_pl.pdf`, `_en.pdf`, `_fr.pdf`). Files already in `data/processed/` are skipped.

Requires:

```bash
brew install ocrmypdf tesseract-lang
```

**Stage 2 - `scripts/ingest.py`** chunks and embeds the data into Qdrant. Two collections:

| Collection | Source | Chunking |
|------------|--------|----------|
| `repair_manuals` | `data/processed/*.pdf` | tokenizer-aware macro/micro split (Qwen tokenizer); ~1200-token parents to Postgres `chunk_parents`, ~250-token children to Qdrant with `parent_id` |
| `forum_posts` | `elektroda_scraper/output/threads.jsonl` | posts chunked with thread title prefix, 512 words, 50 overlap |

By default both collections are rebuilt. To re-ingest only one:

```bash
uv run python scripts/ingest.py --only pdfs
uv run python scripts/ingest.py --only forum
```

To scrape more forum threads, add URLs to `elektroda_scraper/urls.txt`:

```bash
cd elektroda_scraper
uv run python main.py urls.txt
```
