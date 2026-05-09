.PHONY: test smoke test-full pack bench run run-detached stop

# Quick smoke test (5 requests, validates API contract)
smoke:
	k6 run test/smoke.js

# Full test with scoring (54k requests, 120s duration)
test:
	k6 run test/test.js

# Alias for test
test-full: test

# Python load test (alternative, no k6 required)
test-python:
	python3 test/load_test.py -u 20 -r 50

pack:
	python3 -m src.pack

bench:
	python3 -m src.bench

run:
	docker compose up --build

run-detached:
	docker compose up --build -d

stop:
	docker compose down
