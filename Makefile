.PHONY: test lint typecheck verify web-test

test:
	pytest -q

lint:
	ruff check .

typecheck:
	mypy src

web-test:
	cd web && npm test -- --run

verify: lint typecheck test
