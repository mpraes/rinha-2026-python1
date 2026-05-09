# Submission Checklist for Rinha de Backend 2026

## Completed ✓

### 1. Code Optimizations
- ✅ Memory optimization: numpy.memmap for index (172 MB → ~5 MB footprint)
- ✅ HTTP keep-alive support in server
- ✅ Nginx connection pooling and timeouts
- ✅ Search optimization with argpartition

### 2. Branch Structure
- ✅ **main** branch: Contains all source code
- ✅ **submission** branch: Contains only runtime files
  - docker-compose.yml
  - nginx.conf
  - info.json
  - LICENSE
  - data/rinha.idx (172 MB pre-generated index)

### 3. Required Files
- ✅ MIT LICENSE file created
- ✅ info.json completed with participant details
- ✅ docker-compose.yml at root of submission branch
- ✅ Memory and CPU limits respect constraints (1 CPU, 350 MB total)

---

## Critical Steps Remaining 🔴

### 1. Build and Push Docker Image (REQUIRED)

The submission branch references `rinha-fraud-2026:latest` but this needs to be a **public** image.

**Option A: Docker Hub**
```bash
# From main branch
docker build --platform linux-amd64 -t docker.io/YOUR_USERNAME/rinha-fraud-2026:latest .
docker push docker.io/YOUR_USERNAME/rinha-fraud-2026:latest

# Then update submission branch docker-compose.yml:
# image: docker.io/YOUR_USERNAME/rinha-fraud-2026:latest
```

**Option B: GitHub Container Registry**
```bash
# From main branch
docker build --platform linux-amd64 -t ghcr.io/YOUR_USERNAME/rinha-fraud-2026:latest .
docker push ghcr.io/YOUR_USERNAME/rinha-fraud-2026:latest

# Then update submission branch docker-compose.yml:
# image: ghcr.io/YOUR_USERNAME/rinha-fraud-2026:latest
```

**Important:** Image MUST be compatible with `linux-amd64` platform!

### 2. Update docker-compose.yml (REQUIRED)

Edit `docker-compose.yml` in the **submission** branch:

```yaml
services:
  api1: &api
    image: YOUR_PUBLIC_IMAGE_URL  # <-- Update this line
    environment:
      - PORT=8000
    # ... rest of config
```

Then commit:
```bash
git checkout submission
git add docker-compose.yml
git commit -m "Update image reference to public registry"
git checkout main
```

### 3. Push to GitHub (REQUIRED)

```bash
# Push both branches
git push origin main
git push origin submission

# Ensure repository is PUBLIC
# Go to GitHub → Settings → Change repository visibility to Public
```

### 4. Register in Rinha Repository (REQUIRED)

1. Go to https://github.com/zanfranceschi/rinha-de-backend-2026
2. Fork the repository
3. Create file `participants/YOUR_GITHUB_USERNAME.json`:

```json
[{
  "id": "mpraes-python1",
  "repo": "https://github.com/YOUR_USERNAME/rinha-2026-python1"
}]
```

4. Open a pull request to merge your fork into the main rinha repo

### 5. Test Locally (RECOMMENDED)

```bash
# Build image from main branch
docker build --platform linux-amd64 -t rinha-fraud-2026:latest .

# Run from submission branch
git checkout submission
docker compose up -d

# Test endpoints
curl http://localhost:9999/ready
curl -X POST http://localhost:9999/fraud-score \
  -H "Content-Type: application/json" \
  -d '{"id":"test","transaction":{"amount":100,"installments":1,"requested_at":"2026-03-11T20:23:35Z"},"customer":{"avg_amount":100,"tx_count_24h":1,"known_merchants":[]},"merchant":{"id":"MERC-001","mcc":"5912","avg_amount":100},"terminal":{"is_online":false,"card_present":true,"km_from_home":10},"last_transaction":null}'

# Check memory usage
docker stats
```

### 6. Run Preview Test (RECOMMENDED)

1. Ensure your repo is public and both branches are pushed
2. Go to your repository issues
3. Create new issue with description: `rinha/test`
4. Wait for Rinha engine to test and post results

---

## Final Checklist Before Submission

- [ ] Docker image built and pushed to public registry
- [ ] docker-compose.yml updated with public image URL
- [ ] Both branches pushed to GitHub
- [ ] Repository is public
- [ ] info.json has correct details
- [ ] Tested locally with `docker compose up`
- [ ] Memory usage verified under 350 MB total
- [ ] Repository registered in rinha-de-backend-2026/participants/

---

## File Structure Summary

**main branch:**
```
├── src/               # Source code
├── resources/         # Reference data
├── docs/              # Documentation
├── LICENSE            # MIT license
├── info.json          # Participant info
├── docker-compose.yml
├── Dockerfile
└── ...
```

**submission branch:**
```
├── docker-compose.yml # References public image
├── nginx.conf         # Load balancer config
├── info.json          # Participant info
├── LICENSE            # MIT license
└── data/
    └── rinha.idx      # Pre-generated index (172 MB)
```

---

## Notes

- The `data/rinha.idx` file is included in submission branch for verification
- However, this file should also be inside the Docker image
- If the Docker image already contains this file, you can remove it from submission branch
- Keep nginx.conf in submission for volume mount reference
