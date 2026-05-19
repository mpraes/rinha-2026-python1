# Submission Guide — rinha-2026-python1

Step-by-step instructions to deploy and test this backend on the official Rinha environment.

## Prerequisites

- Docker + Docker Compose on the build machine
- Git with push access to `https://github.com/mpraes/rinha-2026-python1`
- Public repository under MIT license

## 1. Build and verify locally

```bash
make pack                    # Generate data/rinha.idx from resources
docker compose up --build    # Build image + start stack
```

Smoke test:

```bash
curl -s http://localhost:9999/ready
curl -s -X POST http://localhost:9999/fraud-score \
  -H 'Content-Type: application/json' \
  -d @resources/example-payloads.json
```

Run the full k6 test:

```bash
k6 run test/test.js
```

## 2. Prepare the `submission` branch

The `submission` branch must contain **only runtime files** — no source code.

```bash
# Switch to submission branch (create if needed)
git checkout submission || git checkout -b submission

# Remove everything that isn't a runtime file
git rm -r --cached src/ docs/ resources/ scripts/ test/ 2>/dev/null || true
git rm --cached Makefile pyproject.toml requirements.txt README.md LICENSE EXAMPLES.md LOCAL_TESTING.md QUICK_TEST.md AGENTS.md .gitignore .dockerignore 2>/dev/null || true

# Ensure runtime files are present
git add docker-compose.yml nginx.conf info.json Dockerfile

# Build the Docker image and extract the pre-built index
docker build -t rinha-fraud-2026:latest .
docker create --name tmp-extract rinha-fraud-2026:latest
docker cp tmp-extract:/app/data ./data
docker rm tmp-extract

# Add pre-built data files
git add data/
git commit -m "submission: update runtime files for preview test"

# Push
git push origin submission
```

The submission branch should look like:

```
submission/
├── docker-compose.yml
├── nginx.conf
├── info.json
├── Dockerfile
└── data/
    └── rinha.idx
```

## 3. Trigger a preview test

Open an issue on [zanfranceschi/rinha-de-backend-2026](https://github.com/zanfranceschi/rinha-de-backend-2026) with:

```
rinha/test rinha-2026-python1
```

The Rinha Engine will:
1. Clone the `submission` branch
2. Run `docker compose up`
3. Execute the k6 load test
4. Post score as a comment and close the issue

You can submit as many preview tests as you want.

## 4. Iterate

After a preview test, check the score comment. Key metrics to watch:

| Metric | Target | Why |
|---|---|---|
| p99 latency | < 2000ms (ideally < 1ms) | Below 2000ms avoids -3000 penalty |
| HTTP error rate | < 1% | Errors weighted 5×; above 15% = -3000 |
| FP count | minimize | Weight 1× |
| FN count | minimize | Weight 3× |

Common iteration loop:

```bash
# Back on main, make changes
git checkout main
# ... edit code ...
make pack
docker compose up --build
k6 run test/test.js

# When satisfied, repeat step 2 and 3
```

## 5. Final test

The final test runs once at the end of Rinha. It uses a heavier script than the preview. The date is TBD.

Ensure the `submission` branch is up to date with your best configuration before the final test window.

## Registration file

The participant registration in the upstream Rinha repo uses:

```json
[
    {
        "id": "rinha-2026-python1",
        "repo": "https://github.com/mpraes/rinha-2026-python1"
    }
]
```

File: `participants/mpraes.json` in [zanfranceschi/rinha-de-backend-2026](https://github.com/zanfranceschi/rinha-de-backend-2026).

## Test environment specs

- Mac Mini Late 2014, Ubuntu 24.04
- 2.6 GHz CPU, 8 GB RAM, 1 TB storage
- 1 CPU core total, 350 MB memory total across all services
- linux/amd64 Docker images only
