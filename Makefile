all: test black

.PHONY: test
test:
	pytest

.PHONY: black
black:
	black src setup.py
