# AGENTS.md

## Project Overview

This is a **Rinha de Backend 2026** submission — a high-performance fraud detection API in Python. It uses an IVF (Inverted File) index with int8 quantization for approximate nearest-neighbor search to classify transactions as fraudulent or legitimate. The architecture is optimized for throughput under tight resource constraints.

## Architecture

```
Client → nginx (port 9999, round-robin) → [api1:8000, api2:8000]
```

- **nginx** (load balancer): Alpine-based, 0.1 CPU / 30MB RAM limit, connection keepalive enabled
- **api1 / api2**: Two identical Python ASGI instances, each limited to 0.45 CPU / 160MB RAM
- Total budget: 1.0 CPU, 350MB RAM across all containers

The app uses a **raw ASGI interface** (no framework like FastAPI/Starlette) for minimal overhead. The `app` function in `src/server.py:190` directly handles the ASGI protocol.

## Essential Commands

```bash
# Run locally (requires index file — see "Data Pipeline" below)
python -m uvicorn src.server:app --host 0.0.0.0 --port 8000 --log-level error

# Build and run with Docker Compose
docker compose up --build

# Generate the binary index from references.json.gz
python -m src.pack
```

There is no formal test suite. `test_change.py` is a standalone ad-hoc script, not part of any framework.

## Data Pipeline

1. **Input**: `resources/references.json.gz` — a gzipped JSON file containing reference transactions with 14-dimensional vectors and labels (`"fraud"` / `"legit"`)
2. **Pack**: `python -m src.pack` reads this file (streaming with `ijson`), computes quantization parameters, runs k-means clustering (64 centroids, 20 iterations), and writes `data/rinha.idx` (~63MB)
3. **Serve**: `src/server.py` loads `data/rinha.idx` at startup into numpy arrays in memory

The binary index format (`rinha.idx`) uses magic `0x52494E48` ("RINH"), version 5, little-endian. Structure:
- Header: magic (4B), version (4B), n_vectors (4B), n_centroids (4B), n_dims (4B)
- Quantization params: dim_min (n_dims × float32), dim_scale (n_dims × float32)
- Centroids: n_centroids × n_dims × float32
- Labels: n_vectors × int32 (1=fraud, 0=legit)
- Quantized vectors: n_vectors × n_dims × int8
- Inverted lists: for each centroid, count (uint32) then count × uint32 indices

**Important**: The index file is **not** committed to git (it's ~63MB). It must be regenerated from `references.json.gz` before running locally. This file IS copied into the Docker image via the Dockerfile.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/ready` | Health check, returns `{"status": "ready"}` |
| `POST` | `/fraud-score` | Fraud detection, returns `{"approved": bool, "fraud_score": float}` |
| Any other | Any | Fallback: returns `{"approved": true, "fraud_score": 0.0}` (safe default) |

### Request Payload Structure (`POST /fraud-score`)

```json
{
  "transaction": { "amount": float, "installments": int, "requested_at": "ISO8601" },
  "customer": { "avg_amount": float, "tx_count_24h": int, "known_merchants": [str] },
  "merchant": { "id": str, "mcc": str, "avg_amount": float },
  "terminal": { "is_online": bool, "card_present": bool, "km_from_home": float },
  "last_transaction": { "timestamp": "ISO8601", "km_from_current": float } | null
}
```

## Fraud Detection Logic

1. **Vectorize** (`server.py:83-122`): Convert the payload into a 14-dimensional float32 vector using normalization constants from `resources/normalization.json` and MCC risk scores from `resources/mcc_risk.json`. Dimensions 5/6 use `-1.0` as a sentinel when `last_transaction` is null.
2. **Quantize** (`server.py:124-130`): Map float32 vector to int8 using per-dimension min/scale from the index.
3. **IVF Search** (`server.py:132-164`): Find nearest centroid → retrieve candidates from that centroid's inverted list (capped at 50) → compute L2 distances in int8 space → select top-5 neighbors → count fraud labels.
4. **Score** (`server.py:166-172`): `fraud_score = fraud_count / 5.0`. Approved if `fraud_score < 0.6`.

## Code Organization

```
src/
  server.py    — ASGI app, FraudDetector class, index loader, route handlers
  pack.py      — Offline index builder (reads references.json.gz → writes rinha.idx)
  __init__.py  — Empty
resources/
  normalization.json  — Per-dimension normalization constants (7 keys)
  mcc_risk.json      — MCC code → risk score mapping (10 entries)
data/
  rinha.idx          — Binary IVF+int8 index (generated, ~63MB)
```

## Key Design Decisions & Gotchas

- **Raw ASGI, no framework**: The app handles ASGI directly (`scope`/`receive`/`send`). There is no middleware, no routing framework. Adding one (FastAPI, etc.) would add overhead — this is intentional for the performance competition.
- **Module-level initialization**: The `FraudDetector` is created at module import time (`server.py:176-187`). This means the index is loaded once at startup before any request is served. The `detector` global is set before the ASGI app runs.
- **Pre-encoded JSON responses**: `RESPONSE_READY` and `RESPONSE_SAFE` are serialized once at module level via `orjson.dumps()` and reused, avoiding repeated serialization.
- **Error handling is intentionally permissive**: The `POST /fraud-score` handler catches all exceptions and returns `RESPONSE_SAFE` (approved=true, score=0). This is a deliberate choice — in a fraud detection benchmark, false negatives (approving fraud) are acceptable if it avoids errors, but this trades safety for availability.
- **Single-centroid search**: Only the single nearest centroid's inverted list is searched. No multi-probe. This is a performance/accuracy tradeoff.
- **Candidate cap at 50**: The `max_candidates = 50` limit in `search()` caps how many vectors from the inverted list are distance-compared. This directly affects accuracy vs. latency.
- **Fallback route returns safe**: Any unmatched path/method returns `RESPONSE_SAFE` (approved=true), not a 404.
- **No `.copy()` in quantize**: The `quantize` method returns `astype(np.int8)` without `.copy()`, which is fine since `astype` creates a new array.
- **`pack.py` requires `references.json.gz`**: This input file is not in the repo. It's a Rinha de Backend competition artifact that must be placed in `resources/` before running the pack step.

## Resource Constraints

The competition enforces strict limits via docker-compose:
- Each API container: **0.45 CPU, 160MB RAM**
- nginx: **0.1 CPU, 30MB RAM**
- Platform: **linux/amd64** (specified in docker-compose and Dockerfile)

These constraints drive all optimization decisions. The int8 quantization, raw ASGI, and single-centroid search are all in service of fitting within 160MB per instance while maximizing throughput.

## Dependencies

- **uvicorn** (with `[standard]` extras for httptools/uvloop): ASGI server
- **orjson**: Fast JSON serialization/deserialization
- **numpy**: Vector operations, quantization, distance computation
- **ijson**: Streaming JSON parsing for the pack step (not used at serve time)
