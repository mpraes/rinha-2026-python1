# Submission Review - Critical Issues Found

## ✅ What's Ready

### Code Quality
- ✅ Memory optimization working (memmap implementation)
- ✅ HTTP keep-alive enabled
- ✅ Search optimization with argpartition
- ✅ All 14 vector dimensions implemented correctly
- ✅ API endpoints working (GET /ready, POST /fraud-score)

### Branch Structure
- ✅ **main** branch: Contains all source code and documentation
- ✅ **submission** branch: Contains only runtime files
  - docker-compose.yml
  - nginx.conf
  - info.json
  - LICENSE

### Compliance
- ✅ MIT LICENSE present
- ✅ info.json with participant details
- ✅ No source code in submission branch
- ✅ Resource limits: 140M + 140M + 70M = 350 MB (correct)
- ✅ CPU limits: 0.45 + 0.45 + 0.1 = 1.0 core (correct)
- ✅ Port 9999 on load balancer
- ✅ Platform: linux-amd64 specified

---

## 🔴 CRITICAL BLOCKING ISSUES

### 1. Docker Image Not Published (BLOCKER)

**Problem:** 
The `docker-compose.yml` in submission branch references:
```yaml
image: rinha-fraud-2026:latest
```

This is a LOCAL image that doesn't exist on any public registry. The Rinha engine will FAIL to pull this image.

**Solution Required:**

You MUST build and push the Docker image to a public registry BEFORE submission.

#### Option A: Docker Hub (Recommended)

```bash
# 1. Login to Docker Hub
docker login

# 2. Build the image from main branch
git checkout main
docker build --platform linux-amd64 -t docker.io/YOUR_DOCKERHUB_USERNAME/rinha-fraud-2026:latest .

# 3. Push to Docker Hub
docker push docker.io/YOUR_DOCKERHUB_USERNAME/rinha-fraud-2026:latest

# 4. Update submission branch
git checkout submission
# Edit docker-compose.yml line 7:
# image: docker.io/YOUR_DOCKERHUB_USERNAME/rinha-fraud-2026:latest
git add docker-compose.yml
git commit -m "Update to use public Docker image"
```

#### Option B: GitHub Container Registry

```bash
# 1. Login to GitHub Container Registry
echo YOUR_GITHUB_TOKEN | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin

# 2. Build the image
git checkout main
docker build --platform linux-amd64 -t ghcr.io/YOUR_GITHUB_USERNAME/rinha-fraud-2026:latest .

# 3. Push to GHCR
docker push ghcr.io/YOUR_GITHUB_USERNAME/rinha-fraud-2026:latest

# 4. Make the package public (GHCR packages are private by default)
# Go to: https://github.com/users/YOUR_GITHUB_USERNAME/packages/container/rinha-fraud-2026/settings
# Change visibility to "Public"

# 5. Update submission branch
git checkout submission
# Edit docker-compose.yml line 7:
# image: ghcr.io/YOUR_GITHUB_USERNAME/rinha-fraud-2026:latest
git add docker-compose.yml
git commit -m "Update to use public Docker image"
```

**Verification:**
```bash
# After pushing, verify the image is accessible:
docker pull docker.io/YOUR_USERNAME/rinha-fraud-2026:latest
# or
docker pull ghcr.io/YOUR_GITHUB_USERNAME/rinha-fraud-2026:latest
```

---

### 2. Repository Not Public (BLOCKER)

**Problem:**
The repository might be private. The Rinha engine requires PUBLIC repositories.

**Solution:**
1. Go to GitHub → Your repository → Settings
2. Scroll to "Danger Zone" → "Change repository visibility"
3. Change to "Public"
4. Confirm the change

---

### 3. Not Registered in Rinha Repository (BLOCKER)

**Problem:**
You haven't registered your submission in the official Rinha repository.

**Solution:**
1. Fork https://github.com/zanfranceschi/rinha-de-backend-2026
2. In your fork, create file: `participants/mpraes.json`
3. Add this content:
```json
[{
  "id": "mpraes-python1",
  "repo": "https://github.com/mpraes/rinha-2026-python1"
}]
```
4. Commit and create a Pull Request to the main Rinha repository
5. Wait for maintainers to merge

---

## ⚠️ WARNINGS (Non-Blocking)

### 1. Docker Image Size

The Docker image will be large because it contains:
- Python runtime
- NumPy library
- 172 MB pre-generated index (data/rinha.idx)
- 48 MB compressed references (resources/references.json.gz)

**Estimate:** ~300-400 MB image size

This is acceptable but not ideal. Consider:
- Removing resources/references.json.gz from final image (only needed at build time)
- Using multi-stage build more aggressively

### 2. Cython Not Actually Used

The `requirements.txt` includes `cython>=3.0.0` but the code doesn't use it.

**Recommendation:** Remove Cython from requirements.txt to reduce image size and build time.

```bash
# Edit requirements.txt:
numpy>=1.24.0
# Remove cython line
```

### 3. Missing Dockerignore Optimization

The `.dockerignore` file might not be optimized, leading to slow builds.

**Recommendation:** Ensure `.dockerignore` excludes:
```
.git
.venv
__pycache__
*.pyc
*.pyo
*.pyd
.Python
data/
*.idx
.env
.venv
venv/
```

---

## 📋 Step-by-Step Submission Guide

### Step 1: Build and Test Locally

```bash
# Checkout main branch
git checkout main

# Build Docker image
docker build --platform linux-amd64 -t rinha-fraud-2026:latest .

# Test the image locally
docker run -d -p 8000:8000 --name test-api rinha-fraud-2026:latest

# Test endpoints
curl http://localhost:8000/ready
curl -X POST http://localhost:8000/fraud-score \
  -H "Content-Type: application/json" \
  -d '{"id":"test","transaction":{"amount":100,"installments":1,"requested_at":"2026-03-11T20:23:35Z"},"customer":{"avg_amount":100,"tx_count_24h":1,"known_merchants":[]},"merchant":{"id":"MERC-001","mcc":"5912","avg_amount":100},"terminal":{"is_online":false,"card_present":true,"km_from_home":10},"last_transaction":null}'

# Check memory usage
docker stats test-api

# Cleanup
docker stop test-api && docker rm test-api
```

### Step 2: Push to Public Registry

```bash
# Choose Docker Hub or GHCR (see instructions above)
# Example with Docker Hub:
docker tag rinha-fraud-2026:latest docker.io/YOUR_USERNAME/rinha-fraud-2026:latest
docker push docker.io/YOUR_USERNAME/rinha-fraud-2026:latest
```

### Step 3: Update Submission Branch

```bash
git checkout submission

# Edit docker-compose.yml to use your public image
# Line 7: image: docker.io/YOUR_USERNAME/rinha-fraud-2026:latest

git add docker-compose.yml
git commit -m "Update to use public Docker Hub image"
```

### Step 4: Push to GitHub

```bash
# Push both branches
git checkout main
git push origin main
git push origin submission

# Verify on GitHub:
# - main branch has source code
# - submission branch has only runtime files
# - Repository is PUBLIC
```

### Step 5: Register in Rinha

1. Fork https://github.com/zanfranceschi/rinha-de-backend-2026
2. Create `participants/mpraes.json` in your fork
3. Create Pull Request

### Step 6: Run Preview Test

1. Go to your repository Issues
2. Create new issue with description: `rinha/test`
3. Wait for Rinha engine to test and comment with results

---

## Current File Structure

### main branch:
```
├── .dockerignore
├── .gitignore
├── .github/
├── AGENTS.md
├── Dockerfile
├── EXAMPLES.md
├── LICENSE
├── Makefile
├── SUBMISSION_CHECKLIST.md
├── docker-compose.yml
├── info.json
├── nginx.conf
├── requirements.txt
├── data/
│   └── rinha.idx (172 MB)
├── docs/
├── resources/
│   ├── example-payloads.json
│   ├── example-references.json
│   ├── mcc_risk.json
│   ├── normalization.json
│   └── references.json.gz (48 MB)
└── src/
    ├── __init__.py
    ├── pack.py
    └── server.py
```

### submission branch:
```
├── LICENSE
├── docker-compose.yml  ← NEEDS UPDATE: public image URL
├── info.json
└── nginx.conf
```

---

## Verification Commands

After completing all steps:

```bash
# Verify image is public
docker pull docker.io/YOUR_USERNAME/rinha-fraud-2026:latest

# Test full stack
git checkout submission
docker compose up -d
curl http://localhost:9999/ready
docker stats  # Should show < 350 MB total

# Check memory split
docker stats --no-stream
# api1: should be < 140 MB
# api2: should be < 140 MB
# lb: should be < 70 MB
```

---

## Summary

**You CANNOT submit until:**
1. ✅ Docker image is built and pushed to PUBLIC registry
2. ✅ docker-compose.yml updated with public image URL
3. ✅ Repository is PUBLIC on GitHub
4. ✅ Registered in Rinha repository (participants/mpraes.json)

**Current Status:**
- Code: ✅ Ready
- Branches: ✅ Ready
- Docker image: 🔴 NOT PUBLISHED (blocking)
- Repository visibility: ❓ Unknown (verify it's public)
- Registration: 🔴 NOT REGISTERED (blocking)
