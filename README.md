# TranscriptFlow

Resilient AI data pipeline for turning raw transcripts into searchable, summarized, vectorized knowledge.

TranscriptFlow converts YouTube/SRT subtitle files into semantic chunks, LLM-generated summaries and tags, batched embeddings, and LanceDB vector indexes. It is designed for long transcripts and batch jobs where observability, retries, and recoverability matter.

## Engineering Highlights

TranscriptFlow is built to demonstrate production-oriented AI pipeline design rather than a single prompt wrapper:

- recoverable multi-phase processing with explicit file states
- chunk-level retries that preserve successful work
- model-level diagnostics for throughput, latency, failures, and error distribution
- atomic checkpoint writes for long-running summarization jobs
- adaptive embedding batching with circuit-breaker protection
- audit tooling for data integrity, stale jobs, and cross-file consistency

## Why It Exists

Most transcript tools stop at "summarize this file." TranscriptFlow treats transcripts as a data pipeline problem:

- preserve semantic boundaries instead of splitting by fixed length
- process many files through a recoverable state machine
- retry failed chunks without throwing away successful work
- track model errors, elapsed time, progress, and batch health
- produce RAG-ready records for semantic search and agent memory

## Key Features

- **Smart Merge 3.0 semantic chunking**: overlapping subtitle windows, embedding cosine similarity, percentile breakpoints, minimum-span validation, and noise filtering.
- **Four-phase pipeline**: chunking, summarization, embedding, and LanceDB insertion.
- **11-state workflow**: explicit file states from `undone` through `done`, including retryable and permanent failure states.
- **Watchdog automation**: scans batch status files, advances eligible work, resets timed-out jobs, and manages phase concurrency.
- **Chunk-level retry**: failed chunks can be retried independently across models.
- **Model diagnostics**: records success/failure counts, elapsed time, throughput, and common error patterns.
- **Batch audit tooling**: checks structure, timeliness, data integrity, error visibility, model performance, and cross-file consistency.
- **OpenAI-compatible API support**: works with OpenAI, LiteLLM Proxy, OpenRouter, vLLM, Ollama-compatible servers, or any service exposing compatible `/v1/chat/completions` and `/v1/embeddings` endpoints.

## Architecture

```text
SRT files + master manifest
        |
        v
batch_status_*.json
        |
        v
auto_watchdog.py
        |
        +--> summarize.py --phase chunking
        |       parse_srt.py -> semantic_chunk.py
        |
        +--> summarize.py --phase summarizing
        |       summarize_pipeline.py
        |
        +--> summarize.py --phase embedding
        |       batch_embedding.py
        |
        +--> summarize.py --phase db_inserting
                finalize.py -> LanceDB
```

## Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/TranscriptFlow.git
cd TranscriptFlow

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
cp scripts/config.example.json scripts/config.json
```

Edit `.env` and `scripts/config.json` for your API endpoint, model names, output directory, and LanceDB path.

```bash
export $(grep -v '^#' .env | xargs)

python3 scripts/state_manager.py init_batch 0 0
python3 scripts/auto_watchdog.py
```

## Configuration

TranscriptFlow reads settings in this order:

1. Environment variables
2. `scripts/config.json`
3. `scripts/config.example.json`

Important environment variables:

```bash
OPENAI_BASE_URL=https://api.openai.com
OPENAI_API_KEY=replace-with-your-key
SUMMARIZATION_MODELS='["gpt-4.1-mini"]'
EMBEDDING_MODEL=text-embedding-3-large
EMBEDDING_EXPECTED_DIM=3072
SRT_OUTPUT_DIR=./output
SRT_DB_PATH=./lancedb
SRT_MASTER_FILE=./examples/master_file_manifest.example.json
```

LiteLLM remains supported because it exposes the same OpenAI-compatible interface:

```bash
OPENAI_BASE_URL=http://localhost:4000
OPENAI_API_KEY=your-litellm-key
```

Legacy `LITELLM_PROXY_URL` and `LITELLM_PROXY_KEY` are still accepted for existing local setups, but new deployments should prefer `OPENAI_BASE_URL` and `OPENAI_API_KEY`.

Do not commit `.env`, `scripts/config.json`, generated output, or LanceDB data.

## State Machine

```text
undone
  -> chunking -> queueing_1
  -> summarizing -> queueing_2
  -> embedding -> queueing_3
  -> db_inserting -> done

failed -> undone
failed_permanent
```

The watchdog advances queued work, resets stale active jobs, and prevents terminal states from being retried accidentally.

## Example Manifest

The batch initializer expects a manifest JSON file that maps file IDs to SRT files. See [examples/master_file_manifest.example.json](examples/master_file_manifest.example.json).

## Open Source Status

This repository was prepared from a personal AI-assisted engineering project. The architecture, reliability model, workflow design, and final review are human-owned; AI agents were used as implementation accelerators for scaffolding, refactoring, debugging, and documentation.

## Roadmap

- Extract the OpenAI-compatible request layer into a dedicated client module.
- Add provider-specific examples for LiteLLM, OpenRouter, vLLM, and local Ollama-compatible servers.
- Add integration tests with mocked chat and embedding endpoints.
- Add CLI ergonomics around batch initialization and phase selection.

## License

MIT
