.PHONY: test pack bench run

test:
	python -m pytest tests/ -v

pack:
	python -m src.pack

bench:
	python -m src.bench

run:
	docker compose up --build
