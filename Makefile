BIN=.venv/bin
PYTHON=$(BIN)/python
PIP=$(BIN)/pip

all: .venv/bin/ofxstatement .requirements.installed

.venv:
	virtualenv -p python3 --no-site-packages .venv

.venv/bin/ofxstatement: .venv setup.py
	$(PYTHON) setup.py develop

.requirements.installed: requirements.txt
	$(PIP) install -r requirements.txt
	touch .requirements.installed

test:
	$(BIN)/py.test --capture=no
