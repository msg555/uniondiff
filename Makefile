.PHONY: format format-check pylint typecheck lint test docs build pypy-test pypy-live
PYTHON ?= python3
PLATFORM ?= linux/amd64
PROFILE ?= dev

all: format lint test docs

format:
	$(PYTHON) -m black .
	$(PYTHON) -m isort --profile=black .

format-check:
	$(PYTHON) -m black --check .
	$(PYTHON) -m isort --profile=black --check .

pylint:
	$(PYTHON) -m pylint dirdiff tests

typecheck:
	$(PYTHON) -m mypy dirdiff tests

lint: format-check pylint typecheck

test:
	$(PYTHON) -m pytest -sv --cov=tplbuild -m unit tests

build:
	$(PYTHON) -m build

clean:
	rm -rf build dist *.egg-info

pypi-test: build
	TWINE_USERNAME=__token__ TWINE_PASSWORD="$(shell gpg -d test.pypi-token.gpg)" \
    $(PYTHON) -m twine upload --repository testpypi dist/*

pypi-live: build
	TWINE_USERNAME=__token__ TWINE_PASSWORD="$(shell gpg -d live.pypi-token.gpg)" \
    $(PYTHON) -m twine upload dist/*
