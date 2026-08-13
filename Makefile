.PHONY: test lint typecheck verify web-test package

test:
	pytest -q

lint:
	ruff check .

typecheck:
	mypy src

web-test:
	cd web && npm test -- --run

verify: lint typecheck test

package:
	cd web && npm ci && npm test -- --run && npm run build
	python scripts/prepare_web_package.py
	python -m build
	python -m pytest tests/integration/test_package_install.py -q
