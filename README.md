# Repair Buddy

AI diagnostic assistant for car mechanics. Supports Skoda Octavia I and VW Golf IV.

## Stack

- FastAPI + LangGraph + LangChain
- Qdrant (vector DB)
- Ollama (LLM, runs locally)

## Requirements

- Docker + Docker Compose
- Ollama running locally on port `11434`

## Run

```bash
docker compose up --build
```

API available at `http://localhost:8000`

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
