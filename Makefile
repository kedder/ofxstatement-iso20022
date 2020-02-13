BIN=.venv/bin
PYTHON=$(BIN)/python
PIP=$(BIN)/pip

all: .venv/bin/ofxstatement .requirements.installed

.venv:
	python3 -m venv .venv

.venv/bin/ofxstatement: .venv setup.py
	$(PYTHON) setup.py develop

.requirements.installed: requirements.txt
	$(PIP) install -r requirements.txt
	touch .requirements.installed

test:
	$(BIN)/py.test --capture=no

clean:
	rm -r .venv .requirements.installed
