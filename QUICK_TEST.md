# Quick Local Testing Guide

## Prerequisites

```bash
# Install k6 (required for official tests)
# Ubuntu/Debian:
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491435B36B6
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update
sudo apt-get install k6

# macOS:
brew install k6
```

## Quick Start

### 1. Smoke Test (Quick Validation - 5 requests)

```bash
# Start API
make run-detached

# Run smoke test (validates API contract)
make smoke

# Stop API
make stop
```

**Expected output:**
```
✓ status is 200
✓ body is json
✓ approved is boolean
✓ fraud_score is number
```

### 2. Full Test (Complete Evaluation - 54k requests)

```bash
# Start API
make run-detached

# Run full test with scoring (120 seconds, 900 RPS)
make test

# View results
cat test/results.json | jq .

# Stop API
make stop
```

**Expected output:**
```json
{
  "p99": "5.81ms",
  "scoring": {
    "breakdown": {
      "true_positive_detections": 1735,
      "true_negative_detections": 3210,
      "false_positive_detections": 40,
      "false_negative_detections": 15,
      "http_errors": 0
    },
    "failure_rate": "1.10%",
    "final_score": 3425.03
  }
}
```

## Test Commands

```bash
make smoke        # Quick validation (5 requests, ~10s)
make test         # Full test with scoring (54k requests, 120s)
make test-python  # Alternative Python test (no k6 required)
```

## Monitor During Tests

```bash
# Watch memory usage
watch -n 1 docker stats --no-stream

# Check logs
docker compose logs -f api1
```

## What Gets Tested

### Smoke Test (`smoke.js`)
- ✅ API responds on port 9999
- ✅ Returns 200 status
- ✅ Returns valid JSON
- ✅ Has `approved` (boolean) field
- ✅ Has `fraud_score` (number) field

### Full Test (`test.js`)
- 🎯 **54,100 test transactions** with expected results
- 🎯 **Detection accuracy**: TP, TN, FP, FN, HTTP errors
- 🎯 **Latency metrics**: P99, throughput
- 🎯 **Full scoring**: Detection score + Latency score

## Score Interpretation

**Good Results:**
- ✅ P99 < 10ms → latency score ~2000+
- ✅ HTTP errors = 0
- ✅ Failure rate < 5%
- ✅ Final score > 3000

**Bad Results:**
- ❌ P99 > 2000ms → latency score = -3000 (cutoff)
- ❌ HTTP errors > 0 → impacts both detection and failure rate
- ❌ Failure rate > 15% → detection score = -3000 (cutoff)

## Memory Validation

```bash
# Start API
make run-detached

# Check memory limits
docker stats --no-stream

# Expected:
# api1: < 140 MB
# api2: < 140 MB
# lb: < 70 MB
# Total: < 350 MB
```

## Troubleshooting

### Test fails to connect
```bash
# Check if API is running
curl http://localhost:9999/ready

# Check logs
docker compose logs api1
```

### Memory issues
```bash
# If hitting limits, reduce container memory or optimize code
docker stats --no-stream
```

### Test file not found
```bash
# Ensure symlink exists
ls -la test/test-data.json

# If missing, create it:
cd test && ln -sf test_data.json test-data.json
```

## Test Files (in .gitignore)

The following test files are excluded from git:
- `test/` directory
- `test/results.json`
- `test_data.json` (47 MB)

These are for local testing only and won't be part of your submission.

## Next Steps After Testing

1. **If tests pass:** 
   - Build and push Docker image to public registry
   - Update `docker-compose.yml` with public image URL
   - Push to GitHub

2. **If tests fail:**
   - Debug issues (memory, performance, accuracy)
   - Optimize code
   - Re-run tests

3. **Run preview test:**
   - Create GitHub issue with description: `rinha/test`
   - Wait for official Rinha engine results
