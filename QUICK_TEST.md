# Quick Local Testing Guide

## Setup (One-time)

```bash
# 1. Install k6 (optional, for official test)
# See: https://grafana.com/docs/k6/latest/set-up/install-k6/

# 2. Get official test files from Rinha repo (optional)
git clone https://github.com/zanfranceschi/rinha-de-backend-2026.git
cp -r rinha-de-backend-2026/test ./test/
```

## Run Tests

### Option 1: Simple Python Test (No k6 needed)

```bash
# Start API
make run-detached

# Run test
make test

# Or with custom parameters
python3 test/load_test.py -u 20 -r 50  # 20 users, 50 requests each

# View results
cat test_results.json | jq .

# Stop API
make stop
```

### Option 2: k6 Test (Official)

```bash
# Start API
make run-detached

# Run k6 test
make test-k6

# Or directly
k6 run test/script.js

# View results
cat results.json | jq .

# Stop API
make stop
```

## Monitor During Test

```bash
# In another terminal
docker stats --no-stream
```

## What to Check

✅ **Good Results:**
- P99 latency < 100ms (ideally < 10ms)
- HTTP errors = 0
- All checks pass
- Memory < 350 MB total

❌ **Bad Results:**
- P99 > 2000ms (triggers cutoff)
- HTTP errors > 0
- Memory exceeds limits
- Timeouts

## Quick Commands

```bash
# Build and start
make run-detached

# Test endpoint
curl http://localhost:9999/ready

# Run load test
make test

# Check memory
docker stats --no-stream

# Stop everything
make stop
```

## Note

Test files (`test/` directory, `test_results.json`, `results.json`) are excluded from git via `.gitignore`. These are for local testing only and won't be part of your submission.

For full scoring with labeled test data, use the official test files from the Rinha repository or wait for the preview test via GitHub issue.
