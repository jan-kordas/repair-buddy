# Repair Buddy

Conversational AI diagnostic assistant for car mechanics. Supports Skoda Octavia I and VW Golf IV. Multi-turn dialogue with slot tracking and RAG over repair manuals + forum threads.

## Stack

- FastAPI + LangGraph + LangChain
- Qdrant (vector DB)
- Postgres (app data, async SQLAlchemy + Alembic)
- Ollama (LLM, runs locally)

## Dialog architecture

Task-oriented dialogue system with four canonical components:

- **NLU** — intent classification + slot extraction (`car_make`, `car_model`, `system`, `symptoms`) via structured output
- **DST** — slots persist in `conversations.slots` (JSON column) and accumulate across turns
- **DP** — conditional routing on intent: `greeting`/`off_topic` → canned response, `question`/`clarify` → full RAG pipeline
- **NLG** — history-aware generation with retrieved context, canned templates for non-domain intents

Graph topology:

```
START → nlu → [route by intent]
              ├─ direct_answer → END                       (canned, no LLM/RAG)
              └─ contextualize → retrieve → generate → END (full RAG)
```

`contextualize` rewrites follow-up questions into standalone form before embedding, so "ile to kosztuje?" in a Golf 4 conversation retrieves chunks about Golf 4 starter cost. Retrieval is filtered by `car_make`/`car_model` from tracked slots.

## Requirements

- Docker + Docker Compose
- Ollama running locally on port `11434`

## Setup

Pull the models (defaults from `.env-example`):

```bash
ollama pull qwen3-embedding:0.6b   # embeddings (ingestion + queries)
ollama pull gemma3:4b              # NLU slot extraction + answer generation
```

Model selection is configurable via `OLLAMA_CHAT_MODEL`, `OLLAMA_NLU_MODEL`, `OLLAMA_EMBEDDING_MODEL` in `.env`.

Run the stack:

```bash
docker compose up --build
```

Apply DB migrations:

```bash
cd backend
uv run alembic upgrade head
```

Prepare PDFs (OCRs scans, adds a text layer where missing) and ingest into the vector DB:

```bash
cd backend
uv run python scripts/prepare_dataset.py   # data/raw/ → data/processed/
uv run python scripts/ingest.py            # data/processed/ + forum → Qdrant
```

`prepare_dataset.py` is idempotent — re-running only processes new files in `data/raw/`. `ingest.py` rebuilds the Qdrant collections from scratch; see [Data ingestion](#data-ingestion) below for selective re-ingest.

API available at `http://localhost:8000`. Adminer (DB browser) at `http://localhost:8080`.

### Optional: LangSmith tracing

Add `LANGSMITH_*` variables to `.env` (see `.env-example`) to enable per-node tracing of the agent graph at https://smith.langchain.com. Each node (nlu, contextualize, retrieve, generate, direct_answer) reports input/output and latency. After changing `.env`, recreate the backend container so it picks up the new vars:

```bash
docker compose up -d backend --force-recreate
```

Note: `docker compose restart` does not reload `.env` — use `up --force-recreate` instead.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | app status |
| GET | `/health/qdrant` | Qdrant status |
| GET | `/health/ollama` | Ollama status |
| GET | `/health/postgres` | Postgres status |
| POST | `/chat` | ask a question (optional `conversation_id` for multi-turn); returns answer, sources, `conversation_id` |
| GET | `/conversations/{id}/messages` | chronological message history of a conversation |

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

Two-stage pipeline: **prepare** PDFs once, then **ingest** into Qdrant whenever sources change.

**Stage 1 — `scripts/prepare_dataset.py`** reads `data/raw/`, writes `data/processed/`:

- PDFs with an existing text layer are copied as-is.
- Scanned PDFs are OCR'd via `ocrmypdf`, with the language inferred from the filename suffix (`_pl.pdf` → `pol`, `_en.pdf` → `eng`, `_fr.pdf` → `fra`).
- Idempotent — files already in `data/processed/` are skipped.

Requires:

```bash
brew install ocrmypdf tesseract-lang
```

**Stage 2 — `scripts/ingest.py`** chunks and embeds the prepared data into Qdrant. Two collections, populated from two sources:

| Collection | Source | Format |
|------------|--------|--------|
| `repair_manuals` | `data/processed/*.pdf` | chunked by page (512 words, 50 overlap) |
| `forum_posts` | `elektroda_scraper/output/threads.jsonl` | posts chunked with thread title prefix |

By default `ingest.py` rebuilds both collections. To re-ingest only one source (the other collection is left untouched):

```bash
uv run python scripts/ingest.py --only pdfs    # re-embed PDFs only
uv run python scripts/ingest.py --only forum   # re-embed forum threads only
```

Use `--only pdfs` after running `prepare_dataset.py` on new manuals, and `--only forum` after scraping more threads — saves the time of re-embedding the other source.

To scrape additional forum threads, add URLs to `elektroda_scraper/urls.txt` and run:

```bash
cd elektroda_scraper
uv run python main.py urls.txt
```
