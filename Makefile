.PHONY: format format-check pylint typecheck lint test docs build pypy-test pypy-live
PYTHON ?= python3
PLATFORM ?= linux/amd64
PROFILE ?= dev
IMAGE_BUILDER ?= docker
IMAGE_NAME ?= msg555/dirdiff

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
ifeq ($(OS),Windows_NT)
	$(PYTHON) -m pytest -sv --cov=dirdiff -m 'not cap and not unix' tests
else
	$(PYTHON) -m pytest -sv --cov=dirdiff -m 'not cap' tests
endif

test-all:
ifeq ($(OS),Windows_NT)
	$(PYTHON) -m pytest -sv --cov=dirdiff -m 'not unix' tests
else
	$(PYTHON) -m pytest -sv --cov=dirdiff -m '' tests
endif

build:
	$(PYTHON) -m build

clean:
	rm -rf build dist *.egg-info

image:
	$(IMAGE_BUILDER) build -t $(IMAGE_NAME) .

image-%: image
	docker run --rm -v "$${PWD}:/dirdiff" $(IMAGE_NAME) make $*

pypi-test: build
	TWINE_USERNAME=__token__ TWINE_PASSWORD="$(shell gpg -d test.pypi-token.gpg)" \
    $(PYTHON) -m twine upload --repository testpypi dist/*

pypi-live: build
	TWINE_USERNAME=__token__ TWINE_PASSWORD="$(shell gpg -d live.pypi-token.gpg)" \
    $(PYTHON) -m twine upload dist/*
