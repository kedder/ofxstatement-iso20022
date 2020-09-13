all: test mypy black

.PHONY: test
test:
	pytest

.PHONY: mypy
mypy:
	mypy src tests

.PHONY: black
black:
	black src tests setup.py
