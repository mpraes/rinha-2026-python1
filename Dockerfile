FROM --platform=linux/amd64 python:3.12-slim AS build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY resources ./resources

RUN if [ ! -f data/index.bin ]; then \
        python -m src.pack; \
    fi

FROM --platform=linux/amd64 python:3.12-slim

WORKDIR /app

COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /app/src ./src
COPY --from=build /app/resources ./resources
COPY --from=build /app/data ./data

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

ENTRYPOINT ["python", "-m", "src.server"]
