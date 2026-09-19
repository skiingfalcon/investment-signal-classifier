.PHONY: sync test lint fmt facts smoke run report

sync:
	uv sync

test:
	uv run pytest -q

lint:
	uv run ruff check src tests

fmt:
	uv run ruff format src tests

# Requires: llama-cpp-spark cloned on this machine, qwen3.8-27b and gpt-oss-120b served
# (`uv run local-llm serve qwen3.8-27b`, `uv run local-llm serve gpt-oss-120b`).
facts:
	uv run isc facts --source xbrl --years 5 --out data/facts.jsonl

smoke:
	uv run isc jev classify examples/bicycle.json --model qwen3.8-27b

run:
	uv run isc run --backend llamacpp --source xbrl --verify --escalate

report:
	uv run isc report $(RUN_DIR)
