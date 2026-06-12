# Repair Buddy

Conversational diagnostic assistant for car mechanics. Currently covers Skoda Octavia I and VW Golf IV. Multi-turn chat with RAG over repair manuals and forum threads.

## Stack

- FastAPI + LangGraph + LangChain
- Qdrant for vectors
- Postgres for app data and parent chunks (async SQLAlchemy + Alembic)
- Cross-encoder reranker (BGE-reranker-v2-m3) over retrieved candidates — in-process, via a native llama.cpp server, or disabled (see [Reranker modes](#reranker-modes))
- Ollama for local LLM and embeddings; optional Groq or OpenAI for answer generation

## How it works

Each `/chat` request goes through a LangGraph pipeline:

1. NLU extracts the intent and slots (car make, model, system, symptoms) from the user message.
2. If the intent is `greeting` or `off_topic`, the graph returns a canned reply and skips RAG.
3. Otherwise the graph rewrites the question into a standalone form (resolves "it", "this", etc. from history), embeds it, and queries both Qdrant collections for matching micro chunks filtered by the tracked slots.
4. A cross-encoder reranks the candidates against the query (see [Reranker modes](#reranker-modes)); chunks below the relevance threshold are dropped and the rest deduplicated by parent. The surviving macro parent chunks are fetched from Postgres.
5. The retrieved parent chunks (broader context than what was matched) plus recent conversation history go to the answer model. If nothing clears the threshold, the model is told the knowledge base has no match rather than answering from general knowledge.

Slots accumulate across turns in `conversations.slots`, so a follow-up like "how long will it take?" still filters retrieval to the right car.

## Requirements

- Docker + Docker Compose
- Ollama running locally on port `11434`
- Optional: llama.cpp running locally on port `8081` for fast reranking (see [Reranker modes](#reranker-modes))

## Setup

Pull the local models:

```bash
ollama pull qwen3-embedding:0.6b   # embeddings
ollama pull gemma3:4b              # NLU + (optional) local answer generation
```

You can switch models via `OLLAMA_CHAT_MODEL`, `OLLAMA_NLU_MODEL`, `OLLAMA_EMBEDDING_MODEL` in `.env`.

For faster answers, set `GENERATE_PROVIDER=groq` (or `openai`) and the matching API key in `.env`. Groq has a free tier that covers normal usage.

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

Frontend is at `http://localhost:3000`, API at `http://localhost:8000`, Adminer (DB browser) at `http://localhost:8080`.

### Reranker modes

Retrieved candidates are reranked by `BAAI/bge-reranker-v2-m3` (a multilingual cross-encoder that handles Polish well). `RERANKER_MODE` in `.env` selects how it runs:

| Mode | What runs | Speed | Notes |
|------|-----------|-------|-------|
| `llamacpp` | native `llama-server` on the host (Metal GPU) | ~1-2 s for 24 candidates | recommended on Apple Silicon; falls back to vector order (no scores) if the server is unreachable |
| `local` | CrossEncoder inside the backend container (CPU) | ~1 s per candidate | no extra services, but Docker on macOS has no GPU access; adds ~1 GB RAM to the container |
| `off` | nothing | instant | chunks keep Qdrant vector-score order; `RELEVANCE_THRESHOLD` is not applied |

For `llamacpp` mode, install and start the server (first run downloads the ~600 MB GGUF):

```bash
brew install llama.cpp
llama-server -hf gpustack/bge-reranker-v2-m3-GGUF:Q8_0 --rerank --port 8081
```

llama.cpp returns raw logits; the backend sigmoid-normalizes them to `[0,1]` so `RELEVANCE_THRESHOLD` means the same in both `llamacpp` and `local` modes.

Tuning knobs in `.env`:

- `RETRIEVAL_TOP_K` — candidates fetched per Qdrant query before reranking (in `local` mode this directly sets latency: ~1 s per candidate on CPU)
- `RERANKER_TOP_K` — chunks passed to the answer model after reranking
- `RELEVANCE_THRESHOLD` — chunks scoring below this are dropped before generation

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
| `forum_posts` | `elektroda_scraper/output/threads.jsonl` | parent per thread (AI summary or title) to Postgres `chunk_parents`; one micro per AI summary plus one per cleaned post to Qdrant with `parent_id` |

By default both collections are rebuilt. To re-ingest only one:

```bash
uv run python scripts/ingest.py --only pdfs
uv run python scripts/ingest.py --only forum
```

To scrape more forum threads, discover thread URLs (searches elektroda for the configured topics, appending to `urls.txt`) then scrape their content: (very likely to be excluded by elektroda antibot mechanisms)

```bash
cd elektroda_scraper
uv run python gather_urls.py        # discover + append URLs to urls.txt
uv run python main.py urls.txt      # scrape thread content to output/threads.jsonl
```
