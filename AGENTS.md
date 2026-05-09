# AGENTS.md

Behavioral guidelines and project-specific context for Rinha de Backend 2026 - Fraud Detection API.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## Project Overview

This is a submission for Rinha de Backend 2026, a fraud detection API competition. The core task is building a vector search system that classifies credit card transactions as fraud or legitimate.

**Key constraints:**
- Port 9999 (fixed)
- CPU limit: 1 core total across all services
- Memory limit: 350 MB total across all services
- Minimum architecture: 1 load balancer + 2 API instances (round-robin)
- Network mode: bridge (host/privileged not allowed)
- docker-compose.yml must be at root of `submission` branch
- Two branches required: `main` (source code) and `submission` (runtime files only, no source)
- Repository must be public and MIT licensed

**Test environment:** Mac Mini Late 2014, Ubuntu 24.04, 2.6 GHz, 8 GB RAM, 1 TB storage

**Scoring (range: -6000 to +6000):**
- Latency component: based on p99, logarithmic scale
  - +3000 for p99 ≤ 1ms
  - -3000 for p99 > 2000ms
  - Every 10x improvement = +1000 points
- Detection component: based on weighted errors
  - Weights: FP=1, FN=3, HTTP error=5
  - +3000 for zero errors
  - -3000 if failure rate > 15%
- Final score = latency_score + detection_score

**Critical insight:** HTTP errors hurt twice (weight=5 AND count toward failure rate). When in doubt, return a safe response rather than 5xx.

## Project-Specific Technical Decisions

### Stack
- Python for HTTP server and entrypoint
- Cython for hot path in `POST /fraud-score`
- Load balancer (TBD) for round-robin, no detection logic
- Custom binary index format (`data/index.bin`) for vector search

### Vector Search Strategy
- IVF (Inverted File Index) or exact k-NN with k=5
- Pre-computed index stored in binary format (`data/index.bin.gz`)
- 14-dimensional vectors with float32 values
- Brute force O(N×14) is expensive; consider ANN (HNSW, IVF) or VP Tree

### The 14 Vector Dimensions
Indices 0-13, normalized to [0.0, 1.0] except for -1 sentinel:

| Index | Dimension | Formula |
|-------|-----------|---------|
| 0 | amount | `clamp(tx.amount / 10000)` |
| 1 | installments | `clamp(tx.installments / 12)` |
| 2 | amount_vs_avg | `clamp((tx.amount / customer.avg_amount) / 10)` |
| 3 | hour_of_day | `hour(tx.requested_at) / 23` (UTC, 0-23) |
| 4 | day_of_week | `day_of_week(tx.requested_at) / 6` (mon=0, sun=6) |
| 5 | minutes_since_last_tx | `clamp(minutes / 1440)` or `-1` if null |
| 6 | km_from_last_tx | `clamp(km / 1000)` or `-1` if null |
| 7 | km_from_home | `clamp(terminal.km_from_home / 1000)` |
| 8 | tx_count_24h | `clamp(customer.tx_count_24h / 20)` |
| 9 | is_online | `1` if online, else `0` |
| 10 | card_present | `1` if present, else `0` |
| 11 | unknown_merchant | `1` if merchant.id not in known_merchants |
| 12 | mcc_risk | lookup in mcc_risk.json (default 0.5) |
| 13 | merchant_avg_amount | `clamp(merchant.avg_amount / 10000)` |

**Sentinel value:** `-1` at indices 5-6 indicates `last_transaction: null` (first transaction). Do NOT filter or replace these values - they're intentional for clustering "no history" transactions together.

### Decision Logic
```
1. Vectorize transaction (14 dimensions)
2. Find 5 nearest neighbors in reference dataset
3. fraud_score = (frauds among 5) / 5
4. approved = fraud_score < 0.6
```

### Reference Files (in resources/)
- `references.json.gz` (~284 MB uncompressed): 3,000,000 labeled vectors
- `mcc_risk.json`: MCC → risk score mapping (default 0.5 if not found)
- `normalization.json`: Constants for normalization formulas

**These files don't change during tests** - pre-process them at build time or startup.

## Build and Development Commands

```bash
# Development
make test     # Run tests with unittest (stdlib only)
make pack     # Generate data/index.bin from references
make bench    # Benchmark the fraud detection

# Runtime
docker compose up --build   # Build and run full stack

# Production (submission branch)
# Only docker-compose.yml and data/*.idx files needed
# No source code on submission branch
```

## API Contract

### `GET /ready`
- Returns `2xx` when ready to receive requests
- No body required

### `POST /fraud-score`
Request:
```json
{
  "id": "tx-123",
  "transaction": { "amount": 384.88, "installments": 3, "requested_at": "2026-03-11T20:23:35Z" },
  "customer": { "avg_amount": 769.76, "tx_count_24h": 3, "known_merchants": ["MERC-009", "MERC-001"] },
  "merchant": { "id": "MERC-001", "mcc": "5912", "avg_amount": 298.95 },
  "terminal": { "is_online": false, "card_present": true, "km_from_home": 13.7 },
  "last_transaction": { "timestamp": "...", "km_from_current": 18.8 } | null
}
```

Response:
```json
{ "approved": false, "fraud_score": 0.8 }
```

**Error handling:** The server must avoid HTTP errors on the fraud path. Parse failures, wrong methods, or unknown routes should return `HTTP 200` with a safe response rather than `4xx`/`5xx`.

## Architecture Constraints

```
Client → lb (port 9999) → api1 (round-robin)
                           ↘ api2 (round-robin)
```

- Load balancer: TBD, round-robin only, NO fraud detection logic
- Two API instances minimum
- All services share 1 CPU and 350 MB memory total
- Resource allocation (example):
  - api1: ~0.4 CPU, ~150M memory
  - api2: ~0.4 CPU, ~150M memory
  - lb: ~0.2 CPU, ~50M memory

## Testing and Evaluation

The official test uses k6 with pre-labeled payloads. Tests compare your `approved` response against expected labels:
- **TP (True Positive):** fraud correctly denied
- **TN (True Negative):** legitimate correctly approved
- **FP (False Positive):** legitimate incorrectly denied
- **FN (False Negative):** fraud incorrectly approved
- **Error:** HTTP non-200 response

**Local testing:**
```bash
# Run k6 load test (test script in /test directory)
k6 run test/script.js
```

## Key Gotchas

1. **HTTP errors are weighted 5x worse than false positives.** When uncertain, return `approved: true, fraud_score: 0.0` rather than 5xx.

2. **The 15% failure rate cutoff is strict.** Above this, detection_score = -3000 regardless of latency.

3. **p99 saturation at 1ms.** Optimizing below 1ms doesn't earn more points.

4. **MCC not in mcc_risk.json.** Use 0.5 as default - this is expected behavior.

5. **`-1` sentinel in vectors.** Indices 5-6 use -1 for "no previous transaction." Don't filter or replace these.

6. **Docker images must support linux-amd64.** Mac users: don't build arm64-only images.

7. **Reference files are static.** Pre-process them freely at build time - they won't change during testing.

8. **Test payloads cannot be used as lookup.** Using test data for fraud detection is disallowed and distorts preview results.

## Code Style and Patterns

- Standard library preferred (unittest for tests)
- Cython for performance-critical paths only
- Binary formats for pre-computed indices
- Avoid HTTP errors - prefer safe responses
- Load balancer does NO detection logic
- Pre-process reference files at build time, not runtime

## Repository Structure

```
# main branch
├── src/           # Python source code
├── scripts/       # pack.py for index generation
├── data/          # Generated *.bin files (gitignored)
├── resources/     # Reference files from competition
├── docs/          # Competition documentation
├── Dockerfile
├── docker-compose.yml
└── Makefile       # Build commands

# submission branch (no source code!)
├── docker-compose.yml
├── data/*.bin     # Pre-built indices
└── info.json      # Submission metadata
```

**info.json required fields:**
```json
{
  "participants": ["Your Name"],
  "social": ["https://github.com/yourusername"],
  "source-code-repo": "https://github.com/your/repo",
  "stack": ["python", "cython"],
  "open_to_work": true
}
```

---

## General Behavioral Guidelines

These guidelines apply to all coding tasks in this repository.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
