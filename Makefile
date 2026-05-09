.PHONY: test pack bench run test-local test-k6

test:
	python3 test/load_test.py

test-local:
	python3 test/load_test.py -u 10 -r 10

test-k6:
	k6 run test/script.js

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
