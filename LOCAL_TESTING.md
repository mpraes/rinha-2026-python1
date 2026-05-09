# Local Testing Guide

This guide explains how to test your Rinha de Backend 2026 submission locally before official evaluation.

## Prerequisites

### 1. Install k6

**Linux/Ubuntu:**
```bash
sudo gpg -k
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491435B36B6
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update
sudo apt-get install k6
```

**macOS:**
```bash
brew install k6
```

**Windows:**
```powershell
choco install k6
```

**Or download directly:** https://github.com/grafana/k6/releases

### 2. Get Test Files

The official test files are in the main Rinha repository:

```bash
# Clone the official Rinha repository
git clone https://github.com/zanfranceschi/rinha-de-backend-2026.git
cd rinha-de-backend-2026

# Copy test files to your project
cp -r test /path/to/your/project/
```

The test directory should contain:
- `test/script.js` - k6 test script
- `test/test-data.json` - labeled test payloads

## Running Tests

### Method 1: Using Example Payloads (Quick Test)

You already have `resources/example-payloads.json`. Create a simple test:

```bash
# Start your API
docker compose up -d

# Run a quick manual test
curl -X POST http://localhost:9999/fraud-score \
  -H "Content-Type: application/json" \
  -d @resources/example-payloads.json
```

### Method 2: Using Official k6 Test Script

1. **Start your API:**
```bash
docker compose up -d
```

2. **Verify it's running:**
```bash
curl http://localhost:9999/ready
```

3. **Run the official k6 test:**
```bash
k6 run test/script.js
```

4. **View results:**
```bash
# Results will be in results.json
cat results.json | jq .
```

### Method 3: Custom k6 Test Script

If you don't have the official test script, create a basic one:

```javascript
// test/script.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';

// Load test data
const testData = new SharedArray('test data', function() {
  return JSON.parse(open('./test-data.json'));
});

export const options = {
  stages: [
    { duration: '30s', target: 20 },  // Ramp up to 20 users
    { duration: '1m', target: 20 },   // Stay at 20 users
    { duration: '30s', target: 0 },   // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(99)<2000'], // 99% of requests < 2000ms
  },
};

export default function() {
  const payload = testData[__VU % testData.length];
  const response = http.post(
    'http://localhost:9999/fraud-score',
    JSON.stringify(payload),
    { headers: { 'Content-Type': 'application/json' } }
  );

  check(response, {
    'status is 200': (r) => r.status === 200,
    'has approved field': (r) => r.json('approved') !== undefined,
    'has fraud_score field': (r) => r.json('fraud_score') !== undefined,
  });

  sleep(1);
}
```

## Monitoring During Tests

### Monitor Memory Usage

```bash
# Watch Docker container stats
watch -n 1 docker stats --no-stream

# Or check specific containers
docker stats api1 api2 lb --no-stream
```

### Monitor Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api1
```

### Monitor Network

```bash
# Check connections
docker compose exec lb netstat -an | grep 9999
```

## Performance Testing

### Memory Stress Test

```bash
# Run test and monitor memory
docker compose up -d
docker stats --no-stream > stats_before.txt
k6 run test/script.js
docker stats --no-stream > stats_after.txt
diff stats_before.txt stats_after.txt
```

### Latency Test

```bash
# Run k6 with detailed output
k6 run --out json=results.json test/script.js

# Analyze results
jq '.metrics.http_req_duration' results.json
```

## Test Data Generation

If you need to generate your own test data:

```python
# scripts/generate_test_data.py
import json
import random
from datetime import datetime, timedelta

def generate_transaction():
    return {
        "id": f"tx-{random.randint(1000000000, 9999999999)}",
        "transaction": {
            "amount": round(random.uniform(10, 5000), 2),
            "installments": random.randint(1, 12),
            "requested_at": (datetime.utcnow() - timedelta(days=random.randint(0, 30))).isoformat() + "Z"
        },
        "customer": {
            "avg_amount": round(random.uniform(100, 2000), 2),
            "tx_count_24h": random.randint(0, 20),
            "known_merchants": [f"MERC-{random.randint(1, 20):03d}" for _ in range(random.randint(0, 5))]
        },
        "merchant": {
            "id": f"MERC-{random.randint(1, 20):03d}",
            "mcc": str(random.choice(["5411", "5912", "5812", "5732", "5311"])),
            "avg_amount": round(random.uniform(50, 500), 2)
        },
        "terminal": {
            "is_online": random.choice([True, False]),
            "card_present": random.choice([True, False]),
            "km_from_home": round(random.uniform(0, 1000), 2)
        },
        "last_transaction": None if random.random() < 0.1 else {
            "timestamp": (datetime.utcnow() - timedelta(hours=random.randint(1, 24))).isoformat() + "Z",
            "km_from_current": round(random.uniform(0, 500), 2)
        }
    }

test_data = [generate_transaction() for _ in range(100)]
with open('test/test-data.json', 'w') as f:
    json.dump(test_data, f, indent=2)
```

## Interpreting Results

### Good Results

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

**What to look for:**
- ✅ p99 < 100ms (ideally < 10ms)
- ✅ HTTP errors = 0
- ✅ Failure rate < 15%
- ✅ Balanced FP/FN ratio

### Bad Results

```json
{
  "p99": "2500ms",
  "scoring": {
    "breakdown": {
      "http_errors": 750
    },
    "failure_rate": "20%",
    "final_score": -6000
  }
}
```

**What to fix:**
- ❌ p99 > 2000ms → optimize performance
- ❌ HTTP errors > 0 → fix crashes/timeout
- ❌ Failure rate > 15% → improve detection accuracy

## Common Issues

### 1. Connection Refused

```bash
# Check if API is running
docker compose ps

# Check logs
docker compose logs api1
```

### 2. Memory Issues

```bash
# Check memory limits
docker stats --no-stream

# If hitting limits, reduce memory usage or adjust docker-compose.yml
```

### 3. Timeout Errors

```bash
# Increase k6 timeout in test script
const response = http.post(url, payload, {
  timeout: '30s'
});
```

### 4. Wrong Results

If detection is poor:
- Check vectorization logic (all 14 dimensions)
- Verify normalization constants
- Test with known payloads manually

## Quick Test Checklist

```bash
# 1. Build and start
docker compose build
docker compose up -d

# 2. Verify ready endpoint
curl http://localhost:9999/ready

# 3. Test single request
curl -X POST http://localhost:9999/fraud-score \
  -H "Content-Type: application/json" \
  -d '{"id":"test","transaction":{"amount":100,"installments":1,"requested_at":"2026-03-11T20:23:35Z"},"customer":{"avg_amount":100,"tx_count_24h":1,"known_merchants":[]},"merchant":{"id":"MERC-001","mcc":"5912","avg_amount":100},"terminal":{"is_online":false,"card_present":true,"km_from_home":10},"last_transaction":null}'

# 4. Run k6 test
k6 run test/script.js

# 5. Check memory
docker stats --no-stream

# 6. View results
cat results.json | jq .

# 7. Cleanup
docker compose down
```

## Next Steps

After successful local testing:

1. **Push Docker image to public registry**
2. **Update submission branch**
3. **Push to GitHub**
4. **Run official preview test** (create issue with `rinha/test`)

---

**References:**
- k6 Documentation: https://grafana.com/docs/k6/latest/
- Rinha EVALUATION.md: docs/EVALUATION.md
- Example payloads: resources/example-payloads.json
